"""任务相关异常定义.

定义任务队列中可能出现的各类异常。
"""

from __future__ import annotations


class TaskException(Exception):
    """任务异常基类.

    Attributes:
        message: 异常消息
        task_id: 相关的任务 ID
    """

    def __init__(self, message: str, task_id: int | str | None = None) -> None:
        """初始化异常.

        Args:
            message: 异常消息
            task_id: 相关的任务 ID
        """
        self.message = message
        self.task_id = task_id
        super().__init__(self.message)


class LockAcquireError(TaskException):
    """获取锁失败异常.

    当无法获取任务的分布式锁时抛出。
    通常意味着该任务已被其他 Worker 持有。
    """

    def __init__(self, task_id: int | str) -> None:
        """初始化异常.

        Args:
            task_id: 任务 ID
        """
        super().__init__(
            message=f"无法获取任务 {task_id} 的锁，可能已被其他 Worker 持有",
            task_id=task_id,
        )


class LockLostError(TaskException):
    """锁丢失异常.

    当任务执行过程中锁意外丢失时抛出。
    可能原因：锁过期、Redis 故障、网络问题等。
    """

    def __init__(self, task_id: int | str) -> None:
        """初始化异常.

        Args:
            task_id: 任务 ID
        """
        super().__init__(
            message=f"任务 {task_id} 的锁已丢失",
            task_id=task_id,
        )


class TaskCancelledError(TaskException):
    """任务取消异常.

    当检测到任务被用户取消时抛出。
    Worker 应捕获此异常并优雅退出。
    """

    def __init__(self, task_id: int | str) -> None:
        """初始化异常.

        Args:
            task_id: 任务 ID
        """
        super().__init__(
            message=f"任务 {task_id} 已被取消",
            task_id=task_id,
        )


class TaskNotFoundError(TaskException):
    """任务不存在异常.

    当尝试操作不存在的任务时抛出。
    """

    def __init__(self, task_id: int | str) -> None:
        """初始化异常.

        Args:
            task_id: 任务 ID
        """
        super().__init__(
            message=f"任务 {task_id} 不存在",
            task_id=task_id,
        )


class TaskRetryExhaustedError(TaskException):
    """任务重试次数耗尽异常.

    当任务达到最大重试次数仍然失败时抛出。

    Attributes:
        retry_count: 当前重试次数
        max_retries: 最大重试次数
    """

    def __init__(
        self,
        task_id: int | str,
        retry_count: int,
        max_retries: int,
    ) -> None:
        """初始化异常.

        Args:
            task_id: 任务 ID
            retry_count: 当前重试次数
            max_retries: 最大重试次数
        """
        self.retry_count = retry_count
        self.max_retries = max_retries
        super().__init__(
            message=f"任务 {task_id} 重试次数耗尽: {retry_count}/{max_retries}",
            task_id=task_id,
        )
