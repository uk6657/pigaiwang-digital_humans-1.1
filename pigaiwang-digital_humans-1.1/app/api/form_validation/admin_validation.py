"""管理员操作验证模块

包含管理员登录、用户管理、角色管理等操作的请求验证模型。
"""

from datetime import datetime
from typing import Any, Literal

from fastapi import HTTPException, status
from pydantic import BaseModel, Field, field_validator

from app.api.form_validation.user_validation import (
    PhoneBase,
    UserAuthByPhonePassword,
    UserAuthByUsernamePassword,
    UserBase,
    strip_strings,
    validate_plain_password,
)
from app.auth import admin_base


class AdminLoginByUsernamePasswordRequest(UserAuthByUsernamePassword):
    device_id: str | None = Field(
        None, description="设备ID，应能唯一标识一台登录设备，以精准限制多设备登录"
    )


class AdminLoginByPhonePasswordRequest(UserAuthByPhonePassword):
    device_id: str | None = Field(
        None, description="设备ID，应能唯一标识一台登录设备，以精准限制多设备登录"
    )


class UserCheckingRequest(BaseModel):
    user_id: str = Field(..., description="用户唯一ID")
    is_pass: bool = Field(..., description="审核是否通过？True-通过，False-不通过")


class PaginationParams(BaseModel):
    skip: int = Field(0, ge=0, description="跳过记录条数，默认跳过 0 条记录")
    limit: int | None = Field(
        10,
        ge=1,
        le=10000,
        description="每页返回的最大记录数（1-100），默认为一页 10 条记录；也可以传 null，返回全部",
    )


class RetrieveUserParams(BaseModel):
    company_name_substring: str | None = Field(None, description="企业名称子串")
    phone_substring: str | None = Field(None, description="手机号子串")
    user_status: Literal[0, 1] | None = Field(
        None, description="用户状态：0-禁用，1-正常"
    )

    @field_validator("company_name_substring", "phone_substring", mode="before")
    @classmethod
    def strip_whitespace(cls, value: Any) -> Any:
        return strip_strings(value)


class RetrieveUserRequest(PaginationParams, RetrieveUserParams):
    pass


class RetrieveCheckingListParams(BaseModel):
    company_name_substring: str | None = Field(None, description="企业名称子串")

    @field_validator("company_name_substring", mode="before")
    @classmethod
    def strip_whitespace(cls, value: Any) -> Any:
        return strip_strings(value)


class RetrieveCheckingListRequest(PaginationParams, RetrieveCheckingListParams):
    pass


class RetrieveAdminParams(BaseModel):
    phone_substring: str | None = Field(None, description="手机号子串")
    user_status: Literal[0, 1] | None = Field(
        None, description="用户状态：0-禁用，1-正常"
    )

    @field_validator("phone_substring", mode="before")
    @classmethod
    def strip_whitespace(cls, value: Any) -> Any:
        return strip_strings(value)


class RetrieveAdminRequest(PaginationParams, RetrieveAdminParams):
    pass


class AddUserRequest(UserBase):
    password: str = Field(
        description="密码-至少需要8个字符、必须包含至少一个数字、一个大写字母、一个小写字母"
    )
    user_status: Literal[0, 1] = Field(..., description="用户状态：0-禁用，1-正常")

    @field_validator("password", mode="before")
    @classmethod
    def strip_whitespace(cls, value):
        return strip_strings(value)

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        validate_plain_password(value)
        return value


class DeleteUserRequest(BaseModel):
    user_id: str = Field(..., description="用户唯一ID")

    @field_validator("user_id", mode="before")
    @classmethod
    def validate_role_id(cls, value: str):
        if admin_base.check_admin_user(value):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="超级管理员不可删除"
            )
        return value


class EditUserInfoRequest(PhoneBase):
    user_id: str = Field(..., description="用户唯一ID")
    username: str = Field(
        ...,
        min_length=1,
        max_length=18,
        description="用户名-有字段唯一性约束且长度不可超过18个字符",
    )

    @field_validator("user_id", mode="before")
    @classmethod
    def validate_user_id(cls, value: str):
        if admin_base.check_admin_user(value):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="超级管理员信息不可修改"
            )
        return value


class AddAdminRequest(PhoneBase):
    username: str = Field(
        min_length=1,
        max_length=18,
        description="用户名-有字段唯一性约束且长度不可超过18个字符",
    )
    password: str = Field(
        description="密码-至少需要8个字符、必须包含至少一个数字、一个大写字母、一个小写字母"
    )
    user_status: Literal[0, 1] = Field(..., description="用户状态：0-禁用，1-正常")

    @field_validator("password", mode="before")
    @classmethod
    def strip_whitespace(cls, value):
        return strip_strings(value)

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        validate_plain_password(value)
        return value


class RetrieveTransactionRecordParams(BaseModel):
    username: str | None = Field(None, description="用户名")
    min_amount: int | None = Field(None, ge=0, description="金额区间下限")
    max_amount: int | None = Field(None, ge=0, description="金额区间上限")
    start_time: datetime | None = Field(
        None, description="检索从该时间点开始的交易记录"
    )
    end_time: datetime | None = Field(None, description="检索以该时间点终止的交易记录")
    company_name_substring: str | None = Field(None, description="企业名称子串")
    is_desc: bool = Field(
        True,
        description="默认按创建时间逆序返回记录；设为False则按创建时间顺序返回记录",
    )

    @field_validator("company_name_substring", mode="before")
    @classmethod
    def strip_whitespace(cls, value):
        return strip_strings(value)


class RetrieveTransactionRecordRequest(
    PaginationParams, RetrieveTransactionRecordParams
):
    pass


class RetrieveUsernameRequest(PaginationParams):
    username_substring: str | None = Field(None, description="用户名子串")


class HandleRoleForUserRequest(BaseModel):
    user_id: str = Field(..., description="用户唯一ID")
    role_id: str = Field(..., description="角色唯一ID")

    @field_validator("role_id", mode="before")
    @classmethod
    def validate_role_id(cls, value: str):
        if value == admin_base.admin_role_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="超级管理员才能拥有该角色",
            )
        return value

    @field_validator("user_id", mode="before")
    @classmethod
    def validate_user_id(cls, value: str):
        if admin_base.check_admin_user(value):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="超级管理员拥有所有权限，角色不可变",
            )
        return value


class UsingOrDisabledRequest(BaseModel):
    user_id: str = Field(..., description="用户唯一ID")
    user_status: Literal[0, 1] = Field(..., description="用户状态：0-禁用，1-正常")

    @field_validator("user_id", mode="before")
    @classmethod
    def validate_user_id(cls, value: str):
        if admin_base.check_admin_user(value):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="超级管理员状态不可变",
            )
        return value


class ForceLogoutUserRequest(BaseModel):
    user_id: str = Field(..., description="用户唯一ID")

    @field_validator("user_id", mode="before")
    @classmethod
    def validate_user_id(cls, value: str):
        if admin_base.check_admin_user(value):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="不可强制超级管理员下线",
            )
        return value


class ExportSystemLogsRequest(BaseModel):
    is_desc: bool = Field(
        True, description="默认按照创建时间逆序返回；为False时，按照创建时间顺序返回"
    )
    level: str | None = Field(None, description="日志级别过滤")
    start_time: datetime | None = Field(None, description="筛选日志的开始时间")
    end_time: datetime | None = Field(None, description="筛选日志的结束时间")
    total: int | None = Field(
        None, gt=0, description="导出数据的条数，当传递为null或不传时，导出全部数据"
    )


class ExportUserLogsRequest(BaseModel):
    is_desc: bool = Field(
        True, description="默认按照创建时间逆序返回；为False时，按照创建时间顺序返回"
    )
    user_name: str | None = Field(None, description="用户名过滤")
    level: str | None = Field(None, description="日志级别过滤")
    start_time: datetime | None = Field(None, description="筛选日志的开始时间")
    end_time: datetime | None = Field(None, description="筛选日志的结束时间")
    total: int | None = Field(
        None, gt=0, description="导出数据的条数，当传递为null或不传时，导出全部数据"
    )


class GetUserStatisticsRequest(BaseModel):
    username: str | None = Field(None, description="完整用户名")


class TargetYearStatisticsRequest(BaseModel):
    target_year: int | None = Field(
        None, description="目标年份，如果为None时，则表示为当前年份"
    )
