"""验证服务模块.

提供各种验证功能的服务类，包括：
- 手机短信验证码发送和验证
- 密码加密和验证
- 图形验证码验证

所有验证方法都包含错误处理，确保系统稳定性。
使用Redis存储验证码，支持分布式部署场景。
"""

import bcrypt
from fastapi import status

from app.core import redis_client


class ValidationService:
    """验证服务类.

    提供各种验证功能，包括：
    - 手机短信验证码发送和验证
    - 密码加密和验证
    - 图形验证码验证

    所有验证方法都包含错误处理，确保系统稳定性.
    """

    def __init__(self):
        """初始化方法"""
        # bcrypt 默认 rounds=12 已经足够安全，生产环境可调到 13~15
        self.rounds = 12

    async def handle_phone_verification_code(
        self, phone: str
    ) -> tuple[bool, int, str, None]:
        """发送手机短信验证码.

        调用第三方服务向指定手机号发送短信验证码，
        并将验证码存储到Redis中，设置60秒有效期。

        Note:
            当前为模拟实现，直接返回成功
            实际应用中需要集成第三方短信服务
        """
        return True, status.HTTP_200_OK, "验证码发送成功", None

    async def validate_phone_verification_code(
        self, phone: str, verification_code: str = "1111"
    ) -> bool:
        """验证手机短信验证码.

        从Redis中获取存储的验证码并验证是否正确。
        验证码有效期为60秒，过期后自动删除。

        Note:
            当前为模拟实现，只验证是否等于"1111"
            实际应用中应该从Redis获取真实验证码进行对比
        """
        return "1111" == verification_code

    def get_hashed_password(self, plain_password: str) -> str:
        """生成密码哈希值.

        使用 bcrypt 算法对明文密码进行加密哈希.

        Args:
            plain_password: 明文密码

        Returns:
            str: 加密后的密码哈希值（utf-8 解码后的字符串）

        Note:
            - 自动生成随机盐值
            - 自动处理 bcrypt 的 72 字节限制（截断前 72 字节）
            - 返回的字符串可直接存入数据库
        """
        # bcrypt 只接受 bytes 类型
        password_bytes = plain_password.encode("utf-8")

        # 处理 72 字节限制（官方推荐做法）
        if len(password_bytes) > 72:
            password_bytes = password_bytes[:72]
            # 可选：记录日志
            # logger.warning(f"密码长度超过72字节，已截断（原长度: {len(plain_password.encode('utf-8'))}）")

        # 生成盐 + hash
        salt = bcrypt.gensalt(rounds=self.rounds)
        hashed = bcrypt.hashpw(password_bytes, salt)

        # 转回字符串存储到数据库
        return hashed.decode("utf-8")

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """验证密码.

        验证明文密码是否与存储的哈希值匹配.

        Args:
            plain_password: 待验证的明文密码
            hashed_password: 存储的密码哈希值（字符串）

        Returns:
            bool: 密码匹配返回 True，否则 False
        """
        # 转成 bytes
        plain_bytes = plain_password.encode("utf-8")
        hashed_bytes = hashed_password.encode("utf-8")

        try:
            return bcrypt.checkpw(plain_bytes, hashed_bytes)
        except Exception:
            # 任何异常（如格式不对）都视为不匹配
            return False

    async def verify_digit_code(
        self, code_image_id: str, image_code_input: str
    ) -> bool:
        """验证图形验证码.

        从Redis中获取存储的图形验证码并与用户输入进行比对。
        验证成功后自动删除Redis中的验证码。

        Note:
            - 验证码有时效性，过期会自动从Redis删除
            - 验证成功后立即删除，防止重复使用
            - 任何异常都返回False，确保系统稳定性
        """
        key = f"code_image:{code_image_id}"
        try:
            # 检查是否存在
            exists = await redis_client.exists(key)
            if not exists:
                return False

            # 获取值并对比
            stored_code = await redis_client.get(key)
            if stored_code == image_code_input:
                await redis_client.delete(key)
                return True
            return False
        except Exception:
            return False


# 单例实例
validation_service: ValidationService = ValidationService()
