"""一个注册任务的示例，开发时请删除!!!"""

import asyncio
import os
from typing import TYPE_CHECKING

from app.storage import AsyncSessionLocal
from app.tasks.enums import TaskType
from app.tasks.exceptions import TaskCancelledError
from app.tasks.executor import worker_executor
from app.tasks.handler import register_handler
from app.tasks.logging import get_task_logger
from app.tasks.models import TaskRunning
from app.tasks.service import TaskService

if TYPE_CHECKING:
    from loguru import Logger


@register_handler(TaskType.TEST)
async def test_handler(task: TaskRunning, logger: "Logger") -> None:
    """测试处理器（示例）

    Args:
        task (TaskRunning): _description_
        logger (Logger): _description_
    """
    logger.info("开始执行任务")
    logger.info("等待20秒")
    await asyncio.sleep(20)
    async with AsyncSessionLocal() as session:
        service = TaskService(session)
        is_cancelling = await service.is_cancelling(
            task.id
        )  # 如果修改TaskRunning.is_cancelling字段则会取消任务
        if is_cancelling:
            raise TaskCancelledError("任务已取消")

    # 模拟使用进程池处理 CPU 密集型任务
    tasks = [
        worker_executor.run_in_mp_pool(worker_executor._process_pool, test_cpu, task.id)
        for i in range(5)
    ]
    results = await asyncio.gather(*tasks)
    print(results)

    logger.info("假装是io密集")
    logger.info("任务执行完毕")


def test_cpu(task_id: str):
    """测试 CPU 密集型任务"""
    logger: "Logger" = get_task_logger(task_id)
    logger.info(f"开始执行 CPU 密集型任务 {os.getpid()}")
    total = 0
    for i in range(10**5):
        total += i * i
    logger.info(f"计算结果为{total}")
    # raise Exception("测试异常")  # 注释掉此行可以模拟任务失败
    return total
