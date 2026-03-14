"""用户表单验证模块。

定义用户相关的请求数据验证模型。
"""

import re
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class UserCreateRequest(BaseModel):
    """用户创建请求模型。"""

    username: str = Field(
        ..., min_length=1, max_length=50, description="用户名（唯一标识，可用于登录）"
    )
    password: str = Field(
        ..., min_length=6, max_length=100, description="密码（至少6位）"
    )
    phone: str = Field(..., max_length=50, description="手机号（唯一，用于找回密码）")
    is_admin: Optional[bool] = Field(
        default=False, description="是否为管理员（默认false）"
    )

    @field_validator("username")
    @classmethod
    def validate_username(cls, v):
        """验证用户名格式。"""
        v = v.strip()
        if not v:
            raise ValueError("用户名不能为空")
        # 用户名只能包含字母、数字、下划线
        if not re.match(r"^[a-zA-Z0-9_]+$", v):
            raise ValueError("用户名只能包含字母、数字和下划线")
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v):
        """验证密码强度。"""
        v = v.strip()
        if len(v) < 6:
            raise ValueError("密码长度至少6位")
        # 可选：密码强度验证
        # if not any(c.isdigit() for c in v):
        #     raise ValueError("密码必须包含至少一个数字")
        # if not any(c.isalpha() for c in v):
        #     raise ValueError("密码必须包含至少一个字母")
        return v

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v):
        """验证手机号格式。"""
        v = v.strip()
        if not v:
            raise ValueError("手机号不能为空")
        # 中国大陆手机号验证（11位数字，1开头）
        if not re.match(r"^1[3-9]\d{9}$", v):
            raise ValueError("手机号格式不正确")
        return v

    # @validator('status')
    # def validate_status(cls, v):
    #     """验证状态值。"""
    #     if v not in [0, 1, 2]:
    #         raise ValueError("状态值必须是0、1或2")
    #     return v


class UserListRequest(BaseModel):
    """用户列表查询请求模型。"""

    username: Optional[str] = Field(None, description="用户名（模糊查询）")
    phone: Optional[str] = Field(None, description="手机号（模糊查询）")
    status: Optional[int] = Field(
        None, ge=0, le=2, description="状态：0-禁用，1-正常，2-待审核"
    )
    is_admin: Optional[bool] = Field(None, description="是否为管理员")
    page: int = Field(1, ge=1, description="页码（从1开始）")
    page_size: int = Field(10, ge=1, le=10000, description="每页数量（1-100）")
    sort_by: Optional[str] = Field(
        "created_at", description="排序字段（created_at、last_login_at、username等）"
    )
    is_desc: Optional[bool] = Field(True, description="是否降序排列")
    keyword: Optional[str] = Field(
        default=None, description="搜索关键词（同时搜索用户名和手机号）"
    )

    @field_validator("page_size")
    @classmethod
    def validate_page_size(cls, v: int) -> int:
        """验证每页数量。"""
        if v > 100:
            return 100
        return v

    @field_validator("username", "phone")
    @classmethod
    def empty_str_to_none(cls, v: Optional[str]) -> Optional[str]:
        """将空字符串转换为None，确保不传或传空字符串时都能查询全部。"""
        if v is None or v.strip() == "":
            return None
        return v.strip()


class UserStatusUpdateRequest(BaseModel):
    """用户状态更新请求模型。"""

    id: str = Field(..., min_length=1, description="用户ID（雪花ID）")
    status: int = Field(..., ge=0, le=2, description="状态：0-禁用，1-正常，2-待审核")


class UserUpdateRequest(BaseModel):
    """用户更新请求模型。"""

    id: str = Field(..., min_length=1, description="用户ID（雪花ID）")

    username: Optional[str] = Field(
        None, min_length=1, max_length=50, description="用户名（唯一标识，可用于登录）"
    )
    password: Optional[str] = Field(
        None, min_length=6, max_length=100, description="密码（至少6位）"
    )
    phone: Optional[str] = Field(
        None, max_length=50, description="手机号（唯一，用于找回密码）"
    )
    status: Optional[int] = Field(
        None, ge=0, le=2, description="状态：0-禁用，1-正常，2-待审核"
    )
    is_admin: Optional[bool] = Field(None, description="是否为管理员")

    @field_validator("username")
    @classmethod
    def validate_username(cls, v, values):
        """验证用户名格式。"""
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError("用户名不能为空")
            if not re.match(r"^[a-zA-Z0-9_]+$", v):
                raise ValueError("用户名只能包含字母、数字和下划线")
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            if len(v) < 6:
                raise ValueError("密码长度至少6位")
        return v

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            # 如果更新时不传phone或传null，不验证；传了就必须符合格式
            if v and not re.match(r"^1[3-9]\d{9}$", v):
                raise ValueError("手机号格式不正确")
        return v


class UserDetailRequest(BaseModel):
    """用户详情查询请求模型。"""

    id: str = Field(..., min_length=1, description="用户ID（雪花ID）")

    @field_validator("id")
    @classmethod
    def validate_id(cls, v):
        """验证ID格式。"""
        v = v.strip()
        if not v:
            raise ValueError("用户ID不能为空")
        if not v.isdigit() or len(v) > 19:
            raise ValueError("用户ID格式不正确")
        return v


class UserDeleteRequest(BaseModel):
    """用户删除请求模型。"""

    id: str = Field(..., min_length=1, description="用户ID（雪花ID）")

    @field_validator("id")
    @classmethod
    def validate_id(cls, v):
        """验证ID格式。"""
        v = v.strip()
        if not v:
            raise ValueError("用户ID不能为空")
        if not v.isdigit() or len(v) > 19:
            raise ValueError("用户ID格式不正确")
        return v
