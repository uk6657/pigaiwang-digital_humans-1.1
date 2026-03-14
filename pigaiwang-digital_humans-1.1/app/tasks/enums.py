"""任务相关枚举定义.

定义任务类型和失败原因的枚举。
由于采用分表设计，任务状态由表本身表示，不再需要 TaskStatus 枚举。
"""

from __future__ import annotations

from enum import IntEnum


class TaskType(IntEnum):
    """任务类型枚举.

    根据业务需求定义不同的任务类型。
    不同类型的任务会使用不同的处理器执行。

    Attributes:
        TEST: 测试任务(示例)
    """

    TEST = 1
    SCRIPT_CONTINUE_GENERATE = 2

    @property
    def display_name(self) -> str:
        """获取任务类型的中文显示名称.

        Returns:
            任务类型的中文名称
        """
        match self:
            case TaskType.TEST:
                return "测试任务(示例)"
            case TaskType.SCRIPT_CONTINUE_GENERATE:
                return "续写剧本任务"
            case _:
                return "未知类型"


class FailReason(IntEnum):
    """任务失败原因枚举.

    用于 TaskFailed 表中区分不同的失败类型。
    """

    ERROR = 1
    TIMEOUT = 2
    CANCELLED = 3

    @property
    def display_name(self) -> str:
        """获取失败原因的中文显示名称."""
        match self:
            case FailReason.ERROR:
                return "执行出错"
            case FailReason.TIMEOUT:
                return "执行超时"
            case FailReason.CANCELLED:
                return "用户取消"
            case _:
                return "未知原因"


class TaskTable(IntEnum):
    """任务表枚举.

    用于标识任务当前所在的表，便于 API 层返回统一的状态。
    """

    PENDING = 0
    RUNNING = 1
    COMPLETED = 2
    FAILED = 3

    @property
    def display_name(self) -> str:
        """获取状态的中文显示名称."""
        match self:
            case TaskTable.PENDING:
                return "待执行"
            case TaskTable.RUNNING:
                return "执行中"
            case TaskTable.COMPLETED:
                return "已完成"
            case TaskTable.FAILED:
                return "已失败"
            case _:
                return "未知状态"
