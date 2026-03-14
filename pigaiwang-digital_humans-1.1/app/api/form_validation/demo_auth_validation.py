"""Validation models for the digital human demo auth APIs."""

from typing import Any

from pydantic import BaseModel, Field, field_validator


def _strip_string(value: Any) -> Any:
    if isinstance(value, str):
        return value.strip()
    return value


class DemoLoginRequest(BaseModel):
    """Minimal login payload for the demo system."""

    username: str = Field(..., min_length=1, max_length=64, description="Username")
    password: str = Field(..., min_length=1, max_length=128, description="Password")
    device_id: str | None = Field(None, description="Optional device identifier")

    @field_validator("username", "password", mode="before")
    @classmethod
    def strip_fields(cls, value: Any) -> Any:
        return _strip_string(value)
