"""用户API响应模型定义。

包含用户列表、详情等响应的数据结构定义。
"""

from datetime import datetime
from typing import Any, List, Optional, Union

from pydantic import BaseModel, Field


class UserBaseResponse(BaseModel):
    """用户基础信息响应"""

    id: str
    username: str
    phone: str
    status: int
    is_admin: bool
    created_at: Optional[datetime] = None


# 定义通用的响应模型
class BaseResponse(BaseModel):
    res: bool
    code: int
    message: str
    data: Union[dict, None] = None


# 用户创建响应
class UserCreateResponse(BaseResponse):
    pass  # 可以继承BaseResponse，不需要额外字段


class UserDetailInfoResponse(BaseModel):
    """用户详情信息响应"""

    id: str
    username: str
    phone: str
    status: int
    is_admin: bool


class UserDetailResponse(BaseModel):
    """用户详情响应"""

    res: bool = Field(..., description="操作是否成功")
    code: int = Field(..., description="业务状态码")
    message: str = Field(..., description="响应消息")
    data: UserDetailInfoResponse


class UserListResponse(BaseModel):
    """用户列表响应"""

    res: bool = Field(..., description="操作是否成功")
    code: int = Field(..., description="业务状态码")
    total: int
    skip: int = 0
    limit: int = 10
    data: dict


class UserListData(BaseModel):
    """用户列表数据"""

    items: List[UserBaseResponse]


class Config:
    """Pydantic模型配置类

    Attributes:
        from_attributes: 允许从ORM对象属性自动转换
    """

    from_attributes = True


# class UserUpdateRequest(BaseModel):
#     """用户更新请求"""
#     id: str
#     username: str
#     phone: Optional[str] = None
#     status: Optional[int] = Field(None, ge=0, le=2)
#     is_admin: Optional[bool] = None
#     updated_at: str


class UserInfo(BaseModel):
    """用户信息响应模型"""

    id: str
    username: str
    phone: str
    status: int
    is_admin: bool
    updated_at: Optional[str] = Field(None, description="更新时间（ISO 8601格式）")

    class Config:
        """Pydantic模型配置"""

        from_attributes = True


class UserUpdateResponse(BaseModel):
    """用户更新响应"""

    res: bool = Field(True, description="操作是否成功")
    code: int = Field(200, description="业务状态码")
    message: str = Field("user updated", description="响应消息")
    data: Optional[UserInfo] = Field(None, description="用户数据")


class UserStatusUpdateResponse(BaseModel):
    """用户状态更新响应"""

    res: bool = True
    code: int = 200
    message: str = "用户状态更新成功"


class UserDeleteResponse(BaseModel):
    """用户删除响应"""

    res: bool = True
    code: int = 200
    message: str = "user deleted"
    data: Optional[Any] = Field(default=None)
