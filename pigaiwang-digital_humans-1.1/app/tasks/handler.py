"""任务处理器注册模块."""

import inspect
from typing import TYPE_CHECKING, Any, Callable, Coroutine

from .enums import TaskType
from .logging import logger

if TYPE_CHECKING:
    from loguru import Logger

    from .models import TaskRunning

# 定义异步处理器的类型别名
AsyncTaskHandler = Callable[["TaskRunning", "Logger"], Coroutine[Any, Any, Any]]

_task_handlers: dict[TaskType, AsyncTaskHandler] = {}


def register_handler(
    task_type: TaskType,
) -> Callable[[AsyncTaskHandler], AsyncTaskHandler]:
    """注册任务处理器装饰器.

    Args:
        task_type: 任务类型

    Returns:
        装饰器函数

    Raises:
        TypeError: 如果处理器不是异步函数

    Example:
        >>> @register_handler(TaskType.PLAGIARISM_CHECK)
        ... async def handle_plagiarism_check(task: TaskRunning, task_logger: Logger):
        ...     # 执行查重逻辑
        ...     pass
    """

    def decorator(func: AsyncTaskHandler) -> AsyncTaskHandler:
        # 运行时检查：确保是异步函数
        if not inspect.iscoroutinefunction(func):
            raise TypeError(
                f"任务处理器必须是异步函数 (async def)，"
                f"但 '{func.__name__}' 不是异步函数"
            )

        _task_handlers[task_type] = func
        logger.info(f"注册任务处理器: {task_type.display_name} -> {func.__name__}")
        return func

    return decorator


def get_task_handler(task_type: TaskType) -> AsyncTaskHandler | None:
    """获取任务处理器.

    Args:
        task_type: 任务类型

    Returns:
        异步处理器函数，不存在返回 None
    """
    return _task_handlers.get(task_type)
