"""数据库基础模块.

提供SQLAlchemy异步数据库的基础设施：
- 异步数据库引擎和会话管理
- 声明式基类定义
- 时区处理工具类
- 模型注册机制
- 数据库连接配置

支持UTC时间存储和自动时区转换。
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import BigInteger, Boolean
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Mapped, declarative_base, mapped_column
from sqlalchemy.types import DateTime, TypeDecorator

from app.common.time_ import time_now, zone_info
from app.configs import base_configs

# 定义基类
Base = declarative_base()

_model_registry = []

utc_tz = ZoneInfo("UTC")  # UTC 时区


def register_model(cls):
    """注册数据库模型.

    将模型类添加到注册表中，用于后续的数据库初始化。

    Args:
        cls: 要注册的模型类

    Returns:
        注册的模型类（装饰器模式）
    """
    _model_registry.append(cls)
    return cls


class StringifiedBigInt(TypeDecorator):
    """自定义类型装饰器，实现 Python 字符串与数据库 BigInteger 的双向转换。

    该类型在 Python 端表现为字符串类型，在数据库端存储为 BigInteger 类型。
    主要用于处理 JavaScript 等前端语言无法精确表示大整数的场景。

    Attributes:
        impl: SQLAlchemy 底层实现类型，使用 BigInteger。
        cache_ok: 表示该类型装饰器可以被缓存。

    Example:
        >>> class MyModel(Base):
        ...     id: Mapped[str] = mapped_column(StringifiedBigInt, primary_key=True)
    """

    impl = BigInteger
    cache_ok = True

    def process_bind_param(self, value, dialect):
        """将 Python 值转换为数据库值（写入时调用）。

        Args:
            value: Python 端的值，可以是 None、int 或 str 类型。
            dialect: SQLAlchemy 数据库方言对象。

        Returns:
            转换后的整数值，如果输入为 None 则返回 None。

        Raises:
            ValueError: 当 value 无法转换为整数时抛出。
        """
        if value is None:
            return None
        if isinstance(value, int):
            return value
        try:
            return int(value)
        except (ValueError, TypeError) as e:
            raise ValueError(f"StringifiedBigInt 无法转换值 '{value}' 为整数") from e

    def process_result_value(self, value, dialect):
        """将数据库值转换为 Python 值（读取时调用）。

        Args:
            value: 数据库返回的整数值，可能为 None。
            dialect: SQLAlchemy 数据库方言对象。

        Returns:
            转换后的字符串值，如果输入为 None 则返回 None。
        """
        if value is None:
            return None
        return str(value)


class BeijingTimeZone(TypeDecorator):
    """自动将数据库中的 UTC 时间转为 Asia/Shanghai.

    继承自 SQLAlchemy 的 TypeDecorator，用于处理时区转换。
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        """将 Python 值转换为数据库值（写入时调用）。

        统一将时间转换为 UTC 后存入数据库。

        Args:
            value: Python 端的 datetime 对象，可能带或不带时区信息。
            dialect: SQLAlchemy 数据库方言对象。

        Returns:
            转换为 UTC 的 datetime 对象，如果输入为 None 则返回 None。
        """
        if value is None:
            return None
        if value.tzinfo is None:
            # naive datetime，假设为北京时间
            value = value.replace(tzinfo=zone_info)
        return value.astimezone(utc_tz)

    def process_result_value(self, value, dialect):
        """处理从数据库读取的时间值.

        将数据库中的 UTC 时间转换为北京时间。

        Args:
            value: 数据库返回的时间值
            dialect: 数据库方言

        Returns:
            转换为北京时间的 datetime 对象，如果输入为 None 则返回 None
        """
        # 从数据库取出时，统一转为北京时间
        if value is not None:
            if value.tzinfo is None:
                # 数据库返回 naive 时间，手动附加 UTC 再转
                value = value.replace(tzinfo=utc_tz)
            return value.astimezone(zone_info)
        return value


# 定义基类
class AbstractBaseModel(Base):
    """所有数据库模型的抽象基类.

    提供通用字段：软删除标记、创建时间、更新时间。
    继承此类的模型将自动拥有这些字段，无需重复定义。
    """

    # 声明这是一个抽象基类，不会对应真实的数据表
    __abstract__ = True

    # 创建时间，自动设置为当前北京时间（Asia/Shanghai）
    created_at: Mapped["datetime"] = mapped_column(
        BeijingTimeZone(),
        default=time_now,  # 使用自定义函数获取带时区的当前时间
        nullable=False,
        index=True,
        comment="创建时间（北京时间）",
    )

    # 更新时间，记录最后一次修改的时间
    updated_at: Mapped["datetime"] = mapped_column(
        BeijingTimeZone(),
        default=time_now,  # 新建时也设置为当前时间
        nullable=False,
        index=True,
        comment="更新时间（北京时间）",
        onupdate=time_now,
    )

    # 软删除标记
    is_deleted: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="是否被删除：False-未删除，True-已删除",
    )


# 创建异步数据库引擎
engine: AsyncEngine = create_async_engine(
    base_configs.DATABASE_URL, echo=base_configs.DATABASE_ECHO
)

# 创建异步数据库会话工厂
AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine, class_=AsyncSession, expire_on_commit=False
)


# 创建所有数据表
async def init_db():
    """初始化数据库.

    创建所有已注册的数据表。
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def stop_db():
    """关闭数据库连接.

    关闭数据库连接。
    """
    await engine.dispose()
