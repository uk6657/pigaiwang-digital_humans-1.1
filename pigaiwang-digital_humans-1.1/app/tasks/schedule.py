"""TaskIQ 调度器配置.

配置定时扫描任务的调度策略。

启动调度器命令::

    taskiq scheduler app.tasks.schedule:scheduler

注意：需要同时启动 worker 进程::

    taskiq worker app.tasks.broker:broker
"""

from __future__ import annotations

from taskiq import TaskiqScheduler
from taskiq.schedule_sources import LabelScheduleSource

from .broker import broker

# ==================== 创建调度器实例 ====================

scheduler = TaskiqScheduler(
    broker=broker,
    sources=[LabelScheduleSource(broker)],
)
