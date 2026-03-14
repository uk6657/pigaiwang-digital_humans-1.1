"""Redis 分布式锁实现.

使用 Redis 实现分布式锁，保证同一时刻只有一个 Worker 执行某个任务。
"""

from __future__ import annotations

import uuid

from redis.asyncio import Redis

from .config import task_config
from .logging import logger


class TaskLock:
    """任务分布式锁.

    使用 Redis 实现的分布式锁，用于保证同一时刻只有一个 Worker 执行某个任务。

    锁的生命周期::

        1. acquire: 尝试获取锁（SETNX + EXPIRE 原子操作）
        2. renew: 定期续期（验证 token 后 EXPIRE）
        3. release: 释放锁（验证 token 后 DEL）

    Attributes:
        redis: Redis 异步客户端
        worker_id: 当前 Worker 的唯一标识

    Example:
        >>> lock = TaskLock(redis_client, "worker-1")
        >>> token = await lock.acquire(task_id=12345)
        >>> if token:
        ...     # 获取成功，执行任务
        ...     await lock.renew(task_id=12345, lock_token=token)
        ...     await lock.release(task_id=12345, lock_token=token)
    """

    # Lua 脚本：验证 token 并续期
    _RENEW_SCRIPT: str = """
    if redis.call("GET", KEYS[1]) == ARGV[1] then
        redis.call("EXPIRE", KEYS[1], ARGV[2])
        return 1
    else
        return 0
    end
    """

    # Lua 脚本：验证 token 并删除
    _RELEASE_SCRIPT: str = """
    if redis.call("GET", KEYS[1]) == ARGV[1] then
        redis.call("DEL", KEYS[1])
        return 1
    else
        return 0
    end
    """

    def __init__(self, redis: Redis, worker_id: str) -> None:
        """初始化任务锁.

        Args:
            redis: Redis 异步客户端
            worker_id: 当前 Worker 的唯一标识
        """
        self.redis = redis
        self.worker_id = worker_id
        self._lock_prefix = task_config.LOCK_KEY_PREFIX
        self._lock_expire = task_config.LOCK_EXPIRE_SECONDS

    def _get_lock_key(self, task_id: int | str) -> str:
        """生成锁的 Redis Key.

        Args:
            task_id: 任务 ID

        Returns:
            完整的 Redis Key
        """
        return f"{self._lock_prefix}{task_id}"

    def _generate_token(self) -> str:
        """生成锁的唯一 Token.

        Token 格式：{worker_id}:{uuid}
        用于标识锁的持有者，防止误操作其他 Worker 的锁。

        Returns:
            唯一的 Token 字符串
        """
        return f"{self.worker_id}:{uuid.uuid4().hex}"

    async def acquire(self, task_id: int | str) -> str | None:
        """尝试获取任务锁.

        使用 SET NX EX 原子操作，保证获取锁和设置过期时间的原子性。

        Args:
            task_id: 任务 ID

        Returns:
            成功返回 lock_token，失败返回 None
        """
        lock_key = self._get_lock_key(task_id)
        lock_token = self._generate_token()

        acquired = await self.redis.set(
            lock_key,
            lock_token,
            nx=True,  # 只在 key 不存在时设置
            ex=self._lock_expire,  # 设置过期时间
        )

        if acquired:
            logger.debug(f"任务 {task_id} 获取锁成功: {lock_token}")
        else:
            logger.debug(f"任务 {task_id} 获取锁失败，锁已存在")

        return lock_token if acquired else None

    async def renew(self, task_id: int | str, lock_token: str) -> bool:
        """续期锁.

        使用 Lua 脚本保证「验证 token」和「续期」的原子性。
        只有当 token 匹配时才会续期，防止误续其他 Worker 的锁。

        Args:
            task_id: 任务 ID
            lock_token: 获取锁时返回的 token

        Returns:
            续期成功返回 True，锁已丢失返回 False
        """
        lock_key = self._get_lock_key(task_id)

        result = await self.redis.eval(
            self._RENEW_SCRIPT,
            1,  # key 的数量
            lock_key,  # KEYS[1]
            lock_token,  # ARGV[1]
            self._lock_expire,  # ARGV[2]
        )

        success = result == 1
        if success:
            logger.debug(f"任务 {task_id} 续期锁成功")
        else:
            logger.warning(f"任务 {task_id} 续期锁失败，锁已丢失")

        return success

    async def release(self, task_id: int | str, lock_token: str) -> bool:
        """释放锁.

        使用 Lua 脚本保证「验证 token」和「删除」的原子性。
        只有当 token 匹配时才会删除，防止误删其他 Worker 的锁。

        Args:
            task_id: 任务 ID
            lock_token: 获取锁时返回的 token

        Returns:
            释放成功返回 True，锁已不属于自己返回 False
        """
        lock_key = self._get_lock_key(task_id)

        result = await self.redis.eval(
            self._RELEASE_SCRIPT,
            1,  # key 的数量
            lock_key,  # KEYS[1]
            lock_token,  # ARGV[1]
        )

        success = result == 1
        if success:
            logger.debug(f"任务 {task_id} 释放锁成功")
        else:
            logger.debug(f"任务 {task_id} 释放锁失败，锁已不属于自己")

        return success

    async def is_locked(self, task_id: int | str) -> bool:
        """检查任务是否被锁定.

        Args:
            task_id: 任务 ID

        Returns:
            是否被锁定
        """
        lock_key = self._get_lock_key(task_id)
        return await self.redis.exists(lock_key) > 0

    async def get_lock_holder(self, task_id: int | str) -> str | None:
        """获取锁的持有者信息.

        Args:
            task_id: 任务 ID

        Returns:
            锁的 token（包含 worker_id），不存在返回 None
        """
        lock_key = self._get_lock_key(task_id)
        token = await self.redis.get(lock_key)
        return token.decode() if token else None

    async def get_ttl(self, task_id: int | str) -> int:
        """获取锁的剩余过期时间.

        Args:
            task_id: 任务 ID

        Returns:
            剩余秒数，-1 表示永不过期，-2 表示不存在
        """
        lock_key = self._get_lock_key(task_id)
        return await self.redis.ttl(lock_key)
