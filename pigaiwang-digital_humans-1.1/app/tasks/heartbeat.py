"""心跳管理器实现.

负责在任务执行期间定期刷新心跳。
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Callable

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.time_ import time_now

from .config import task_config
from .exceptions import LockLostError
from .lock import TaskLock
from .logging import logger
from .models import TaskRunning

if TYPE_CHECKING:
    from loguru import Logger


class HeartbeatManager:
    """心跳管理器.

    负责在任务执行期间定期刷新心跳，包括：
    1. 续期 Redis 锁（权威来源，保证执行权）
    2. 更新 TaskRunning 表的 heartbeat_at 字段

    心跳机制的作用：
    - 证明 Worker 还在正常工作
    - 防止任务被定时器误判为超时并重新提交
    - 发现锁丢失时及时通知任务停止

    Attributes:
        task_id: 任务 ID
        lock_token: 锁的 Token
        task_lock: TaskLock 实例
        db_session_factory: 数据库会话工厂函数
        task_logger: 任务专属 logger

    Example:
        >>> heartbeat = HeartbeatManager(
        ...     task_id="12345",
        ...     lock_token="worker-1:abc123",
        ...     task_lock=task_lock,
        ...     db_session_factory=get_db_session,
        ...     task_logger=get_task_logger("12345"),
        ... )
        >>> await heartbeat.start()
        >>> # ... 执行任务 ...
        >>> await heartbeat.stop()
    """

    def __init__(
        self,
        task_id: str,
        lock_token: str,
        task_lock: TaskLock,
        db_session_factory: Callable[[], AsyncSession],
        task_logger: Logger | None = None,
    ) -> None:
        """初始化心跳管理器.

        Args:
            task_id: 任务 ID
            lock_token: 获取锁时返回的 token
            task_lock: TaskLock 实例
            db_session_factory: 异步数据库会话工厂函数
            task_logger: 任务专属 logger，None 则使用全局 logger
        """
        self.task_id = task_id
        self.lock_token = lock_token
        self.task_lock = task_lock
        self.db_session_factory = db_session_factory
        self.task_logger = task_logger or logger

        self._heartbeat_task: asyncio.Task | None = None
        self._stopped = False
        self._lock_lost = False

    @property
    def is_lock_lost(self) -> bool:
        """锁是否已丢失.

        Returns:
            锁丢失返回 True
        """
        return self._lock_lost

    async def start(self) -> None:
        """启动心跳任务.

        创建一个后台 asyncio.Task 定期刷新心跳。
        """
        self._stopped = False
        self._lock_lost = False
        self._heartbeat_task = asyncio.create_task(
            self._heartbeat_loop(),
            name=f"heartbeat-{self.task_id}",
        )
        self.task_logger.debug(f"任务 {self.task_id} 心跳已启动")

    async def stop(self) -> None:
        """停止心跳任务.

        取消后台 Task 并等待其结束。
        """
        if self._stopped:
            return
        self._stopped = True

        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None

        self.task_logger.debug(f"任务 {self.task_id} 心跳已停止")

    async def _heartbeat_loop(self) -> None:
        """心跳循环.

        每隔固定间隔执行一次心跳刷新：
        1. 先续 Redis 锁（失败则抛出 LockLostError）
        2. 再更新 TaskRunning 表的 heartbeat_at，同时检测任务是否还存在
        """
        interval = task_config.HEARTBEAT_INTERVAL

        while not self._stopped:
            try:
                # 等待一个心跳间隔
                await asyncio.sleep(interval)

                if self._stopped:
                    break

                # 1. 先续 Redis 锁（权威来源）
                renewed = await self.task_lock.renew(self.task_id, self.lock_token)
                if not renewed:
                    self._lock_lost = True
                    self.task_logger.warning(
                        f"任务 {self.task_id} Redis 锁续期失败，锁已丢失"
                    )
                    raise LockLostError(task_id=self.task_id)

                # 2. 更新数据库心跳，同时检测任务是否还存在
                task_exists = await self._update_db_heartbeat()
                if not task_exists:
                    self.task_logger.info(
                        f"任务 {self.task_id} 已不在 running 表中，停止心跳"
                    )
                    self._stopped = True
                    break

                self.task_logger.debug(f"任务 {self.task_id} 心跳刷新成功")

            except LockLostError:
                # 锁丢失，向上抛出让任务处理
                raise

            except asyncio.CancelledError:
                # 任务被取消，正常退出
                break

            except Exception as e:
                # 其他异常（如数据库错误），记录日志但继续心跳
                self.task_logger.warning(f"任务 {self.task_id} 心跳更新失败: {e}")

    async def _update_db_heartbeat(self) -> bool:
        """更新 TaskRunning 表的心跳时间.

        Returns:
            更新成功返回 True，任务不存在返回 False
        """
        async with self.db_session_factory() as session:
            result = await session.execute(
                update(TaskRunning)
                .where(TaskRunning.id == self.task_id)
                .values(heartbeat_at=time_now())
            )
            await session.commit()
            # 检查是否有行被更新，rowcount == 0 表示任务已不存在
            return result.rowcount > 0

    async def check_lock(self) -> bool:
        """主动检查锁是否还持有.

        用于在关键操作前验证锁状态。

        Returns:
            锁仍然有效返回 True
        """
        if self._lock_lost:
            return False

        # 获取当前锁的持有者
        holder = await self.task_lock.get_lock_holder(self.task_id)
        if holder != self.lock_token:
            self._lock_lost = True
            return False

        return True
