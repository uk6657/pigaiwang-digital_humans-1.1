"""基于 Redis 的 Worker ID 分配器。

用于雪花ID生成器的 worker_id 分配，支持自动续期。

Example:
    基本使用::

        allocator = WorkerIdAllocator(redis_client)
        try:
            worker_id = await allocator.acquire()
            print(f"获取到 worker_id: {worker_id}")
        finally:
            await allocator.release()
"""

import asyncio
from typing import Optional

import redis.asyncio as redis

from app.core.redis_ import redis_client


class WorkerIdAllocator:
    """Worker ID 分配器。

    从 Redis 获取 1-1023 范围内的唯一 worker_id，支持自动续期和优雅退出。

    Attributes:
        redis_url: Redis 连接地址。
        key_prefix: Redis key 前缀。
        ttl_seconds: key 过期时间（秒）。
        renew_interval: 续期间隔（秒）。
        min_id: 最小 worker_id。
        max_id: 最大 worker_id。

    Example:
        手动管理生命周期::

            allocator = WorkerIdAllocator(redis_client)
            try:
                worker_id = await allocator.acquire()
                # 使用 worker_id
            finally:
                await allocator.release()
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        key_prefix: str = "snowflake:worker_id:",
        ttl_seconds: int = 7200,
        renew_interval: int = 1800,
        min_id: int = 1,
        max_id: int = 1023,
    ) -> None:
        """初始化 Worker ID 分配器。

        Args:
            redis_client: Redis 客户端实例。
            key_prefix: Redis key 前缀，默认为 "snowflake:worker_id:"。
            ttl_seconds: key 过期时间（秒），默认为 3600（1小时）。
            renew_interval: 续期间隔（秒），默认为 1800（30分钟，TTL的一半）。
            min_id: 最小 worker_id，默认为 1。
            max_id: 最大 worker_id，默认为 1023。
        """
        self.key_prefix = key_prefix
        self.ttl_seconds = ttl_seconds
        self.renew_interval = renew_interval
        self.min_id = min_id
        self.max_id = max_id

        self._redis: redis.Redis = redis_client
        self._worker_id: int = -1
        self._identifier: str = ""
        self._renew_task: asyncio.Task
        self._running = False

    @property
    def worker_id(self) -> int:
        """获取当前分配的 worker_id。

        Returns:
            当前分配的 worker_id，未分配时返回 None。
        """
        return self._worker_id

    def _get_key(self, worker_id: int) -> str:
        """生成 Redis key。

        Args:
            worker_id: worker ID。

        Returns:
            完整的 Redis key。
        """
        return f"{self.key_prefix}{worker_id}"

    async def _try_acquire(self, worker_id: int, identifier: str) -> bool:
        """尝试获取指定的 worker_id。

        使用 SET NX EX 命令保证原子性。

        Args:
            worker_id: 要获取的 worker ID。
            identifier: 当前 worker 的唯一标识。

        Returns:
            获取成功返回 True，否则返回 False。
        """
        key = self._get_key(worker_id)
        result = await self._redis.set(key, identifier, nx=True, ex=self.ttl_seconds)
        return result is True

    async def acquire(self, identifier: Optional[str] = None) -> int:
        """获取一个可用的 worker_id。

        遍历所有可能的 ID 并尝试获取，成功后启动自动续期任务。

        Args:
            identifier: 用于标识当前 worker 的唯一标识。
                默认使用 "{hostname}:{pid}:{object_id}" 格式。

        Returns:
            分配的 worker_id。

        Raises:
            RuntimeError: 所有 ID 都已被占用时抛出。
        """
        if self._worker_id != -1:
            return self._worker_id

        if identifier is None:
            import os
            import socket

            identifier = f"{socket.gethostname()}:{os.getpid()}:{id(self)}"

        self._identifier = identifier

        for worker_id in range(self.min_id, self.max_id + 1):
            if await self._try_acquire(worker_id, identifier):
                self._worker_id = worker_id
                self._running = True
                self._renew_task = asyncio.create_task(self._renew_loop())
                return worker_id

        raise RuntimeError(
            f"无法获取 worker_id，所有 ID ({self.min_id}-{self.max_id}) 都已被占用"
        )

    async def _renew_loop(self) -> None:
        """续期循环。

        在后台持续运行，按照 renew_interval 间隔执行续期操作。
        """
        while self._running:
            try:
                await asyncio.sleep(self.renew_interval)
                if self._running and self._worker_id is not None:
                    await self._renew()
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Worker ID 续期失败: {e}")

    async def _renew(self) -> bool:
        """续期当前 worker_id。

        使用 Lua 脚本保证原子性，只有当 key 的值仍是当前 identifier 时才续期。

        Returns:
            续期成功返回 True。

        Raises:
            RuntimeError: 当 ID 被其他进程占用时抛出。
        """
        if self._worker_id == -14:
            return False

        key = self._get_key(self._worker_id)

        lua_script = """
        if redis.call('GET', KEYS[1]) == ARGV[1] then
            redis.call('EXPIRE', KEYS[1], ARGV[2])
            return 1
        else
            return 0
        end
        """

        result = await self._redis.eval(
            lua_script, 1, key, self._identifier, self.ttl_seconds
        )  # type: ignore

        if result == 1:
            return True
        else:
            self._running = False
            raise RuntimeError(f"Worker ID {self._worker_id} 已被其他进程占用")

    async def release(self) -> None:
        """释放当前 worker_id。

        依次执行以下操作：
        1. 取消续期任务
        2. 从 Redis 删除 key（仅当值匹配时）
        """
        self._running = False

        if self._renew_task is not None:
            self._renew_task.cancel()
            try:
                await self._renew_task
            except asyncio.CancelledError:
                pass

        if self._worker_id != -1:
            key = self._get_key(self._worker_id)

            lua_script = """
            if redis.call('GET', KEYS[1]) == ARGV[1] then
                redis.call('DEL', KEYS[1])
                return 1
            else
                return 0
            end
            """

            await self._redis.eval(lua_script, 1, key, self._identifier)  # type: ignore
            self._worker_id = -1


worker_id_allocator = WorkerIdAllocator(redis_client)
