"""JWT令牌管理模块。

提供JWT（JSON Web Token）的生成、验证和管理功能：
- JWT令牌的生成和签名
- 令牌验证和解码
- 基于Redis的会话管理
- 单设备登录控制
- 令牌刷新和撤销
- 设备ID管理

使用HS256算法签名，支持配置令牌过期时间。
"""

import hashlib
import time
from datetime import timedelta
from typing import Any, Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from redis.asyncio import Redis

from app.common.time_ import time_now
from app.configs import base_configs
from app.core.redis_ import redis_client


class UserClaims(BaseModel):
    """JWT用户声明模型.

    只存储不可变的基础信息，可变信息（如用户名、角色）通过user_id实时查询

    Attributes:
        user_id (str): 用户唯一标识符（不可变）
        exp (int): token过期时间戳
        device_id (None | str): 设备标识符，用于单设备登录控制
        iat (int): token签发时间戳
    """

    user_id: str
    exp: int
    device_id: None | str = None
    iat: int  # issued at - 签发时间


class TokenInfo(BaseModel):
    """Token信息模型.

    Attributes:
        access_token (str): 访问令牌
        token_type (str): 令牌类型，默认为"bearer"
        expires_in (int): token过期时间（秒）
    """

    access_token: str
    token_type: str = "bearer"
    expires_in: int


class JWTManager:
    """JWT管理器 - 负责token生成、验证和用户会话管理.

    该类提供了完整的JWT token管理功能，包括token的生成、验证，
    以及基于Redis的单设备登录控制和用户会话管理。

    Attributes:
        secret_key (str): JWT签名密钥
        algorithm (str): JWT签名算法
        redis_client (Redis): Redis客户端实例
    """

    def __init__(self, secret_key: str, algorithm: str = "HS256"):
        """初始化JWT管理器.

        Args:
            secret_key (str): JWT签名密钥
            algorithm (str, optional): JWT签名算法. Defaults to "HS256".
        """
        self.secret_key = secret_key
        self.algorithm = algorithm
        self.redis_client: Redis = redis_client

    async def generate_token(
        self,
        user_id: str,
        device_id: None | str = None,
        store_in_redis: bool = True,
        device_info: Optional[dict] = None,
        force_login: bool = False,
    ) -> TokenInfo:
        """生成访问令牌.

        只在JWT中存储user_id等不可变信息，用户名和角色等可变信息从数据库实时获取。
        默认实现单设备登录限制，如果用户已在其他设备登录，则拒绝新的登录请求。

        Args:
            user_id (str): 用户ID（不可变标识符）
            device_id (None | str, optional): 设备ID. Defaults to None，会自动生成.
            store_in_redis (bool, optional): 是否存储到Redis. Defaults to True.
            device_info (Optional[dict], optional): 设备信息(IP、UserAgent等). Defaults to None.
            force_login (bool, optional): 是否强制登录（踢掉其他设备）. Defaults to False.

        Returns:
            TokenInfo: 包含访问令牌和相关信息的对象

        Raises:
            HTTPException: 用户已在其他设备登录且force_login=False时抛出409异常
            Exception: Redis操作异常时可能抛出异常
        """
        # 生成设备ID（如果未提供）
        if not device_id:
            device_id = hashlib.md5(
                f"{user_id}_{int(time.time())}".encode()
            ).hexdigest()

        # TODO: 开发阶段为了方便测试，允许一个账号的多设备登录

        # 检查单设备登录限制
        if store_in_redis and self.redis_client:
            existing_session: Optional[dict] = await self.redis_client.hgetall(  # type: ignore
                f"user_token:{user_id}"
            )
            if existing_session:
                return TokenInfo(
                    access_token=existing_session["access_token"],
                    expires_in=base_configs.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
                )
                # existing_device_id = existing_session.get("device_id", "")
                # # 如果是同一设备，允许重新登录（刷新token）
                # if existing_device_id == device_id:
                #     pass  # 同设备重新登录，继续执行
                # elif not force_login:
                #     # 不同设备且不强制登录，拒绝登录
                #     existing_login_ip = existing_session.get("login_ip", "")
                #     existing_created_at = existing_session.get("created_at", "")

                #     raise HTTPException(
                #         status_code=status.HTTP_409_CONFLICT,
                #         detail="User already logged in on another device",
                #         headers={
                #             "X-Existing-Device": existing_device_id,
                #             "X-Existing-IP": existing_login_ip,
                #             "X-Existing-Login-Time": existing_created_at,
                #         },
                #     )
                # # 如果force_login=True，会继续执行，覆盖现有session

        # 计算时间戳
        now = time_now()
        expires_in = base_configs.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        exp_timestamp = int(
            (
                now + timedelta(minutes=base_configs.ACCESS_TOKEN_EXPIRE_MINUTES)
            ).timestamp()
        )
        iat_timestamp = int(now.timestamp())

        # 构建payload - 只包含不可变信息
        payload: dict[str, Any] = {
            "user_id": user_id,
            "device_id": device_id,
            "exp": exp_timestamp,
            "iat": iat_timestamp,
        }

        # 生成token
        access_token: str = jwt.encode(
            payload, self.secret_key, algorithm=self.algorithm
        )

        token_info: TokenInfo = TokenInfo(
            access_token=access_token, expires_in=expires_in
        )

        # 将token存储到Redis
        if store_in_redis and self.redis_client:
            # 准备新的token数据
            token_data: dict[str, Any] = {
                "access_token": access_token,
                # "device_id": device_id, # TODO: 设备ID暂时不存储到Redis，可以多设备同时登录
                "user_id": user_id,
                "created_at": now.isoformat(),
                "last_activity": now.isoformat(),
                "login_ip": device_info.get("ip", "") if device_info else "",
                "user_agent": device_info.get("user_agent", "") if device_info else "",
            }

            # 使用pipeline确保原子性操作
            async with self.redis_client.pipeline() as pipe:
                pipe.hset(f"user_token:{user_id}", mapping=token_data)
                pipe.expire(f"user_token:{user_id}", expires_in)
                await pipe.execute()

        return token_info

    async def verify_token(self, token: str, check_redis: bool = True) -> UserClaims:
        """验证token.

        验证JWT token的有效性，可选择是否检查Redis中的会话信息以确保单设备登录限制。

        Args:
            token (str): 需要验证的JWT token
            check_redis (bool, optional): 是否检查Redis会话. Defaults to True.

        Returns:
            UserClaims: 解析后的用户声明信息

        Raises:
            HTTPException: 当token无效、过期或不匹配时抛出401异常
        """
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            claims = UserClaims(**payload)  # type: ignore

        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired"
            )
        except jwt.InvalidTokenError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
            )

        # 检查Redis中存储的token是否匹配（单设备登录验证）
        if check_redis and self.redis_client:
            stored_token_data = await self.redis_client.hgetall(  # type: ignore
                f"user_token:{claims.user_id}"
            )

            if not stored_token_data:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Session not found, please login again",
                )

            # 检查当前token是否与存储的token匹配
            stored_access_token = stored_token_data.get("access_token", "")

            if token != stored_access_token:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Your account has been logged in from another device",
                    headers={"X-Logout-Reason": "token_mismatch"},
                )

            # 更新最后活动时间
            await self.redis_client.hset(  # type: ignore
                f"user_token:{claims.user_id}", "last_activity", time_now().isoformat()
            )

        return claims

    async def logout_user(self, user_id: str) -> bool:
        """用户登出（删除Redis中的token记录）.

        删除用户在Redis中的token记录，实现登出功能。

        Args:
            user_id (str): 用户ID

        Returns:
            bool: 操作成功返回True，失败返回False
        """
        if self.redis_client:
            result = await self.redis_client.delete(f"user_token:{user_id}")
            return result > 0
        return False

    async def force_logout_all_devices(self, user_id: str) -> bool:
        """强制用户所有设备下线.

        清除用户的所有会话信息，强制所有设备重新登录。

        Args:
            user_id (str): 用户ID

        Returns:
            bool: 操作成功返回True，失败返回False
        """
        if not self.redis_client:
            return False

        # 删除用户token记录
        result = await self.redis_client.delete(f"user_token:{user_id}")
        return result > 0

    async def get_online_users(self) -> list[dict[str, Any]]:
        """获取在线用户列表.

        扫描Redis中的所有用户token记录，返回当前在线用户的基础会话信息。

        Returns:
            list[dict[str, Any]]: 在线用户会话信息列表
        """
        if not self.redis_client:
            return []

        online_users = []
        pattern = "user_token:*"

        async for key in self.redis_client.scan_iter(match=pattern):
            user_id = key.replace("user_token:", "")
            token_data: dict = await self.redis_client.hgetall(key)  # type: ignore

            if token_data:
                online_users.append(
                    {
                        "user_id": user_id,
                        "device_id": token_data.get("device_id", ""),
                        "created_at": token_data.get("created_at", ""),
                        "last_activity": token_data.get("last_activity", ""),
                        "login_ip": token_data.get("login_ip", ""),
                        "user_agent": token_data.get("user_agent", ""),
                    }
                )

        return online_users

    async def is_user_online(self, user_id: str) -> bool:
        """检查用户是否在线.

        检查指定用户是否在Redis中有活跃的会话。

        Args:
            user_id (str): 用户ID

        Returns:
            bool: 用户在线返回True，否则返回False
        """
        if self.redis_client:
            return await self.redis_client.exists(f"user_token:{user_id}")
        return False

    async def get_user_session_info(self, user_id: str) -> Optional[dict[str, Any]]:
        """获取用户会话信息.

        获取指定用户的详细会话信息，不包含用户名和角色等可变信息。

        Args:
            user_id (str): 用户ID

        Returns:
            Optional[dict[str, Any]]: 用户会话信息，如果用户不在线则返回None
        """
        if not self.redis_client:
            return None

        token_data: Optional[dict] = await self.redis_client.hgetall(  # type: ignore
            f"user_token:{user_id}"
        )
        if not token_data:
            return None

        return {
            "user_id": user_id,
            "device_id": token_data.get("device_id", ""),
            "created_at": token_data.get("created_at", ""),
            "last_activity": token_data.get("last_activity", ""),
            "expires_in": token_data.get("expires_in", "0"),
            "login_ip": token_data.get("login_ip", ""),
            "user_agent": token_data.get("user_agent", ""),
        }

    async def cleanup_expired_sessions(self) -> int:
        """清理过期的会话.

        扫描并清理Redis中过期或无效的用户会话，可以设置为定时任务。

        Returns:
            int: 清理的会话数量
        """
        if not self.redis_client:
            return 0

        cleaned_count = 0
        pattern = "user_token:*"

        async for key in self.redis_client.scan_iter(match=pattern):
            ttl = await self.redis_client.ttl(key)
            if ttl == -1:  # 没有过期时间设置
                await self.redis_client.expire(
                    key, base_configs.ACCESS_TOKEN_EXPIRE_MINUTES * 60
                )
            elif ttl == -2:  # key不存在
                cleaned_count += 1

        return cleaned_count

    async def batch_logout_users(self, user_ids: list[str]) -> dict[str, bool]:
        """批量登出用户.

        批量删除多个用户的token记录。

        Args:
            user_ids (list[str]): 用户ID列表

        Returns:
            dict[str, bool]: 每个用户ID对应的操作结果
        """
        results = {}
        for user_id in user_ids:
            results[user_id] = await self.logout_user(user_id)
        return results

    async def get_online_users_count(self) -> int:
        """获取在线用户数量.

        统计当前在线用户的数量，比get_online_users()更高效。

        Returns:
            int: 在线用户数量
        """
        if not self.redis_client:
            return 0

        count = 0
        pattern = "user_token:*"
        async for _ in self.redis_client.scan_iter(match=pattern):
            count += 1
        return count

    async def refresh_user_activity(self, user_id: str) -> bool:
        """刷新用户活动时间.

        更新用户的最后活动时间，用于保持会话活跃。

        Args:
            user_id (str): 用户ID

        Returns:
            bool: 操作成功返回True，失败返回False
        """
        if not self.redis_client:
            return False

        key = f"user_token:{user_id}"
        if not await self.redis_client.exists(key):
            return False

        await self.redis_client.hset(key, "last_activity", time_now().isoformat())  # type: ignore

        return True

    async def get_user_token_info(self, user_id: str) -> None | str:
        """获取用户当前的访问令牌.

        获取指定用户当前有效的访问令牌。

        Args:
            user_id (str): 用户ID

        Returns:
            None | str: 用户的访问令牌，如果用户不在线则返回None
        """
        if not self.redis_client:
            return None

        token_data = await self.redis_client.hgetall(f"user_token:{user_id}")  # type: ignore
        if not token_data:
            return None

        return token_data.get("access_token", "")

    def decode_token_without_verify(self, token: str) -> Optional[dict[str, Any]]:
        """解码token但不验证（用于调试和日志记录）.

        解码JWT token获取载荷信息，但不验证签名和过期时间。
        主要用于调试、日志记录等场景。

        Args:
            token (str): JWT token

        Returns:
            Optional[dict[str, Any]]: token载荷信息，解码失败返回None
        """
        try:
            return jwt.decode(
                token, options={"verify_signature": False, "verify_exp": False}
            )
        except Exception:
            return None


# 全局JWT管理器实例
jwt_manager = JWTManager(base_configs.SECRET_KEY, base_configs.ALGORITHM)

# HTTP Bearer token 解析器
security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> UserClaims:
    """获取当前用户（FastAPI依赖项）.

    FastAPI依赖项，用于在路由处理函数中获取当前认证用户的基础信息。
    会自动从请求头中提取Bearer token并验证。

    Args:
        credentials: HTTP Bearer凭证，自动从Authorization头中提取

    Returns:
        UserClaims: 当前用户的JWT声明信息（只包含user_id等不可变信息）

    Raises:
        HTTPException: 当token无效时抛出401异常

    Note:
        用户名、角色等可变信息需要通过user_id从数据库实时查询
    """
    token = credentials.credentials
    user_claims = await jwt_manager.verify_token(token)

    # 刷新用户活动时间
    await jwt_manager.refresh_user_activity(user_claims.user_id)
    return user_claims


get_current_user_dependency = Depends(get_current_user)
