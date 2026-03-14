"""Validation models for digital human demo APIs."""

from typing import Any

from pydantic import BaseModel, Field, field_validator


class GroupVideoConfigSaveRequest(BaseModel):
    """Payload for saving a group's ordered video ids."""

    video_ids: list[int] = Field(default_factory=list, description="Ordered video ids")


class DemoVideoCreateRequest(BaseModel):
    """Create a new video metadata record."""

    external_video_id: str | None = Field(default=None, max_length=64)
    video_name: str = Field(..., min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=500)
    file_path: str | None = Field(default=None, max_length=1000)


class DemoGroupVideoItemRequest(BaseModel):
    """Video item inside a frontend group payload."""

    id: str = Field(..., min_length=1, max_length=64)
    videoName: str = Field(..., min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=500)


class DemoGroupPayloadRequest(BaseModel):
    """One group payload from frontend."""

    groupId: int = Field(..., description="Fixed group id such as 1001")
    groupName: str = Field(..., min_length=1, max_length=64)
    videos: list[DemoGroupVideoItemRequest] = Field(default_factory=list)


class DemoGroupBatchConfigRequest(BaseModel):
    """Batch group payload pushed by frontend."""

    groups: list[DemoGroupPayloadRequest] = Field(default_factory=list)


class VideoQueryRequest(BaseModel):
    """Optional filters for video list APIs."""

    group_id: int | None = Field(default=None, description="Optional group id")

    @field_validator("group_id", mode="before")
    @classmethod
    def normalize_group_id(cls, value: Any) -> Any:
        if value in ("", None):
            return None
        return value
