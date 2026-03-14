"""任务数据库模型 - 分表设计.

按任务状态分为四张表：
- TaskPending: 待执行任务（热数据，小表）
- TaskRunning: 执行中任务（热数据，小表）
- TaskCompleted: 已完成任务（冷数据，大表，只插入只查询）
- TaskFailed: 失败任务（小表，用于排查问题）

优势：
- 热冷数据分离，running/pending 表始终保持很小
- completed 表无更新操作，可按时间分区
- 不需要 status 索引，表本身就代表状态
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Index, Integer, SmallInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.storage.base import (
    AbstractBaseModel,
    BeijingTimeZone,
    StringifiedBigInt,
    register_model,
)

from .config import task_config
from .enums import FailReason, TaskTable, TaskType


class TaskMixin:
    """任务表公共 Mixin.

    提供所有任务表共享的字段定义。
    注意：不继承 AbstractBaseModel，由具体表类继承。

    Attributes:
        id: 雪花 ID，主键
        task_type: 任务类型
        related_id: 关联的业务表 ID
        creator_id: 创建用户 ID
        task_name: 任务名称
        task_description: 任务描述
    """

    # ==================== 主键 ====================
    id: Mapped[str] = mapped_column(
        StringifiedBigInt,
        primary_key=True,
        comment="雪花ID，主键",
    )

    # ==================== 任务关联 ====================
    task_type: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        index=True,
        comment="任务类型，对应 TaskType 枚举",
    )

    related_id: Mapped[str] = mapped_column(
        StringifiedBigInt,
        nullable=False,
        comment="关联的业务表ID",
    )

    creator_id: Mapped[str] = mapped_column(
        StringifiedBigInt,
        nullable=False,
        index=True,
        comment="创建用户ID",
    )

    # ==================== 任务描述 ====================
    task_name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        comment="任务名称",
    )

    task_description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="任务描述",
    )

    # ==================== 属性方法 ====================
    @property
    def task_type_enum(self) -> TaskType:
        """获取任务类型枚举.

        Returns:
            TaskType 枚举值
        """
        return TaskType(self.task_type)


@register_model
class TaskPending(TaskMixin, AbstractBaseModel):
    """待执行任务表.

    存储等待执行的任务，是热数据表。
    任务被 Worker 接收后会移动到 TaskRunning 表。

    继承自 AbstractBaseModel 的字段:
        created_at: 创建时间
        updated_at: 更新时间（用于超时判断）
        is_deleted: 软删除标记
    """

    __tablename__ = "task_pending"

    # ==================== 重试相关 ====================
    retry_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="当前重试次数",
    )

    max_retries: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=task_config.DEFAULT_MAX_RETRIES,
        comment="最大重试次数",
    )

    # ==================== 索引 ====================
    __table_args__ = (
        # 用于定时器扫描超时的 pending 任务
        Index("idx_pending_updated", "updated_at"),
        {"comment": "待执行任务表"},
    )

    @property
    def table_type(self) -> TaskTable:
        """获取任务所在表类型."""
        return TaskTable.PENDING

    def __repr__(self) -> str:
        """返回任务的字符串表示形式.

        Returns:
            格式化的任务信息字符串
        """
        return f"<TaskPending(id={self.id}, type={self.task_type_enum.display_name})>"


@register_model
class TaskRunning(TaskMixin, AbstractBaseModel):
    """执行中任务表.

    存储正在执行的任务，是热数据表。
    Worker 会定期更新心跳时间。
    任务完成后移动到 TaskCompleted 或 TaskFailed 表。

    继承自 AbstractBaseModel 的字段:
        created_at: 创建时间
        updated_at: 更新时间
        is_deleted: 软删除标记
    """

    __tablename__ = "task_running"

    # ==================== 执行信息 ====================
    worker_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="当前处理的Worker标识",
    )

    heartbeat_at: Mapped[datetime] = mapped_column(
        BeijingTimeZone(),
        nullable=False,
        index=True,
        comment="心跳时间",
    )

    started_at: Mapped[datetime] = mapped_column(
        BeijingTimeZone(),
        nullable=False,
        comment="任务开始执行时间",
    )

    # ==================== 重试相关 ====================
    retry_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="当前重试次数",
    )

    max_retries: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=task_config.DEFAULT_MAX_RETRIES,
        comment="最大重试次数",
    )

    # ==================== 取消标记 ====================
    is_cancelling: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
        comment="是否正在取消（Worker 检测此标记后退出）",
    )

    # ==================== 索引 ====================
    __table_args__ = (
        # 用于定时器扫描心跳超时的任务
        Index("idx_running_heartbeat", "heartbeat_at"),
        {"comment": "执行中任务表"},
    )

    @property
    def table_type(self) -> TaskTable:
        """获取任务所在表类型."""
        return TaskTable.RUNNING

    @property
    def can_retry(self) -> bool:
        """判断任务是否可以重试.

        Returns:
            是否可以重试
        """
        return self.retry_count < self.max_retries

    def __repr__(self) -> str:
        """返回任务的字符串表示形式.

        Returns:
            格式化的任务信息字符串
        """
        return (
            f"<TaskRunning(id={self.id}, type={self.task_type_enum.display_name}, "
            f"worker={self.worker_id})>"
        )


@register_model
class TaskCompleted(TaskMixin, AbstractBaseModel):
    """已完成任务表.

    存储成功完成的任务，是冷数据表。
    只有插入和查询操作，没有更新。
    可按时间分区便于归档。

    继承自 AbstractBaseModel 的字段:
        created_at: 创建时间
        updated_at: 更新时间（实际不会更新）
        is_deleted: 软删除标记
    """

    __tablename__ = "task_completed"

    # ==================== 执行信息 ====================
    started_at: Mapped[datetime] = mapped_column(
        BeijingTimeZone(),
        nullable=False,
        comment="任务开始执行时间",
    )

    finished_at: Mapped[datetime] = mapped_column(
        BeijingTimeZone(),
        nullable=False,
        index=True,
        comment="任务完成时间",
    )

    # ==================== 索引 ====================
    __table_args__ = (
        # 按完成时间查询，便于归档
        Index("idx_completed_finished", "finished_at"),
        {"comment": "已完成任务表"},
    )

    @property
    def table_type(self) -> TaskTable:
        """获取任务所在表类型."""
        return TaskTable.COMPLETED

    def __repr__(self) -> str:
        """返回任务的字符串表示形式.

        Returns:
            格式化的任务信息字符串
        """
        return f"<TaskCompleted(id={self.id}, type={self.task_type_enum.display_name})>"


@register_model
class TaskFailed(TaskMixin, AbstractBaseModel):
    """失败任务表.

    存储执行失败、超时或被取消的任务。
    用于问题排查和统计分析。

    继承自 AbstractBaseModel 的字段:
        created_at: 创建时间
        updated_at: 更新时间（实际不会更新）
        is_deleted: 软删除标记
    """

    __tablename__ = "task_failed"

    # ==================== 失败信息 ====================
    fail_reason: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        index=True,
        comment="失败原因，对应 FailReason 枚举",
    )

    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="错误信息",
    )

    # ==================== 执行信息 ====================
    started_at: Mapped[datetime | None] = mapped_column(
        BeijingTimeZone(),
        nullable=True,
        comment="任务开始执行时间（可能未开始就失败）",
    )

    finished_at: Mapped[datetime] = mapped_column(
        BeijingTimeZone(),
        nullable=False,
        index=True,
        comment="任务失败时间",
    )

    # ==================== 重试信息 ====================
    retry_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="重试了多少次",
    )

    # ==================== 索引 ====================
    __table_args__ = (
        Index("idx_failed_finished", "finished_at"),
        Index("idx_failed_reason", "fail_reason"),
        {"comment": "失败任务表"},
    )

    @property
    def table_type(self) -> TaskTable:
        """获取任务所在表类型."""
        return TaskTable.FAILED

    @property
    def fail_reason_enum(self) -> FailReason:
        """获取失败原因枚举.

        Returns:
            FailReason 枚举值
        """
        return FailReason(self.fail_reason)

    def __repr__(self) -> str:
        """返回任务的字符串表示形式.

        Returns:
            格式化的任务信息字符串
        """
        return (
            f"<TaskFailed(id={self.id}, type={self.task_type_enum.display_name}, "
            f"reason={self.fail_reason_enum.display_name})>"
        )


# ==================== 类型别名 ====================
# 用于类型标注，表示任意任务表的记录
AnyTask = TaskPending | TaskRunning | TaskCompleted | TaskFailed
