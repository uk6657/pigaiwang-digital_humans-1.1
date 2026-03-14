"""任务队列配置.

集中管理任务队列相关的所有配置参数。
"""

from __future__ import annotations

import os
import socket
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class TaskQueueConfig(BaseSettings):
    """任务队列配置参数.

    可通过环境变量覆盖，环境变量前缀为 TASK_QUEUE_。

    Attributes:
        WORKER_ID: 标识worker的唯一ID
        HEARTBEAT_INTERVAL: 心跳间隔（秒）
        HEARTBEAT_TIMEOUT: 心跳超时阈值（秒）
        SCAN_INTERVAL: 定时器扫描间隔（秒）
        PENDING_TIMEOUT: PENDING 状态超时阈值（秒）
        LOCK_EXPIRE_SECONDS: Redis 锁过期时间（秒）
        LOCK_KEY_PREFIX: Redis 锁的 Key 前缀
        MAX_RUNNING_TASKS: 最大同时运行任务数
        DEFAULT_MAX_RETRIES: 默认最大重试次数
        PROCESS_POOL_SIZE: 进程池大小
        THREAD_POOL_SIZE: 线程池大小
        CANCEL_CHECK_INTERVAL: 取消状态检查间隔（处理项数）
        LOG_DIR: 日志目录路径
        LOG_LEVEL: 日志级别

    Example:
        通过环境变量配置::

            export TASK_QUEUE_MAX_RUNNING_TASKS=200
            export TASK_QUEUE_LOG_DIR=/var/log/myapp/tasks
    """

    model_config: SettingsConfigDict = SettingsConfigDict(
        env_file="./conf/task.env", env_file_encoding="utf-8", extra="ignore"
    )
    # ===================== 基本配置 ====================

    WORKER_ID: str = f"{socket.gethostname()}-{os.getpid()}"
    """Worker ID，使用主机名 + 进程 ID"""

    # ===================== 心跳相关 ====================
    HEARTBEAT_INTERVAL: int = 10
    """心跳间隔（秒）：Worker 每隔多久更新一次心跳"""

    HEARTBEAT_TIMEOUT: int = 30
    """心跳超时阈值（秒）：超过此时间未更新心跳视为异常"""

    # ==================== 定时器相关 ====================
    SCAN_INTERVAL: int = 30
    """扫描间隔（秒）：定时器每隔多久扫描一次待处理任务"""

    PENDING_TIMEOUT: int = 30
    """PENDING 超时阈值（秒）：pending 状态超过此时间会被重新提交"""

    # ==================== Redis 锁相关 ====================
    LOCK_EXPIRE_SECONDS: int = 45
    """锁过期时间（秒）：与心跳超时保持一致"""

    LOCK_KEY_PREFIX: str = "task_lock:"
    """锁的 Key 前缀"""

    # ==================== 任务控制 ====================
    MAX_RUNNING_TASKS: int = 100
    """最大同时运行任务数"""

    DEFAULT_MAX_RETRIES: int = 3
    """默认最大重试次数"""

    # ==================== Worker 相关 ====================
    PROCESS_POOL_SIZE: int = 2
    """进程池大小（用于 CPU 密集型计算）"""

    THREAD_POOL_SIZE: int = 10
    """线程池大小（用于 IO 密集型操作）"""

    # ==================== 取消检测相关 ====================
    CANCEL_CHECK_INTERVAL: int = 100
    """每处理多少个项目检查一次取消状态"""

    # ==================== 日志相关 ====================
    LOG_DIR: Path = Path("./logs/tasks")
    """日志目录路径"""

    LOG_LEVEL: str = "DEBUG"
    """日志级别"""

    LOG_ROTATION: str = "1 week"
    """日志轮转策略"""

    LOG_RETENTION: str = "1 month"
    """日志保留时间"""


# 全局配置实例
task_config = TaskQueueConfig()
