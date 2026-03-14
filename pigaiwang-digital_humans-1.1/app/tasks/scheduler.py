"""定时扫描任务 - 基于 TaskIQ.

使用 TaskIQ 的定时任务功能，定期扫描需要重新提交的任务。

配置方式：
1. 在 TaskIQ 的 schedule 源中注册扫描任务
2. 启动 taskiq scheduler 进程
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from app.storage import AsyncSessionLocal

from .broker import broker
from .config import task_config
from .logging import logger
from .service import TaskService
from .worker import submit_task


@broker.task(
    task_name="task_queue:scan_and_submit",
    schedule=[
        {"interval": timedelta(seconds=task_config.SCAN_INTERVAL)}
    ],  # 按时间间隔执行
)
async def scan_and_submit_task() -> None:
    """扫描并提交需要执行的任务.

    这是一个 TaskIQ 定时任务，由 TaskIQ Scheduler 定期触发。
    负责扫描：
    1. 超时的 TaskPending 任务（首次提交失败的任务）
    2. 心跳超时的 TaskRunning 任务（Worker 异常中断的任务）

    Returns:
        扫描结果统计字典

    Example:
        在 schedule 源中配置::

            from taskiq import TaskiqScheduler
            from taskiq.schedule_sources import LabelScheduleSource

            scheduler = TaskiqScheduler(
                broker=broker,
                sources=[LabelScheduleSource(broker)],
            )

        或使用 Redis schedule source::

            from taskiq_redis import RedisScheduleSource

            scheduler = TaskiqScheduler(
                broker=broker,
                sources=[RedisScheduleSource(redis_url)],
            )
    """
    result: dict[str, Any] = {
        "running_count": 0,
        "pending_count": 0,
        "pending_submitted": 0,
        "timeout_submitted": 0,
        "errors": [],
    }

    pending_timeout = task_config.PENDING_TIMEOUT
    heartbeat_timeout = task_config.HEARTBEAT_TIMEOUT
    max_running_tasks = task_config.MAX_RUNNING_TASKS

    try:
        async with AsyncSessionLocal() as db:
            service = TaskService(db)

            # 1. 统计当前任务数
            result["running_count"] = await service.count_running_tasks()
            result["pending_count"] = await service.count_pending_tasks()

            # 2. 检查是否达到上限
            if result["running_count"] >= max_running_tasks:
                logger.debug(
                    f"运行中任务数 ({result['running_count']}) 已达上限 "
                    f"({max_running_tasks})，跳过本次扫描"
                )
                return

            available_slots = max_running_tasks - result["running_count"]

            # 3. 扫描超时的 TaskPending 任务
            pending_tasks = await service.get_timeout_pending_tasks(
                timeout_seconds=pending_timeout,
                limit=available_slots,
            )

            for task in pending_tasks:
                try:
                    await submit_task(task.id, is_resume=False)
                    result["pending_submitted"] += 1
                    logger.info(f"重新提交 pending 任务: {task.id}")
                except Exception as e:
                    error_msg = f"pending:{task.id}:{e}"
                    result["errors"].append(error_msg)
                    logger.error(f"提交 pending 任务失败: {error_msg}")

            # 4. 更新可用槽位
            available_slots -= len(pending_tasks)
            if available_slots <= 0:
                return

            # 5. 扫描心跳超时的 TaskRunning 任务
            timeout_tasks = await service.get_heartbeat_timeout_tasks(
                timeout_seconds=heartbeat_timeout,
                limit=available_slots,
            )

            for task in timeout_tasks:
                try:
                    await submit_task(task.id, is_resume=True)
                    result["timeout_submitted"] += 1
                    logger.info(f"重新提交心跳超时任务: {task.id}")
                except Exception as e:
                    error_msg = f"timeout:{task.id}:{e}"
                    result["errors"].append(error_msg)
                    logger.error(f"提交心跳超时任务失败: {error_msg}")

        logger.info(
            f"扫描完成: pending_submitted={result['pending_submitted']}, "
            f"timeout_submitted={result['timeout_submitted']}"
        )

    except Exception as e:
        logger.exception(f"扫描任务执行失败: {e}")
        result["errors"].append(f"scan_error:{e}")

    return


async def trigger_scan() -> None:
    """手动触发一次扫描.

    用于测试或手动干预。

    Example:
        >>> from task.scheduler import trigger_scan
        >>> await trigger_scan()
    """
    await scan_and_submit_task.kiq()
    logger.info("已触发扫描任务")


# ==================== 调度器配置示例 ====================
#
# 方式一：使用 LabelScheduleSource（在任务上添加 schedule label）
#
# 在 worker.py 或单独的 schedule.py 中：
#
# ```python
# from datetime import timedelta
# from taskiq import TaskiqScheduler
# from taskiq.schedule_sources import LabelScheduleSource
# from task.worker import broker
#
# # 给扫描任务添加调度标签
# scan_and_submit_task = scan_and_submit_task.with_labels(
#     schedule=[{"cron": "* * * * *"}]  # 每分钟执行一次
# )
#
# # 或者使用 timedelta
# scan_and_submit_task = scan_and_submit_task.with_labels(
#     schedule=[{"time": timedelta(seconds=60)}]  # 每60秒执行一次
# )
#
# scheduler = TaskiqScheduler(
#     broker=broker,
#     sources=[LabelScheduleSource(broker)],
# )
#
# # 启动命令: taskiq scheduler task.schedule:scheduler
# ```
#
# 方式二：使用 Redis Schedule Source（动态调度）
#
# ```python
# from taskiq import TaskiqScheduler
# from taskiq_redis import RedisScheduleSource
# from task.worker import broker
#
# schedule_source = RedisScheduleSource(
#     url="redis://localhost:6379/0",
# )
#
# scheduler = TaskiqScheduler(
#     broker=broker,
#     sources=[schedule_source],
# )
#
# # 动态添加调度任务
# await schedule_source.add_schedule(
#     task_name="task_queue:scan_and_submit",
#     cron="* * * * *",  # 每分钟
# )
# ```
#
# 启动调度器：
# ```bash
# taskiq scheduler task.schedule:scheduler
# ```
