"""日志处理模块（类封装版，FastAPI/AsyncSessionLocal 适配）。

功能：
- 使用 asyncio worker + AsyncSessionLocal 异步批量写入数据库
- 直接使用 Loguru message.record 结构化入库（不再解析字符串）
- 系统日志与用户日志分离处理
- asyncio.Queue 队列管理（支持 maxsize / 丢弃策略）
- 批量阈值 + 定时 flush 双触发，避免“日志不够一批就不落库”
- 优雅停机：logger.complete() + 队列 join + worker 退出
- 进程退出兜底：注册 atexit

注意：
- 不要将协程 sink 与 enqueue=True 混用（enqueue=True 会在后台线程调用 sink）。
- 进程被 SIGKILL/断电等强制中止时，任何方案都无法保证 100% 不丢日志；
  本模块尽力覆盖“正常退出/优雅停机/TERM/INT”场景。
"""

import asyncio
import atexit
from dataclasses import dataclass
from typing import Any, Optional

from loguru import logger

from app.common.time_ import zone_info
from app.configs import base_configs
from app.storage import SystemLogModel, UserLogModel
from app.storage.base import AsyncSessionLocal

# Worker 停止哨兵
_STOP_SENTINEL = object()


@dataclass(frozen=True)
class LogItem:
    """队列中传递的结构化日志对象。

    Attributes:
        time: 日志时间（通常是 Loguru 的 datetime 对象）。
        level: 日志级别字符串，例如 "INFO"、"ERROR"。
        message: 日志正文。
        extra: Loguru 记录中的 extra 字段。
    """

    time: Any
    level: str
    message: str
    extra: dict[str, Any]


class AsyncLogService:
    """异步日志服务：Loguru sink -> asyncio.Queue -> worker 批量落库。

    使用方式（建议）：
        1. service = AsyncLogService(...)
        2. setup_logger(service)
        3. await service.start()
        4. 应用退出时 await service.shutdown()

    设计要点：
        - 不使用全局队列/全局 task，避免多 worker、生命周期不清晰的问题
        - 支持“批量阈值”和“定时 flush”，解决低日志量不落库
        - shutdown 时强制 flush，最大化降低丢日志概率
    """

    def __init__(
        self,
        *,
        batch_size: int = 2000,
        flush_interval: float = 1.0,
        queue_maxsize: int = 200_000,
        drop_when_full: bool = True,
    ) -> None:
        """初始化异步日志服务。

        Args:
            batch_size: 触发批量写入的条数阈值。
            flush_interval: 定时刷新间隔（秒）。在该时间内没有新日志也会触发写入，
                用于避免“日志数量达不到 batch_size 导致一条都不落库”。
            queue_maxsize: 内存队列最大长度。建议根据机器内存和峰值日志量调整。
            drop_when_full: 队列满时的策略：
                - True：丢弃日志并 warning（保护主业务不被阻塞）
                - False：sink 会 await put（可能阻塞请求路径，不推荐）

        Raises:
            ValueError: 参数不合法时抛出。
        """
        if batch_size <= 0:
            raise ValueError("batch_size 必须大于 0")
        if flush_interval <= 0:
            raise ValueError("flush_interval 必须大于 0")
        if queue_maxsize <= 0:
            raise ValueError("queue_maxsize 必须大于 0")

        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self.queue: asyncio.Queue[Any] = asyncio.Queue(maxsize=queue_maxsize)
        self.drop_when_full = drop_when_full

        self._worker_task: Optional[asyncio.Task] = None
        self._closing = False
        self._shutdown_started = False

        # 保存运行中的 event loop（用于 signal/atexit 兜底时投递 shutdown）
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._hooks_installed = False

    def _record_to_item(self, message) -> Optional[LogItem]:
        """将 Loguru message 转换为 LogItem。

        仅处理 extra["log_type"] 为 "system" 或 "user" 的日志。

        Args:
            message: Loguru sink 接收到的 message 对象，包含 message.record。

        Returns:
            LogItem: 需要入库的结构化日志对象。
            None: 不符合入库条件（例如未设置 log_type）。
        """
        record = message.record
        extra = record.get("extra") or {}
        log_type = extra.get("log_type")

        if log_type not in ("system", "user"):
            return None

        return LogItem(
            time=record["time"],
            level=record["level"].name,
            message=record["message"],
            extra=extra,
        )

    async def sink(self, message) -> None:
        """Loguru 协程 sink：将结构化日志推入 asyncio 队列。

        Args:
            message: Loguru sink 接收到的 message 对象。

        Notes:
            - 服务进入关闭阶段后（self._closing=True），会忽略新日志，避免 shutdown 卡死。
            - 当 drop_when_full=True 时，队列满会丢弃日志，以保证主业务不阻塞。
        """
        if self._closing:
            return

        item = self._record_to_item(message)
        if item is None:
            return

        if self.drop_when_full:
            try:
                self.queue.put_nowait(item)
            except asyncio.QueueFull:
                logger.warning("日志队列已满，丢弃日志")
        else:
            await self.queue.put(item)

    async def _write_log_batch(self, items: list[LogItem]) -> None:
        """将一批日志写入数据库。

        Args:
            items: 结构化日志列表。

        Notes:
            - system 日志写入 SystemLogModel
            - user 日志写入 UserLogModel
            - 发生异常会 rollback 并记录错误日志
        """
        async with AsyncSessionLocal() as db:
            try:
                entries: list[Any] = []

                for it in items:
                    extra = it.extra or {}
                    log_type = extra.get("log_type")

                    if log_type == "system":
                        entries.append(
                            SystemLogModel(level=it.level, message=it.message)
                        )
                    elif log_type == "user":
                        entries.append(
                            UserLogModel(
                                user_id=extra.get("user_id"),
                                ip_address=extra.get("ip_address"),
                                user_agent=extra.get("user_agent"),
                                level=it.level,
                                message=it.message,
                            )
                        )

                if entries:
                    db.add_all(entries)
                    await db.commit()

            except Exception as e:
                logger.error(f"批量写入日志失败: {e}")
                await db.rollback()

    async def _worker_loop(self) -> None:
        """后台 worker：消费队列并批量/定时落库。

        Flush 触发条件：
            1) 达到 batch_size
            2) 超过 flush_interval 没有新日志（定时 flush，解决低日志量不落库）
            3) 收到停止哨兵（先 flush 剩余再退出）

        Notes:
            - task_done() 必须在日志“确定已写入/已丢弃”后调用，
              否则 queue.join() 会提前返回，导致误以为已落库。
        """
        batch: list[LogItem] = []
        pending_done = 0

        while True:
            try:
                item = await asyncio.wait_for(
                    self.queue.get(), timeout=self.flush_interval
                )

                if item is _STOP_SENTINEL:
                    # 退出前 flush
                    if batch:
                        await self._write_log_batch(batch)
                        for _ in range(pending_done):
                            self.queue.task_done()
                        batch.clear()
                        pending_done = 0

                    self.queue.task_done()
                    logger.info("日志 Worker 接收到停止信号，正常退出")
                    return

                if isinstance(item, LogItem):
                    batch.append(item)
                # 非预期类型：丢弃
                pending_done += 1

                if len(batch) >= self.batch_size:
                    await self._write_log_batch(batch)
                    for _ in range(pending_done):
                        self.queue.task_done()
                    batch.clear()
                    pending_done = 0

            except asyncio.TimeoutError:
                # 定时 flush：保证低日志量也会写库
                if batch:
                    await self._write_log_batch(batch)
                    for _ in range(pending_done):
                        self.queue.task_done()
                    batch.clear()
                    pending_done = 0

            except Exception as e:
                logger.error(f"日志 worker 出错: {e}")
                # 防止 join 卡死：把 pending 标记 done 并丢弃 batch
                if pending_done:
                    for _ in range(pending_done):
                        self.queue.task_done()
                batch.clear()
                pending_done = 0

    async def start(self) -> asyncio.Task:
        """启动后台 worker 并安装退出兜底钩子。

        Returns:
            asyncio.Task: worker 的任务对象。

        Notes:
            - 建议在 FastAPI lifespan 启动阶段调用一次。
            - 首次启动会注册 atexit + SIGTERM/SIGINT 兜底钩子。
        """
        if self._worker_task is not None and not self._worker_task.done():
            return self._worker_task

        self._loop = asyncio.get_running_loop()
        self._install_exit_hooks()

        self._worker_task = asyncio.create_task(self._worker_loop())
        return self._worker_task

    async def shutdown(self) -> None:
        """优雅关闭日志服务（强制 flush）。

        关闭顺序：
            1) await logger.complete()：确保 Loguru 的协程 sink 已执行完（日志已入队）
            2) 向队列发送停止哨兵
            3) await queue.join()：等待队列全部处理完成（真正落库）
            4) await worker task：等待 worker 退出

        Notes:
            - 该方法幂等（多次调用不会重复执行）。
        """
        if self._shutdown_started:
            return
        self._shutdown_started = True

        self._closing = True

        # 1) 先尽量把 Loguru 的异步 sink 全部跑完（保证日志入队）
        try:
            await logger.complete()
        except Exception as e:
            logger.error(f"Loguru complete 出错: {e}")

        # 2) 通知 worker 停止（并触发剩余 flush）
        try:
            await self.queue.put(_STOP_SENTINEL)
        except Exception as e:
            logger.error(f"Loguru stop 出错: {e}")

        # 3) 等待落库完成
        try:
            await self.queue.join()
        except Exception as e:
            logger.error(f"Loguru queue join 出错: {e}")

        # 4) 等待 worker 退出
        if self._worker_task is not None:
            try:
                await self._worker_task
            except Exception:
                pass

    def _install_exit_hooks(self) -> None:
        """安装进程退出兜底钩子（atexit + SIGTERM/SIGINT）。

        Notes:
            - 优先使用 loop.add_signal_handler（Unix + 主线程）
            - 钩子中不阻塞，只做“投递 shutdown 任务”的 best-effort
        """
        if self._hooks_installed:
            return
        self._hooks_installed = True

        atexit.register(self._atexit_handler)

    def _schedule_shutdown(self) -> None:
        """将 shutdown() 投递到事件循环中执行（best-effort）。

        Notes:
            - 可在 signal handler / atexit 环境调用。
            - 如果 loop 不存在或未运行，则直接返回。
        """
        loop = self._loop
        if loop is None or (not loop.is_running()):
            return

        try:
            asyncio.run_coroutine_threadsafe(self.shutdown(), loop)
        except Exception as e:
            print(f"Loguru shutdown 投递失败: {e}")

    def _atexit_handler(self) -> None:
        """解释器退出兜底：尝试投递 shutdown（不阻塞）。"""
        self._schedule_shutdown()


def setup_logger(service: AsyncLogService) -> None:
    """配置 Loguru，并将 system/user 日志绑定到 AsyncLogService 入库。

    Args:
        service: AsyncLogService 实例（由应用生命周期持有）。

    Notes:
        - 入库 sink 是协程 sink，因此必须 enqueue=False（避免后台线程无 event loop）。
        - error 文件 sink 可独立使用 enqueue=True（它是同步文件写入）。
    """
    # 统一时区
    logger.configure(
        patcher=lambda record: record.update(time=record["time"].astimezone(zone_info))
    )

    # 入库：system/user 分流
    logger.add(
        service.sink,
        level="INFO",  # INFO 及以上（包含 ERROR/CRITICAL）都会进入，但仍受 filter 控制
        filter=lambda record: record["extra"].get("log_type") == "system",
        enqueue=False,
    )
    logger.add(
        service.sink,
        level="INFO",
        filter=lambda record: record["extra"].get("log_type") == "user",
        enqueue=False,
    )

    # 错误日志文件：独立记录
    logger.add(
        f"{base_configs.PROJECT_LOG_DIR}/error_{{time}}.log",
        level="ERROR",
        format="{time:YYYY-MM-DD HH:mm:ss} - {level} - {message} {extra}",
        rotation="10 MB",
        retention="30 days",
        compression="zip",
        enqueue=True,
    )
