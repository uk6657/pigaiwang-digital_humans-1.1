"""TaskIQ Worker 任务执行器 - 分表版.

定义任务执行入口和相关工具函数。
"""

from typing import TYPE_CHECKING, Any, TypeVar

from app.core.redis_ import redis_client
from app.storage import AsyncSessionLocal

from .broker import broker
from .config import task_config
from .enums import FailReason, TaskType
from .exceptions import LockLostError, TaskCancelledError
from .handler import get_task_handler
from .heartbeat import HeartbeatManager
from .lock import TaskLock
from .logging import get_task_logger, logger, remove_task_logger
from .models import TaskRunning
from .service import TaskService

if TYPE_CHECKING:
    from loguru import Logger

# 类型变量，用于泛型函数
T = TypeVar("T")

# ==================== TaskIQ 任务定义 ====================


@broker.task
async def execute_task(
    task_id: str,
    is_resume: bool = False,
) -> dict[str, Any]:
    """任务执行入口.

    这是 TaskIQ 接收到任务后的入口函数。
    负责获取锁、移动表状态、执行业务逻辑、处理异常。

    Args:
        task_id: 任务 ID
        is_resume: 是否是恢复执行（心跳超时后重新执行）

    Returns:
        执行结果字典，包含 status 和其他信息
    """
    # 获取任务专属 logger
    task_logger = get_task_logger(task_id)
    task_logger.info(
        f"Worker {task_config.WORKER_ID} 收到任务 {task_id}，恢复执行: {is_resume}"
    )

    # 创建 TaskLock
    task_lock = TaskLock(redis_client, task_config.WORKER_ID)

    # 1. 尝试获取分布式锁
    lock_token = await task_lock.acquire(task_id)
    if not lock_token:
        task_logger.info(f"任务 {task_id} 锁已存在，跳过执行")
        remove_task_logger(task_id)
        return {"status": "skipped", "reason": "lock_exists"}

    heartbeat_manager: HeartbeatManager

    try:
        async with AsyncSessionLocal() as db:
            service = TaskService(db)

            # 2. 移动任务到 TaskRunning 表
            running_task: TaskRunning | None = await service.start_task(
                task_id=task_id,
                worker_id=task_config.WORKER_ID,
                is_resume=is_resume,
            )

            if not running_task:
                task_logger.info(f"任务 {task_id} 不存在或状态不符，跳过执行")
                await task_lock.release(task_id, lock_token)
                remove_task_logger(task_id)
                return {"status": "skipped", "reason": "task_not_found"}
            await db.commit()
            await db.refresh(running_task)

        # 3. 启动心跳
        heartbeat_manager = HeartbeatManager(
            task_id=task_id,
            lock_token=lock_token,
            task_lock=task_lock,
            db_session_factory=AsyncSessionLocal,
            task_logger=task_logger,
        )
        await heartbeat_manager.start()

        # 4. 执行业务逻辑
        await _execute_task_logic(running_task, task_logger)

        # 5. 移动到 TaskCompleted 表
        async with AsyncSessionLocal() as db:
            service = TaskService(db)
            await service.complete_task(task_id)
            await db.commit()

        task_logger.info(f"任务 {task_id} 执行完成")
        return {"status": "completed"}

    except LockLostError:
        task_logger.warning(f"任务 {task_id} 锁丢失，停止执行")
        return {"status": "aborted", "reason": "lock_lost"}

    except TaskCancelledError:
        task_logger.info(f"任务 {task_id} 已取消")
        # 移动到 TaskFailed 表
        async with AsyncSessionLocal() as db:
            service = TaskService(db)
            await service.cancel_running_task(task_id)
            await db.commit()
        return {"status": "cancelled"}

    except Exception as e:
        task_logger.exception(f"任务 {task_id} 执行失败: {e}")

        # 移动到 TaskFailed 或 TaskPending（重试）
        async with AsyncSessionLocal() as db:
            service = TaskService(db)
            await service.fail_task(task_id, str(e), FailReason.ERROR)
            await db.commit()

        return {"status": "failed", "error": str(e)}

    finally:
        # 6. 停止心跳
        if heartbeat_manager:
            await heartbeat_manager.stop()

        # 7. 释放锁
        await task_lock.release(task_id, lock_token)

        # 8. 清理任务 logger
        remove_task_logger(task_id)


async def _execute_task_logic(
    task: TaskRunning,
    task_logger: "Logger",
) -> None:
    """执行具体的业务逻辑.

    根据任务类型调用对应的处理器。

    Args:
        task: TaskRunning 对象
        task_logger: 任务专属 logger

    Raises:
        TaskCancelledError: 任务被取消
        ValueError: 未找到对应的任务处理器
        Exception: 业务逻辑执行异常
    """
    task_type = TaskType(task.task_type)
    handler = get_task_handler(task_type)

    if handler is None:
        raise ValueError(f"未找到任务类型 {task_type} 的处理器")

    await handler(task, task_logger)


# ==================== 辅助函数 ====================


async def submit_task(task_id: str | int, is_resume: bool = False) -> None:
    """提交任务到 TaskIQ.

    Args:
        task_id: 任务 ID
        is_resume: 是否是恢复执行
    """
    await execute_task.kiq(str(task_id), is_resume)
    logger.info(f"任务 {task_id} 已提交到队列，恢复执行: {is_resume}")
