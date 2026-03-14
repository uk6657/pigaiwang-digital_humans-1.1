"""任务队列模块 - 分表设计.

采用按状态分表的设计：
- TaskPending: 待执行任务（热数据，小表）
- TaskRunning: 执行中任务（热数据，小表）
- TaskCompleted: 已完成任务（冷数据，大表，只插入只查询）
- TaskFailed: 失败任务（小表，用于排查问题）

优势：
- 热冷数据分离，running/pending 表始终保持很小
- completed 表无更新操作，可按时间分区
- 不需要 status 索引，表本身就代表状态

Example:
    初始化日志::

        from app.tasks import setup_task_logger
        setup_task_logger(log_dir="/var/log/myapp/tasks")

    创建任务::

        from app.tasks import TaskService, TaskType
        service = TaskService(db)
        task = await service.create_task(
            task_type=TaskType.PLAGIARISM_CHECK,
            related_id="12345",
            creator_id="1",
        )

    注册任务处理器::

        from app.tasks import register_handler, TaskType

        @register_handler(TaskType.PLAGIARISM_CHECK)
        async def handle_check(task, detail, is_resume, check_cancelled, task_logger):
            task_logger.info(f"处理任务: {task.id}")
            # 业务逻辑...
"""

from __future__ import annotations

import app.tasks.broker_tasks  # noqa: F401
import app.tasks.handlers  # noqa: F401

from .broker import broker
from .config import TaskQueueConfig, task_config
from .enums import FailReason, TaskTable, TaskType
from .exceptions import (
    LockAcquireError,
    LockLostError,
    TaskCancelledError,
    TaskException,
    TaskNotFoundError,
    TaskRetryExhaustedError,
)
from .handler import get_task_handler, register_handler
from .heartbeat import HeartbeatManager
from .lock import TaskLock
from .logging import (
    get_task_logger,
    logger,
    remove_task_logger,
    setup_task_logger,
)
from .models import (
    AnyTask,
    TaskCompleted,
    TaskFailed,
    TaskMixin,
    TaskPending,
    TaskRunning,
)
from .schedule import scheduler as taskiq_scheduler
from .scheduler import (
    scan_and_submit_task,
    trigger_scan,
)
from .service import TaskService
from .worker import execute_task, submit_task

__all__ = [
    # 配置
    "TaskQueueConfig",
    "task_config",
    # 枚举
    "TaskType",
    "TaskTable",
    "FailReason",
    # 模型
    "TaskMixin",
    "TaskPending",
    "TaskRunning",
    "TaskCompleted",
    "TaskFailed",
    "AnyTask",
    # 异常
    "TaskException",
    "LockAcquireError",
    "LockLostError",
    "TaskCancelledError",
    "TaskNotFoundError",
    "TaskRetryExhaustedError",
    # 锁
    "TaskLock",
    # 心跳
    "HeartbeatManager",
    # 任务注册
    "register_handler",
    "get_task_handler",
    # 服务
    "TaskService",
    # Worker
    "broker",
    "execute_task",
    "submit_task",
    # 调度器
    "scan_and_submit_task",
    "trigger_scan",
    "taskiq_scheduler",
    # 日志
    "logger",
    "setup_task_logger",
    "get_task_logger",
    "remove_task_logger",
]
