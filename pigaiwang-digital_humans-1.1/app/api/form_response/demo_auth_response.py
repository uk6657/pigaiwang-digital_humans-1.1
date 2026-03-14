"""Response models for the digital human demo auth APIs."""

from pydantic import BaseModel, ConfigDict, Field

from app.auth.jwt_manager import TokenInfo


class DemoLoginUserResponseModel(BaseModel):
    """Logged-in user summary."""

    id: str = Field(description="User id")
    username: str = Field(description="Username")
    type: int = Field(description="1-teacher, 2-operator")
    display_name: str | None = Field(default=None, description="Display name")

    model_config = ConfigDict(from_attributes=True)


class DemoLoginResponseModel(BaseModel):
    """Login response payload."""

    user: DemoLoginUserResponseModel = Field(description="Current user")
    token_info: TokenInfo = Field(description="Access token info")

