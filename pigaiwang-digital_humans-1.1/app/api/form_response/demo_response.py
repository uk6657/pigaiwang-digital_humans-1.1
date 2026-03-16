"""Response models for digital human demo APIs."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DemoUserResponseModel(BaseModel):
    """Current user information."""

    id: str = Field(description="User id")
    username: str = Field(description="Username")
    type: int = Field(description="1-teacher, 2-operator")
    display_name: str | None = Field(default=None, description="Display name")

    model_config = ConfigDict(from_attributes=True)


class DemoGroupResponseModel(BaseModel):
    """Group metadata."""

    id: int = Field(description="Group id")
    group_no: int = Field(description="Group number")
    group_name: str = Field(description="Group name")
    description: str | None = Field(default=None, description="Description")
    is_active: bool = Field(description="Whether the group is active")

    model_config = ConfigDict(from_attributes=True)


class DemoVideoResponseModel(BaseModel):
    """Video resource metadata."""

    id: int = Field(description="Video id")
    group_id: int | None = Field(default=None, description="Compatibility group id")
    external_video_id: str | None = Field(default=None, description="External video id from frontend")
    video_name: str = Field(description="Video name")
    description: str | None = Field(default=None, description="Video description")
    file_name: str = Field(description="File name")
    file_path: str = Field(description="Local file path")
    access_url: str | None = Field(default=None, description="Playback URL")
    source_type: int = Field(description="Original source file type")
    stream_url: str | None = Field(default=None, description="Direct mp4 stream URL")
    hls_url: str | None = Field(default=None, description="HLS m3u8 URL")
    playback_type: int = Field(description="Preferred playback type")
    process_status: int = Field(description="Video processing lifecycle status")
    duration_seconds: int | None = Field(default=None, description="Duration in seconds")
    file_size_bytes: int | None = Field(default=None, description="File size in bytes")
    mime_type: str | None = Field(default=None, description="Mime type")
    is_available: bool = Field(description="Whether file is currently available")
    created_at: datetime = Field(description="Created at")
    updated_at: datetime = Field(description="Updated at")

    model_config = ConfigDict(from_attributes=True)


class DemoGroupVideoConfigResponseModel(BaseModel):
    """Ordered group video configuration."""

    group_id: int = Field(description="Group id")
    video_ids: list[int] = Field(description="Ordered video ids")
    videos: list[DemoVideoResponseModel] = Field(description="Ordered video objects")


class DemoGroupBatchConfigResponseModel(BaseModel):
    """Batch group config response."""

    groups: list[DemoGroupVideoConfigResponseModel] = Field(description="Saved group configs")


class VideoCacheItemResponseModel(BaseModel):
    """Video cache/download metadata for local sync clients."""

    video_id: int = Field(description="Video id")
    external_video_id: str | None = Field(default=None, description="External video id")
    video_name: str = Field(description="Video name")
    file_name: str = Field(description="Original file name")
    file_size_bytes: int | None = Field(default=None, description="File size in bytes")
    mime_type: str | None = Field(default=None, description="Mime type")
    updated_at: datetime = Field(description="Last metadata update time")
    download_url: str = Field(description="Direct download URL for the source file")


class VideoCacheManifestResponseModel(BaseModel):
    """Cache manifest for all downloadable videos."""

    videos: list[VideoCacheItemResponseModel] = Field(description="All downloadable videos")


class VideoCacheVersionItemResponseModel(BaseModel):
    """Compact video version information for local cache checks."""

    video_id: int = Field(description="Video id")
    updated_at: datetime = Field(description="Last metadata update time")
    file_size_bytes: int | None = Field(default=None, description="File size in bytes")


class VideoCacheVersionResponseModel(BaseModel):
    """Compact version list for cache synchronization."""

    videos: list[VideoCacheVersionItemResponseModel] = Field(
        description="Compact cache version info"
    )
