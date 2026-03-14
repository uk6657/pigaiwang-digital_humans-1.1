"""返回校验的基类"""

from typing import Generic, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class BaseResponseModel(BaseModel, Generic[T]):
    """基本响应模型."""

    res: bool = Field(default=True, description="Response status")
    code: int = Field(default=200, description="Response status code")
    message: str = Field(default="success", description="Response message")
    data: Optional[T] = Field(None, description="Response data")  # type: ignore


class PaginatedResponseModel(BaseResponseModel, Generic[T]):
    """分页响应模型

    - `total`: 记录总数
    - `skip`: 跳过的记录数（用于分页偏移）
    - `limit`: 每页返回的最大记录数
    """

    total: int | None = Field(
        default=None, title="总记录数", description="符合条件的总记录数"
    )
    skip: int = Field(title="当前页码", description="当前请求的页码")
    limit: int | None = Field(
        default=None, title="每页大小", description="每页返回的记录数"
    )


class BaseResponseModelWithTotal(BaseResponseModel, Generic[T]):
    """带总数的响应模型（不分页）

    - `total`: 记录总数
    """

    total: int | None = Field(
        default=None, title="总记录数", description="符合条件的总记录数"
    )
