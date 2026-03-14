"""用户验证模块

包含用户注册、登录、信息修改等操作的请求验证模型。
"""

import re
from datetime import datetime
from typing import Any, Literal

from fastapi import HTTPException, status
from phonenumbers import PhoneNumberFormat, format_number, parse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_extra_types.phone_numbers import PhoneNumber


class PhoneBase(BaseModel):
    phone: PhoneNumber = Field(description="中国手机号码")

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str) -> str:
        # 先解析 pydantic-extra-types 给出来的字符串
        number = parse(value, None)
        # 格式化成 E.164 纯净格式（+86xxx）
        value_str = format_number(number, PhoneNumberFormat.E164)
        validate_chinese_phone(value_str)
        print("value_str", value_str)
        return value_str


class UserBase(PhoneBase):
    username: str = Field(
        min_length=1,
        max_length=18,
        description="用户名-有字段唯一性约束且长度不可超过18个字符",
    )

    @field_validator("username", mode="before")
    @classmethod
    def strip_whitespace(cls, value):
        return strip_strings(value)

    model_config = ConfigDict(from_attributes=True)


class UserCreateRequest(UserBase):
    password: str = Field(
        description="密码-至少需要8个字符、必须包含至少一个数字、一个大写字母、一个小写字母"
    )
    verification_code: str = Field(description="手机验证码")

    @field_validator("password", "verification_code", mode="before")
    @classmethod
    def strip_whitespace(cls, value):
        return strip_strings(value)

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        validate_plain_password(value)
        return value

    @field_validator("verification_code")
    @classmethod
    def validate_verification_code(cls, value: str) -> str:
        validate_verification_code(value)
        return value


class PasswordAuthBase(BaseModel):
    """使用密码进行验证的基类"""

    password: str = Field(description="密码")
    image_code: str = Field(description="图形数字验证码")
    image_id: str = Field(description="数字图形唯一ID")

    @field_validator("password", "image_code", mode="before")
    @classmethod
    def strip_common_whitespace(cls, value: Any):
        return strip_strings(value)

    @field_validator("password")
    @classmethod
    def validate_password_format(cls, value: str) -> str:
        try:
            validate_plain_password(value)
            return value
        except Exception:
            # 统一报错信息，增加安全性，防止探测账号是否存在
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="用户名或密码错误"
            )


class UserAuthByUsernamePassword(PasswordAuthBase):
    """用户名密码登录：继承 PasswordAuthBase"""

    username: str = Field(description="用户名")

    @field_validator("username", mode="before")
    @classmethod
    def strip_username_whitespace(cls, value: Any):
        return strip_strings(value)

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        if not (0 < len(value) <= 50):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="用户名或密码错误"
            )
        return value


class UserAuthByPhonePassword(PhoneBase, PasswordAuthBase):
    """手机号密码登录：多继承 PhoneBase (处理手机) 和 PasswordAuthBase (处理密码验证码)"""

    pass


class ForgotPasswordRequest(PhoneBase):
    verification_code: str = Field(description="手机验证码")
    new_password: str = Field(
        description="密码-至少需要8个字符、必须包含至少一个数字、一个大写字母、一个小写字母"
    )

    @field_validator("verification_code", "new_password", mode="before")
    @classmethod
    def strip_whitespace(cls, value):
        return strip_strings(value)

    @field_validator("verification_code")
    @classmethod
    def validate_verification_code(cls, value: str) -> str:
        validate_verification_code(value)
        return value

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, value):
        validate_plain_password(value)
        return value


class VerificationCodeRequest(PhoneBase):
    pass


class VerifyVerificationCodeRequest(PhoneBase):
    verification_code: str = Field(description="手机验证码")

    @field_validator("verification_code", mode="before")
    @classmethod
    def strip_whitespace(cls, value: Any):
        return strip_strings(value)

    @field_validator("verification_code")
    @classmethod
    def validate_verification_code(cls, value: str):
        validate_verification_code(value)
        return value


class ChangeBindedPhoneRequest(PhoneBase):
    verification_code: str = Field(description="手机验证码")

    @field_validator("verification_code", mode="before")
    @classmethod
    def strip_whitespace(cls, value: Any):
        return strip_strings(value)

    @field_validator("verification_code")
    @classmethod
    def validate_verification_code(cls, value: str):
        validate_verification_code(value)
        return value


# class ChangeUserInfoRequest(BaseModel):


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(description="用户旧密码")
    new_password: str = Field(description="用户新密码")

    @field_validator("old_password", "new_password", mode="before")
    @classmethod
    def strip_whitespace(cls, value):
        return strip_strings(value)

    @field_validator("old_password", "new_password")
    @classmethod
    def validate_password(cls, value: str):
        validate_plain_password(value)
        return value


class UserUpdateRequest(BaseModel):
    username: str = Field(
        min_length=1,
        max_length=18,
        description="用户名-有字段唯一性约束且长度不可超过18个字符",
    )

    @field_validator("username", mode="before")
    @classmethod
    def strip_whitespace(cls, value):
        return strip_strings(value)


class ExportTransactionsRequest(BaseModel):
    transaction_type: Literal[1, 2] | None = Field(
        None, description="交易类型：1-充值，2-消费"
    )
    is_desc: bool = Field(
        True, description="默认按照创建时间逆序返回；为False时，按照创建时间顺序返回"
    )
    start_time: datetime | None = Field(None, description="筛选账单的起始日期")
    end_time: datetime | None = Field(None, description="筛选账单的结束日期")
    total: int | None = Field(
        None, gt=0, description="导出数据的条数，当传递为null或不传时，导出全部数据"
    )


def validate_plain_password(password: str) -> None:
    # 验证密码长度
    if len(password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="密码至少需要8个字符"
        )

    # 至少包含一个数字
    if not re.search(r"\d", password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="密码必须包含至少一个数字"
        )

    # 至少包含一个大写字母
    if not re.search(r"[A-Z]", password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="密码必须包含至少一个大写字母",
        )

    # 至少包含一个小写字母
    if not re.search(r"[a-z]", password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="密码必须包含至少一个小写字母",
        )


# 去除字符串类型字段值的首尾空格
def strip_strings(value: Any) -> Any:
    if isinstance(value, str):
        return value.strip()
    return value


def validate_verification_code(verification_code: str) -> None:
    if len(verification_code) != 4 and len(verification_code) != 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="手机验证码错误"
        )


def validate_chinese_phone(phone: str):
    if not phone.startswith("+86"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="请输入中国大陆的手机号码"
        )
