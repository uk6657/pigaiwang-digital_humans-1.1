from __future__ import annotations

"""Database models for the digital human demo backend."""

from enum import IntEnum

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.orm import relationship

from app.storage.base import AbstractBaseModel, BeijingTimeZone, register_model


class UserType(IntEnum):
    """Login user type defined by the product."""

    teacher = 1
    operator = 2


class VideoSyncStatus(IntEnum):
    """Result of the latest filesystem sync for a video asset."""

    pending = 0
    synced = 1
    missing = 2
    failed = 3


class VideoSourceType(IntEnum):
    """Original uploaded/source file type."""

    unknown = 0
    mp4 = 1
    mov = 2
    avi = 3
    mkv = 4


class VideoPlaybackType(IntEnum):
    """Preferred playback mode for frontend consumption."""

    mp4 = 1
    hls = 2


class VideoProcessStatus(IntEnum):
    """Processing lifecycle for a video asset."""

    uploaded = 1
    transcoding = 2
    ready = 3
    failed = 4


class SubmissionStatus(IntEnum):
    """Compatibility enum kept for legacy grading code."""

    not_started = 0
    in_progress = 1
    submitted = 2
    grading = 3
    reviewed = 4
    expired = 5


class GradingStatus(IntEnum):
    """Compatibility enum kept for legacy grading code."""

    pending = 0
    grading = 1
    graded = 2


class ResultStatus(IntEnum):
    """Compatibility enum kept for legacy grading code."""

    unanswered = 0
    correct = 1
    wrong = 2
    partial = 3


@register_model
class UserModel(AbstractBaseModel):
    """System account used for login and authorization."""

    __tablename__ = "user_account"

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True, nullable=False
    )
    username: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, index=True, comment="1-teacher, 2-operator"
    )
    display_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    email: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=1, comment="0-disabled, 1-using, 2-checking"
    )
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login_at: Mapped[object | None] = mapped_column(
        BeijingTimeZone(), nullable=True
    )
    remark: Mapped[str | None] = mapped_column(String(255), nullable=True)


@register_model
class GroupModel(AbstractBaseModel):
    """Fixed demo group metadata."""

    __tablename__ = "demo_group"

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True, nullable=False
    )
    group_no: Mapped[int] = mapped_column(Integer, nullable=False, unique=True, index=True)
    group_name: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


@register_model
class VideoModel(AbstractBaseModel):
    """Video asset metadata scanned from the local media directory."""

    __tablename__ = "video_asset"
    __table_args__ = (
        UniqueConstraint("file_path", name="uq_video_asset_file_path"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True, nullable=False
    )
    group_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("demo_group.id"), nullable=True, index=True
    )
    external_video_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, unique=True, index=True
    )
    video_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    access_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    source_type: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=VideoSourceType.unknown.value,
        comment="0-unknown, 1-mp4, 2-mov, 3-avi, 4-mkv",
    )
    playback_type: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=VideoPlaybackType.mp4.value,
        comment="1-mp4, 2-hls",
    )
    process_status: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=VideoProcessStatus.uploaded.value,
        comment="1-uploaded, 2-transcoding, 3-ready, 4-failed",
    )
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sync_status: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=VideoSyncStatus.pending.value,
        comment="0-pending, 1-synced, 2-missing, 3-failed",
    )
    is_available: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_scanned_at: Mapped[object | None] = mapped_column(
        BeijingTimeZone(), nullable=True
    )
    remark: Mapped[str | None] = mapped_column(String(255), nullable=True)


@register_model
class GroupVideoConfigModel(AbstractBaseModel):
    """Stored ordered video id array for a group."""

    __tablename__ = "group_video_config"
    __table_args__ = (
        UniqueConstraint("group_id", name="uq_group_video_config_group_id"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True, nullable=False
    )
    group_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("demo_group.id"), nullable=False, index=True
    )
    video_ids: Mapped[list[int]] = mapped_column(
        JSON, nullable=False, default=list, comment="Ordered video id array from frontend"
    )
    updated_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("user_account.id"), nullable=True, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


@register_model
class StudentModel(AbstractBaseModel):
    """Student login account and profile."""

    __tablename__ = "student_account"

    student_id: Mapped[int] = mapped_column(Integer, primary_key=True, nullable=False)
    group_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("demo_group.id"), nullable=False, index=True
    )
    username: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    student_name: Mapped[str] = mapped_column(String(64), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login_at: Mapped[object | None] = mapped_column(
        BeijingTimeZone(), nullable=True
    )


@register_model
class StudentTaskModel(AbstractBaseModel):
    """Per-student task assignment within a group."""

    __tablename__ = "student_task"
    __table_args__ = (
        UniqueConstraint("student_id", name="uq_student_task_student_id"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True, nullable=False
    )
    group_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("demo_group.id"), nullable=False, index=True
    )
    student_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("student_account.student_id"), nullable=False, index=True
    )
    task_content: Mapped[str] = mapped_column(Text, nullable=False)


@register_model
class StudentScriptModel(AbstractBaseModel):
    """Per-student ordered script lines."""

    __tablename__ = "student_script"
    __table_args__ = (
        UniqueConstraint("student_id", "script_order", name="uq_student_script_order"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True, nullable=False
    )
    student_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("student_account.student_id"), nullable=False, index=True
    )
    script_order: Mapped[int] = mapped_column(Integer, nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)


@register_model
class SystemLogModel(AbstractBaseModel):
    """System log persisted by the async logger."""

    __tablename__ = "system_log"

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True, nullable=False
    )
    level: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    module: Mapped[str | None] = mapped_column(String(100), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)


@register_model
class UserLogModel(AbstractBaseModel):
    """User operation log persisted by the async logger."""

    __tablename__ = "user_log"

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True, nullable=False
    )
    user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("user_account.id"), nullable=True, index=True
    )
    level: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    action: Mapped[str | None] = mapped_column(String(100), nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    trace_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)

    user = relationship("UserModel")


@register_model
class VideoSyncLogModel(AbstractBaseModel):
    """Optional log table for media directory scan results."""

    __tablename__ = "video_sync_log"

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True, nullable=False
    )
    video_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("video_asset.id"), nullable=True, index=True
    )
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    sync_status: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=VideoSyncStatus.pending.value,
        comment="0-pending, 1-synced, 2-missing, 3-failed",
    )
    message: Mapped[str | None] = mapped_column(Text, nullable=True)


# Backward-friendly aliases used by existing modules.
DigitalHumanUserModel = UserModel
VideoAssetModel = VideoModel
DemoGroupModel = GroupModel
