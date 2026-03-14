"""admin_log相关返回校验"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SystemLogResponseModel(BaseModel):
    id: str = Field(..., description="日志 ID")
    level: str = Field(..., description="日志级别")
    message: str = Field(..., description="日志信息")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")

    model_config = ConfigDict(from_attributes=True)


class AdminLogResponseModel(BaseModel):
    id: str = Field(..., description="日志 ID")
    user_id: str = Field(..., description="管理员用户 ID")
    user_name: str = Field(..., description="管理员用户名")
    level: str = Field(..., description="日志级别")
    message: str = Field(..., description="日志信息")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")

    model_config = ConfigDict(from_attributes=True)


class UserLogResponseModel(BaseModel):
    id: str = Field(..., description="日志 ID")
    user_id: str = Field(..., description="用户 ID")
    user_name: str = Field(..., description="用户名")
    level: str = Field(..., description="日志级别")
    message: str = Field(..., description="日志信息")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")

    model_config = ConfigDict(from_attributes=True)
