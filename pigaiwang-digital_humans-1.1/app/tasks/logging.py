"""日志配置模块.

使用 loguru 实现日志管理，支持：
- 按周轮转日志文件
- 最大保留1个月
- 每个任务独立的日志文件
- 空文件不创建
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from loguru import Logger


class TaskLoggerConfig:
    """任务日志配置类.

    Attributes:
        log_dir: 日志根目录
        rotation: 日志轮转策略
        retention: 日志保留时间
        compression: 压缩格式
        encoding: 文件编码
        format: 日志格式
    """

    def __init__(
        self,
        log_dir: str | Path = "./logs/tasks",
        rotation: str = "1 week",
        retention: str = "1 month",
        compression: str = "zip",
        encoding: str = "utf-8",
        log_format: str | None = None,
    ) -> None:
        """初始化日志配置.

        Args:
            log_dir: 日志根目录路径
            rotation: 日志轮转策略，默认每周轮转
            retention: 日志保留时间，默认保留1个月
            compression: 压缩格式，默认 zip
            encoding: 文件编码，默认 utf-8
            log_format: 日志格式，None 则使用默认格式
        """
        self.log_dir = Path(log_dir)
        self.rotation = rotation
        self.retention = retention
        self.compression = compression
        self.encoding = encoding
        self.format = log_format or (
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        )

        # 任务日志格式（包含任务 ID）
        self.task_format = (
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{extra[task_id]}</cyan> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        )

        # 确保日志目录存在
        self.log_dir.mkdir(parents=True, exist_ok=True)

    @property
    def main_log_path(self) -> Path:
        """主日志文件路径."""
        return self.log_dir / "task_queue_{time:YYYY-MM-DD}.log"

    def get_task_log_path(self, task_id: str) -> Path:
        """获取任务专属日志文件路径.

        Args:
            task_id: 任务 ID

        Returns:
            任务日志文件路径
        """
        task_log_dir = self.log_dir / "tasks"
        task_log_dir.mkdir(parents=True, exist_ok=True)
        return task_log_dir / f"task_{task_id}.log"


# 全局配置实例
_config: TaskLoggerConfig | None = None

# 已注册的任务日志 handler ID
_task_handlers: dict[str, int] = {}


def setup_task_logger(
    log_dir: str | Path = "./logs/tasks",
    level: str = "DEBUG",
    rotation: str = "1 week",
    retention: str = "1 month",
) -> None:
    """配置任务队列日志.

    应在应用启动时调用一次。

    Args:
        log_dir: 日志根目录路径
        level: 日志级别
        rotation: 日志轮转策略
        retention: 日志保留时间

    Example:
        >>> setup_task_logger(
        ...     log_dir="/var/log/myapp/tasks",
        ...     level="INFO",
        ... )
    """
    global _config
    _config = TaskLoggerConfig(
        log_dir=log_dir,
        rotation=rotation,
        retention=retention,
    )

    # 移除默认 handler
    logger.remove()

    # 添加控制台输出
    logger.add(
        sys.stderr,
        format=_config.format,
        level=level,
        colorize=True,
    )

    # 添加主日志文件（按周轮转，空则不创建）
    logger.add(
        str(_config.main_log_path),
        format=_config.format,
        level=level,
        rotation=_config.rotation,
        retention=_config.retention,
        compression=_config.compression,
        encoding=_config.encoding,
        delay=True,  # 延迟创建，空则不创建
    )


def get_task_logger(task_id: str) -> Logger:
    """获取任务专属的 logger.

    为指定任务创建独立的日志文件。

    Args:
        task_id: 任务 ID

    Returns:
        绑定了任务 ID 的 logger 实例

    Example:
        >>> task_logger = get_task_logger("123456")
        >>> task_logger.info("任务开始执行")
    """
    global _config, _task_handlers

    if _config is None:
        # 使用默认配置
        _config = TaskLoggerConfig()

    # 如果该任务的 handler 已存在，直接返回绑定的 logger
    if task_id in _task_handlers:
        return logger.bind(task_id=task_id)

    # 创建任务专属日志文件
    task_log_path = _config.get_task_log_path(task_id)

    # 添加任务专属 handler
    handler_id = logger.add(
        str(task_log_path),
        format=_config.task_format,
        level="DEBUG",
        rotation=_config.rotation,
        retention=_config.retention,
        compression=_config.compression,
        encoding=_config.encoding,
        filter=lambda record: record["extra"].get("task_id") == task_id,
        delay=True,
    )

    _task_handlers[task_id] = handler_id

    return logger.bind(task_id=task_id)


def remove_task_logger(task_id: str) -> None:
    """移除任务专属的 logger handler.

    任务完成后应调用此函数清理资源。

    Args:
        task_id: 任务 ID
    """
    global _task_handlers

    if task_id in _task_handlers:
        handler_id = _task_handlers.pop(task_id)
        try:
            logger.remove(handler_id)
        except ValueError:
            # handler 可能已被移除
            pass


__all__ = [
    "logger",
    "setup_task_logger",
    "get_task_logger",
    "remove_task_logger",
    "TaskLoggerConfig",
]
