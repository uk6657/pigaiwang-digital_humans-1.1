"""基于分表的任务服务层实现.

处理任务在不同状态表之间的流转：
- TaskPending → TaskRunning: 任务开始执行
- TaskRunning → TaskCompleted: 任务成功完成
- TaskRunning → TaskFailed: 任务失败/超时/取消
- TaskRunning → TaskPending: 任务失败但可重试
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.time_ import time_now
from app.utils.snowflake_id import generate_id

from .config import task_config
from .enums import FailReason, TaskTable, TaskType
from .exceptions import TaskNotFoundError
from .logging import logger
from .models import (
    AnyTask,
    TaskCompleted,
    TaskFailed,
    TaskPending,
    TaskRunning,
)


class TaskService:
    """任务服务层.

    提供任务的创建、状态流转、查询等业务操作。
    核心是处理任务在不同表之间的移动。

    注意：所有写操作不会自动 commit，由调用方控制事务。

    Attributes:
        db: 异步数据库会话
        TABLE_MODEL_MAP: 表类型到模型类的映射
    """

    TABLE_MODEL_MAP: dict[TaskTable, type[AnyTask]] = {
        TaskTable.PENDING: TaskPending,
        TaskTable.RUNNING: TaskRunning,
        TaskTable.COMPLETED: TaskCompleted,
        TaskTable.FAILED: TaskFailed,
    }

    def __init__(self, db: AsyncSession) -> None:
        """初始化任务服务.

        Args:
            db: 异步数据库会话
        """
        self.db = db

    # ==================== 创建任务 ====================

    async def create_task(
        self,
        task_type: TaskType,
        related_id: int | str,
        creator_id: int | str,
        task_name: str | None = None,
        task_description: str | None = None,
        max_retries: int | None = None,
    ) -> TaskPending:
        """创建任务.

        创建一个新的待执行任务，插入 TaskPending 表。
        调用方需要在创建后将任务提交到 TaskIQ。

        Args:
            task_type: 任务类型
            related_id: 关联的业务表 ID
            creator_id: 创建用户 ID
            task_name: 任务名称，默认使用 task_type.display_name
            task_description: 任务描述
            max_retries: 最大重试次数，默认使用配置值

        Returns:
            创建的 TaskPending 对象
        """
        task = TaskPending(
            id=generate_id(),
            task_type=task_type,
            related_id=str(related_id),
            creator_id=str(creator_id),
            task_name=task_name or task_type.display_name,
            task_description=task_description,
            max_retries=max_retries or task_config.DEFAULT_MAX_RETRIES,
        )

        self.db.add(task)
        logger.info(f"创建任务: {task}")
        return task

    # ==================== 状态流转 ====================

    async def start_task(
        self,
        task_id: str,
        worker_id: str,
        is_resume: bool = False,
    ) -> TaskRunning | None:
        """开始执行任务.

        将任务从 TaskPending 移动到 TaskRunning。
        如果是恢复执行（is_resume=True），则从 TaskRunning 表中更新。

        Args:
            task_id: 任务 ID
            worker_id: Worker 标识
            is_resume: 是否是恢复执行（心跳超时后重新执行）

        Returns:
            成功返回 TaskRunning 对象，任务不存在或状态不符返回 None
        """
        now = time_now()

        if is_resume:
            # 恢复执行：更新 TaskRunning 表
            result = await self.db.execute(
                update(TaskRunning)
                .where(TaskRunning.id == task_id)
                .values(
                    worker_id=worker_id,
                    heartbeat_at=now,
                    retry_count=TaskRunning.retry_count + 1,
                )
                .returning(TaskRunning)
            )
            task_running = result.scalar_one_or_none()

            if task_running:
                logger.info(
                    f"恢复执行任务: {task_id}, retry_count={task_running.retry_count}"
                )
            return task_running

        # 首次执行：从 TaskPending 移动到 TaskRunning
        # 1. 查询 TaskPending
        result = await self.db.execute(
            select(TaskPending).where(
                TaskPending.id == task_id,
                TaskPending.is_deleted == False,  # noqa: E712
            )
        )
        pending_task = result.scalar_one_or_none()

        if not pending_task:
            return None

        # 2. 创建 TaskRunning 记录
        running_task = TaskRunning(
            id=pending_task.id,
            task_type=pending_task.task_type,
            related_id=pending_task.related_id,
            creator_id=pending_task.creator_id,
            created_at=pending_task.created_at,
            task_name=pending_task.task_name,
            task_description=pending_task.task_description,
            worker_id=worker_id,
            heartbeat_at=now,
            started_at=now,
            retry_count=pending_task.retry_count,
            max_retries=pending_task.max_retries,
        )

        # 3. 删除 TaskPending 记录
        await self.db.execute(delete(TaskPending).where(TaskPending.id == task_id))

        # 4. 插入 TaskRunning 记录
        self.db.add(running_task)

        logger.info(f"任务开始执行: {task_id}, worker={worker_id}")
        return running_task

    async def complete_task(self, task_id: str) -> TaskCompleted:
        """完成任务.

        将任务从 TaskRunning 移动到 TaskCompleted。

        Args:
            task_id: 任务 ID

        Returns:
            TaskCompleted 对象

        Raises:
            TaskNotFoundError: 任务不存在
        """
        now = time_now()

        # 1. 查询 TaskRunning
        result = await self.db.execute(
            select(TaskRunning).where(TaskRunning.id == task_id)
        )
        running_task = result.scalar_one_or_none()

        if not running_task:
            raise TaskNotFoundError(task_id)

        # 2. 创建 TaskCompleted 记录
        completed_task = TaskCompleted(
            id=running_task.id,
            task_type=running_task.task_type,
            related_id=running_task.related_id,
            creator_id=running_task.creator_id,
            created_at=running_task.created_at,
            task_name=running_task.task_name,
            task_description=running_task.task_description,
            started_at=running_task.started_at,
            finished_at=now,
        )

        # 3. 删除 TaskRunning 记录
        await self.db.execute(delete(TaskRunning).where(TaskRunning.id == task_id))

        # 4. 插入 TaskCompleted 记录
        self.db.add(completed_task)

        logger.info(f"任务完成: {task_id}")
        return completed_task

    async def fail_task(
        self,
        task_id: str,
        error_message: str,
        fail_reason: FailReason = FailReason.ERROR,
    ) -> TaskFailed | TaskPending:
        """任务失败处理.

        如果重试次数未耗尽，将任务移回 TaskPending 等待重试。
        如果重试次数已耗尽，将任务移动到 TaskFailed。

        Args:
            task_id: 任务 ID
            error_message: 错误信息
            fail_reason: 失败原因

        Returns:
            TaskFailed 或 TaskPending 对象

        Raises:
            TaskNotFoundError: 任务不存在
        """
        now = time_now()

        # 1. 查询 TaskRunning
        result = await self.db.execute(
            select(TaskRunning).where(TaskRunning.id == task_id)
        )
        running_task = result.scalar_one_or_none()

        if not running_task:
            raise TaskNotFoundError(task_id)

        # 2. 删除 TaskRunning 记录
        await self.db.execute(delete(TaskRunning).where(TaskRunning.id == task_id))

        # 3. 判断是重试还是彻底失败
        if running_task.can_retry and fail_reason == FailReason.ERROR:
            # 可以重试：移回 TaskPending
            pending_task = TaskPending(
                id=running_task.id,
                task_type=running_task.task_type,
                related_id=running_task.related_id,
                creator_id=running_task.creator_id,
                created_at=running_task.created_at,
                task_name=running_task.task_name,
                task_description=running_task.task_description,
                retry_count=running_task.retry_count + 1,
                max_retries=running_task.max_retries,
            )
            self.db.add(pending_task)

            logger.info(
                f"任务失败将重试: {task_id}, "
                f"retry_count={running_task.retry_count}/{running_task.max_retries}, "
                f"error={error_message}"
            )
            return pending_task

        # 彻底失败：移动到 TaskFailed
        failed_task = TaskFailed(
            id=running_task.id,
            task_type=running_task.task_type,
            related_id=running_task.related_id,
            creator_id=running_task.creator_id,
            created_at=running_task.created_at,
            task_name=running_task.task_name,
            task_description=running_task.task_description,
            fail_reason=fail_reason,
            error_message=error_message,
            started_at=running_task.started_at,
            finished_at=now,
            retry_count=running_task.retry_count,
        )
        self.db.add(failed_task)

        logger.error(
            f"任务失败: {task_id}, reason={fail_reason.display_name}, error={error_message}"
        )
        return failed_task

    async def timeout_task(self, task_id: str) -> TaskFailed | TaskPending:
        """任务超时处理.

        超时的任务会尝试重试，重试次数耗尽后标记为超时失败。

        Args:
            task_id: 任务 ID

        Returns:
            TaskFailed 或 TaskPending 对象
        """
        return await self.fail_task(
            task_id=task_id,
            error_message="任务执行超时",
            fail_reason=FailReason.TIMEOUT,
        )

    # ==================== 取消任务 ====================

    async def cancel_pending_task(self, task_id: str) -> TaskFailed | None:
        """取消待执行的任务.

        将任务从 TaskPending 移动到 TaskFailed。

        Args:
            task_id: 任务 ID

        Returns:
            取消成功返回 TaskFailed，任务不存在返回 None
        """
        now = time_now()

        # 1. 查询并删除 TaskPending
        result = await self.db.execute(
            select(TaskPending).where(
                TaskPending.id == task_id,
                TaskPending.is_deleted == False,  # noqa: E712
            )
        )
        pending_task = result.scalar_one_or_none()

        if not pending_task:
            return None

        await self.db.execute(delete(TaskPending).where(TaskPending.id == task_id))

        # 2. 插入 TaskFailed
        failed_task = TaskFailed(
            id=pending_task.id,
            task_type=pending_task.task_type,
            related_id=pending_task.related_id,
            creator_id=pending_task.creator_id,
            created_at=pending_task.created_at,
            task_name=pending_task.task_name,
            task_description=pending_task.task_description,
            fail_reason=FailReason.CANCELLED,
            error_message="用户取消",
            started_at=None,
            finished_at=now,
            retry_count=pending_task.retry_count,
        )
        self.db.add(failed_task)

        logger.info(f"取消待执行任务: {task_id}")
        return failed_task

    async def mark_cancelling(self, task_id: str) -> bool:
        """标记任务正在取消.

        设置 TaskRunning 表的 is_cancelling 字段为 True。
        Worker 在执行过程中会检测此标记并退出。

        Args:
            task_id: 任务 ID

        Returns:
            标记成功返回 True，任务不存在返回 False
        """
        result = await self.db.execute(
            update(TaskRunning)
            .where(TaskRunning.id == task_id)
            .values(is_cancelling=True)
            .returning(TaskRunning.id)
        )

        success = result.scalar() is not None
        if success:
            logger.info(f"标记任务取消中: {task_id}")
        return success

    async def cancel_running_task(self, task_id: str) -> TaskFailed | None:
        """取消执行中的任务.

        由 Worker 检测到取消标记后调用，将任务移动到 TaskFailed。

        Args:
            task_id: 任务 ID

        Returns:
            取消成功返回 TaskFailed，任务不存在返回 None
        """
        now = time_now()

        # 1. 查询并删除 TaskRunning
        result = await self.db.execute(
            select(TaskRunning).where(TaskRunning.id == task_id)
        )
        running_task = result.scalar_one_or_none()

        if not running_task:
            return None

        await self.db.execute(delete(TaskRunning).where(TaskRunning.id == task_id))

        # 2. 插入 TaskFailed
        failed_task = TaskFailed(
            id=running_task.id,
            task_type=running_task.task_type,
            related_id=running_task.related_id,
            creator_id=running_task.creator_id,
            created_at=running_task.created_at,
            task_name=running_task.task_name,
            task_description=running_task.task_description,
            fail_reason=FailReason.CANCELLED,
            error_message="用户取消",
            started_at=running_task.started_at,
            finished_at=now,
            retry_count=running_task.retry_count,
        )
        self.db.add(failed_task)

        logger.info(f"取消执行中任务: {task_id}")
        return failed_task

    async def cancel_task(self, task_id: str) -> bool:
        """取消任务（通用接口）.

        根据任务所在表执行不同的取消操作：
        - TaskPending: 直接移动到 TaskFailed
        - TaskRunning: 标记 is_cancelling，等待 Worker 处理

        Args:
            task_id: 任务 ID

        Returns:
            操作成功返回 True，任务不存在或已完成返回 False
        """
        # 先尝试取消 pending 任务
        result = await self.cancel_pending_task(task_id)
        if result:
            return True

        # 再尝试标记 running 任务
        return await self.mark_cancelling(task_id)

    # ==================== 查询方法 ====================

    async def is_cancelling(self, task_id: str) -> bool:
        """检查任务是否正在取消.

        用于 Worker 执行过程中定期检查。

        Args:
            task_id: 任务 ID

        Returns:
            正在取消返回 True
        """
        result = await self.db.execute(
            select(TaskRunning.is_cancelling).where(TaskRunning.id == task_id)
        )
        is_cancelling = result.scalar()
        return is_cancelling is True

    def _build_query_filters(
        self,
        model: AnyTask,
        task_type: TaskType | None = None,
        creator_id: int | str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list:
        """构建通用查询条件.

        Args:
            model: 任务模型类
            task_type: 任务类型筛选
            creator_id: 创建人筛选
            start_time: 开始时间筛选
            end_time: 结束时间筛选

        Returns:
            SQLAlchemy 条件列表
        """
        filters = []

        # 软删除过滤（仅部分表有此字段）
        if hasattr(model, "is_deleted"):
            filters.append(model.is_deleted == False)  # noqa: E712

        if task_type is not None:
            filters.append(model.task_type == task_type.value)

        if creator_id is not None:
            filters.append(model.creator_id == str(creator_id))

        if start_time is not None:
            filters.append(model.created_at >= start_time)

        if end_time is not None:
            filters.append(model.created_at <= end_time)

        return filters

    async def get_task(
        self,
        task_id: str,
        table: TaskTable | None = None,
    ) -> tuple[AnyTask | None, TaskTable | None]:
        """按 ID 查询任务.

        Args:
            task_id: 任务 ID
            table: 指定查询的表，None 则自动查找所有表

        Returns:
            (任务对象, 表类型) 元组，不存在返回 (None, None)
        """
        # 指定表查询
        if table is not None:
            model = self.TABLE_MODEL_MAP[table]
            filters = self._build_query_filters(model)
            filters.append(model.id == task_id)
            result = await self.db.execute(select(model).where(*filters))
            task = result.scalar_one_or_none()
            return (task, table) if task else (None, None)

        # 自动查找：优先热数据表
        for table_type in [
            TaskTable.RUNNING,
            TaskTable.PENDING,
            TaskTable.COMPLETED,
            TaskTable.FAILED,
        ]:
            model = self.TABLE_MODEL_MAP[table_type]
            filters = self._build_query_filters(model)
            filters.append(model.id == task_id)
            result = await self.db.execute(select(model).where(*filters))
            if task := result.scalar_one_or_none():
                return task, table_type

        return None, None

    async def get_task_or_raise(
        self,
        task_id: str,
        table: TaskTable | None = None,
    ) -> tuple[AnyTask, TaskTable]:
        """获取任务，不存在则抛出异常.

        Args:
            task_id: 任务 ID
            table: 指定查询的表，None 则自动查找所有表

        Returns:
            (任务对象, 表类型) 元组

        Raises:
            TaskNotFoundError: 任务不存在
        """
        task, task_table = await self.get_task(task_id, table)
        if not task or not task_table:
            raise TaskNotFoundError(task_id)
        return task, task_table

    async def count_tasks(
        self,
        table: TaskTable | None = None,
        task_type: TaskType | None = None,
        creator_id: int | str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> int | dict[TaskTable, int]:
        """统计任务数量.

        Args:
            table: 指定状态，None 则统计所有状态
            task_type: 任务类型筛选
            creator_id: 创建人筛选
            start_time: 开始时间筛选（基于 created_at）
            end_time: 结束时间筛选（基于 created_at）

        Returns:
            table 指定时返回 int，否则返回 dict[TaskTable, int]
        """
        if table is not None:
            model = self.TABLE_MODEL_MAP[table]
            filters = self._build_query_filters(
                model, task_type, creator_id, start_time, end_time
            )
            result = await self.db.execute(select(func.count(model.id)).where(*filters))
            return result.scalar() or 0

        # 全部表统计
        counts: dict[TaskTable, int] = {}
        for tbl, model in self.TABLE_MODEL_MAP.items():
            filters = self._build_query_filters(
                model, task_type, creator_id, start_time, end_time
            )
            result = await self.db.execute(select(func.count(model.id)).where(*filters))
            counts[tbl] = result.scalar() or 0
        return counts

    async def list_tasks(
        self,
        table: TaskTable,
        task_type: TaskType | None = None,
        creator_id: int | str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[AnyTask], int]:
        """分页查询任务列表.

        Args:
            table: 任务状态（必选）
            task_type: 任务类型筛选
            creator_id: 创建人筛选
            start_time: 开始时间筛选（基于 created_at）
            end_time: 结束时间筛选（基于 created_at）
            limit: 分页大小
            offset: 分页偏移

        Returns:
            (任务列表, 总数) 元组
        """
        model = self.TABLE_MODEL_MAP[table]
        filters = self._build_query_filters(
            model, task_type, creator_id, start_time, end_time
        )

        # 查询总数
        count_result = await self.db.execute(
            select(func.count(model.id)).where(*filters)
        )
        total = count_result.scalar() or 0

        # 查询数据
        query = (
            select(model)
            .where(*filters)
            .order_by(model.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.db.execute(query)
        tasks = list(result.scalars().all())

        return tasks, total

    # ==================== 内部扫描方法 ====================

    async def count_running_tasks(self) -> int:
        """统计执行中的任务数量.

        Returns:
            TaskRunning 表的记录数
        """
        result = await self.db.execute(select(func.count(TaskRunning.id)))
        return result.scalar() or 0

    async def count_pending_tasks(self) -> int:
        """统计待执行的任务数量.

        Returns:
            TaskPending 表的记录数
        """
        result = await self.db.execute(
            select(func.count(TaskPending.id)).where(
                TaskPending.is_deleted == False,  # noqa: E712
            )
        )
        return result.scalar() or 0

    async def get_timeout_pending_tasks(
        self,
        timeout_seconds: int,
        limit: int = 100,
    ) -> list[TaskPending]:
        """获取超时的待执行任务.

        用于定时器扫描重新提交。

        Args:
            timeout_seconds: 超时阈值（秒）
            limit: 最大返回数量

        Returns:
            超时的 TaskPending 列表
        """
        threshold = time_now() - timedelta(seconds=timeout_seconds)

        result = await self.db.execute(
            select(TaskPending)
            .where(
                TaskPending.updated_at < threshold,
                TaskPending.is_deleted == False,  # noqa: E712
            )
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_heartbeat_timeout_tasks(
        self,
        timeout_seconds: int,
        limit: int = 100,
    ) -> list[TaskRunning]:
        """获取心跳超时的执行中任务.

        用于定时器扫描重新提交。

        Args:
            timeout_seconds: 超时阈值（秒）
            limit: 最大返回数量

        Returns:
            心跳超时的 TaskRunning 列表
        """
        threshold = time_now() - timedelta(seconds=timeout_seconds)

        result = await self.db.execute(
            select(TaskRunning).where(TaskRunning.heartbeat_at < threshold).limit(limit)
        )
        return list(result.scalars().all())
