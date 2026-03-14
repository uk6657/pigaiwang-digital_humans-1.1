"""基于 Redis 的同步 Worker ID 分配器。

用于子进程（ProcessPoolExecutor）在 initializer 中获取 worker_id。

Example:
    直接使用::

        allocator = SyncWorkerIdAllocator(redis_url)
        worker_id = allocator.acquire()
        # ...
        allocator.release()

    作为进程池初始化函数::

        executor = ProcessPoolExecutor(
            max_workers=4,
            initializer=init_subprocess_worker,
            initargs=(redis_url,),
        )
"""

from __future__ import annotations

import atexit
import os
import socket
import threading

import redis


class SyncWorkerIdAllocator:
    """同步 Worker ID 分配器。

    从 Redis 获取 1-1023 范围内的唯一 worker_id，支持自动续期。
    用于子进程（ProcessPoolExecutor）的 initializer。

    Attributes:
        redis_url: Redis 连接地址。
        key_prefix: Redis key 前缀。
        ttl_seconds: key 过期时间（秒）。
        renew_interval: 续期间隔（秒）。
        min_id: 最小 worker_id。
        max_id: 最大 worker_id。
    """

    def __init__(
        self,
        redis_url: str,
        key_prefix: str = "snowflake:worker_id:",
        ttl_seconds: int = 7200,
        renew_interval: int = 1800,
        min_id: int = 1,
        max_id: int = 1023,
    ) -> None:
        """初始化同步 Worker ID 分配器。

        Args:
            redis_url: Redis 连接地址。
            key_prefix: Redis key 前缀，默认为 "snowflake:worker_id:"。
            ttl_seconds: key 过期时间（秒），默认为 3600（1小时）。
            renew_interval: 续期间隔（秒），默认为 1800（30分钟）。
            min_id: 最小 worker_id，默认为 1。
            max_id: 最大 worker_id，默认为 1023。
        """
        self._redis_url = redis_url
        self._key_prefix = key_prefix
        self._ttl_seconds = ttl_seconds
        self._renew_interval = renew_interval
        self._min_id = min_id
        self._max_id = max_id

        self._worker_id: int = -1
        self._identifier: str = ""
        self._running: bool = False
        self._renew_thread: threading.Thread | None = None

    @property
    def worker_id(self) -> int:
        """获取当前分配的 worker_id。

        Returns:
            当前分配的 worker_id，未分配时返回 -1。
        """
        return self._worker_id

    def _get_key(self, worker_id: int) -> str:
        """生成 Redis key。

        Args:
            worker_id: worker ID。

        Returns:
            完整的 Redis key。
        """
        return f"{self._key_prefix}{worker_id}"

    def _get_identifier(self) -> str:
        """生成唯一标识。

        Returns:
            格式为 "{hostname}:{pid}:{object_id}" 的唯一标识。
        """
        return f"{socket.gethostname()}:{os.getpid()}:{id(self)}"

    def _create_redis_client(self) -> redis.Redis:
        """创建同步 Redis 客户端。

        Returns:
            同步 Redis 客户端实例。
        """
        return redis.from_url(self._redis_url, decode_responses=True)

    def acquire(self) -> int:
        """获取一个可用的 worker_id。

        遍历所有可能的 ID 并尝试获取，成功后启动后台续期线程。

        Returns:
            分配的 worker_id。

        Raises:
            RuntimeError: 所有 ID 都已被占用时抛出。
        """
        if self._worker_id != -1:
            return self._worker_id

        self._identifier = self._get_identifier()

        r = self._create_redis_client()
        try:
            for worker_id in range(self._min_id, self._max_id + 1):
                key = self._get_key(worker_id)
                if r.set(key, self._identifier, nx=True, ex=self._ttl_seconds):
                    self._worker_id = worker_id
                    self._running = True
                    self._start_renew_thread()
                    atexit.register(self.release)
                    return worker_id

            raise RuntimeError(
                f"无法获取 worker_id，所有 ID ({self._min_id}-{self._max_id}) 都已被占用"
            )
        finally:
            r.close()

    def _start_renew_thread(self) -> None:
        """启动后台续期线程。"""

        def renew_loop() -> None:
            r = self._create_redis_client()
            lua_script = """
            if redis.call('GET', KEYS[1]) == ARGV[1] then
                redis.call('EXPIRE', KEYS[1], ARGV[2])
                return 1
            else
                return 0
            end
            """

            try:
                while self._running:
                    # 可中断的 sleep（每秒检查一次 _running 状态）
                    for _ in range(self._renew_interval):
                        if not self._running:
                            return
                        threading.Event().wait(1)

                    if not self._running or self._worker_id == -1:
                        return

                    try:
                        key = self._get_key(self._worker_id)
                        result = r.eval(
                            lua_script, 1, key, self._identifier, self._ttl_seconds
                        )
                        if result != 1:
                            print(
                                f"⚠️ [子进程 {os.getpid()}] "
                                f"Worker ID {self._worker_id} 续期失败"
                            )
                            self._running = False
                            return
                    except Exception as e:
                        print(f"⚠️ [子进程 {os.getpid()}] Worker ID 续期异常: {e}")
            finally:
                r.close()

        self._renew_thread = threading.Thread(target=renew_loop, daemon=True)
        self._renew_thread.start()

    def release(self) -> None:
        """释放当前 worker_id。

        依次执行以下操作：
        1. 停止续期线程
        2. 从 Redis 删除 key（仅当值匹配时）
        """
        if self._worker_id == -1:
            return

        self._running = False

        # 等待续期线程结束
        if self._renew_thread is not None and self._renew_thread.is_alive():
            self._renew_thread.join(timeout=2)
            self._renew_thread = None

        # 释放 worker_id
        r = self._create_redis_client()
        try:
            key = self._get_key(self._worker_id)
            lua_script = """
            if redis.call('GET', KEYS[1]) == ARGV[1] then
                redis.call('DEL', KEYS[1])
                return 1
            else
                return 0
            end
            """
            r.eval(lua_script, 1, key, self._identifier)
            print(f"✅ [子进程 {os.getpid()}] 已释放 worker_id: {self._worker_id}")
            self._worker_id = -1
        finally:
            r.close()


# ==========================================
# 子进程全局变量和初始化函数
# ==========================================

_subprocess_allocator: SyncWorkerIdAllocator | None = None


def init_subprocess_worker_id(redis_url: str, **kwargs: int | str) -> int:
    """子进程获取worker_id 的初始化函数。

    用于 ProcessPoolExecutor 的 initializer。

    Args:
        redis_url: Redis 连接地址。
        **kwargs: 传递给 SyncWorkerIdAllocator 的其他参数。

    Example:
        executor = ProcessPoolExecutor(
            max_workers=4,
            initializer=init_subprocess_worker_id,
            initargs=(redis_url,),
        )
    """
    global _subprocess_allocator

    _subprocess_allocator = SyncWorkerIdAllocator(redis_url, **kwargs)  # type: ignore
    worker_id = _subprocess_allocator.acquire()
    print(f"✅ [子进程 {os.getpid()}] 获取到 worker_id: {worker_id}")
    return worker_id


def get_subprocess_worker_id() -> int:
    """获取子进程的 worker_id。

    Returns:
        子进程的 worker_id。

    Raises:
        RuntimeError: 子进程未初始化时抛出。
    """
    if _subprocess_allocator is None:
        raise RuntimeError("子进程未初始化，请确保使用了 init_subprocess_worker")
    return _subprocess_allocator.worker_id
