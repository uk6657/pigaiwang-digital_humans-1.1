"""Validation models for student and task APIs."""

from typing import Any

from pydantic import BaseModel, Field, field_validator


def _strip_string(value: Any) -> Any:
    if isinstance(value, str):
        return value.strip()
    return value


class StudentLoginRequest(BaseModel):
    """Student login payload."""

    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=128)
    device_id: str | None = Field(default=None)

    @field_validator("username", "password", mode="before")
    @classmethod
    def strip_fields(cls, value: Any) -> Any:
        return _strip_string(value)


class StudentRenameRequest(BaseModel):
    """Student rename payload."""

    student_name: str = Field(..., min_length=1, max_length=64)

    @field_validator("student_name", mode="before")
    @classmethod
    def strip_name(cls, value: Any) -> Any:
        return _strip_string(value)


class StudentTaskEntryRequest(BaseModel):
    """Task entry for one student."""

    studentId: int = Field(..., description="Student id such as 11")
    studentName: str = Field(..., min_length=1, max_length=64, description="Student name")
    task: str = Field(..., min_length=1)


class GroupTaskPayloadRequest(BaseModel):
    """Task payload for one group."""

    groupId: int = Field(..., description="Fixed group id such as 1001")
    groupName: str = Field(..., min_length=1, max_length=64)
    students: list[StudentTaskEntryRequest] = Field(default_factory=list)


class StudentScriptLineRequest(BaseModel):
    """One ordered line in a student's script."""

    order: int = Field(..., ge=1)
    question: str = Field(..., min_length=1)
    answer: str = Field(..., min_length=1)


class TaskScriptBatchRequest(BaseModel):
    """Full task/script configuration payload."""

    tasks: list[GroupTaskPayloadRequest] = Field(default_factory=list)
    scripts: dict[str, list[StudentScriptLineRequest]] = Field(default_factory=dict)
