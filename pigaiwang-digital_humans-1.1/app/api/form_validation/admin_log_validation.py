"""管理员日志验证模块

包含系统日志、管理员日志和用户日志的请求验证模型。
"""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.common.time_ import time_now_naive


class BaseLogRequest(BaseModel):
    """日志请求基础类，包含通用的日志查询参数和验证逻辑"""

    level: None | str = Field(None, description="日志级别过滤，如 'INFO', 'ERROR'")
    start_time: None | str = Field(
        None, description="开始时间，格式 'YYYY-MM-DD HH:MM:SS'"
    )
    end_time: None | str = Field(
        None, description="结束时间，格式 'YYYY-MM-DD HH:MM:SS'"
    )
    skip: int = Field(0, ge=0, description="分页跳过的记录数，默认为 0")
    limit: int = Field(
        10, ge=1, le=10000, description="分页返回的记录数，默认为 10，最大不超过 100"
    )

    @field_validator("level")
    def validate_level(cls, v):
        valid_levels = {"DEBUG", "INFO", "WARN", "ERROR", "CRITICAL"}
        if v is not None and v not in valid_levels:
            raise ValueError(f"日志级别必须是以下之一: {', '.join(valid_levels)}")
        return v

    @field_validator("start_time")
    def validate_start_time(cls, v):
        if v is None:
            return v
        jian_yi_time = datetime.strptime(v, "%Y-%m-%d %H:%M:%S")
        if jian_yi_time > time_now_naive():
            raise ValueError("开始时间不能超过当前时间")
        return v

    @field_validator("end_time")
    def validate_end_time(cls, v):
        if v is None:
            return v
        jian_yi_time = datetime.strptime(v, "%Y-%m-%d %H:%M:%S")
        if jian_yi_time > time_now_naive():
            raise ValueError("结束时间不能超过当前时间")
        return v

    @field_validator("start_time", "end_time")
    def validate_time_range(cls, v, info):
        # 注意：这里需要修改验证逻辑，因为Pydantic V2的验证器行为有所不同
        # 这里简化处理，实际应根据具体版本调整
        start_time = info.data.get("start_time") if hasattr(info, "data") else None
        end_time = v

        if start_time and end_time:
            start_datetime = datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
            end_datetime = datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S")
            if start_datetime > end_datetime:
                raise ValueError("开始时间不能超过结束时间")
        return v


class SystemLogsRequest(BaseLogRequest):
    """系统日志请求类"""

    # 如果SystemLogsRequest不需要额外字段，则无需添加任何内容
    pass


class AdminLogsRequest(BaseLogRequest):
    """管理员日志请求类"""

    user_name: None | str = Field(None, description="管理员用户名过滤")

    @field_validator("user_name")
    def validate_user_name(cls, v):
        if v is not None and len(v) > 50:
            raise ValueError("用户名长度不能超过50个字符")
        return v


class UserLogsRequest(BaseLogRequest):
    """用户日志请求类"""

    user_name: None | str = Field(None, description="用户名过滤")

    @field_validator("user_name")
    def validate_user_name(cls, v):
        if v is not None and len(v) > 50:
            raise ValueError("用户名长度不能超过50个字符")
        return v
