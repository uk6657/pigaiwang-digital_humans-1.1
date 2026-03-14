"""管理员日志服务模块。.

该模块提供了系统日志、管理员日志和普通用户日志的查询功能。
支持分页查询、条件筛选和日志导出等功能。
"""

from datetime import datetime

from sqlalchemy import and_, func, literal, select, text, union_all

from app.common.time_ import to_naive_beijing
from app.storage import (
    SystemLogModel,
    UserLogModel,
)
from app.storage.base import AsyncSessionLocal
from app.storage.database_models import UserModel


class AdminLogService:
    """管理员日志服务类。.

    提供系统日志、管理员日志和普通用户日志的查询和管理功能。
    支持按时间范围、日志级别、用户名等条件进行筛选。
    """

    async def get_system_logs(
        self,
        level: None | str = None,
        start_time: None | str = None,
        end_time: None | str = None,
        skip: int = 0,
        limit: int = 10,
    ) -> tuple[bool, int, str, int, list]:
        """分页查询系统日志。.

        根据筛选条件查询系统日志，支持按日志级别、时间范围筛选。

        Args:
            level: 日志级别筛选（INFO、WARNING、ERROR等），可选
            start_time: 开始时间，ISO格式字符串，可选
            end_time: 结束时间，ISO格式字符串，可选
            skip: 跳过的记录数，默认为0
            limit: 限制返回的记录数，默认为10

        Returns:
            返回元组包含：
            - bool: 操作是否成功
            - int: HTTP状态码
            - str: 响应消息
            - int: 总记录数
            - list: 系统日志列表

        Raises:
            Exception: 数据库查询异常时可能抛出
        """
        # 这里是一个示例实现，实际逻辑根据需求调整
        async with AsyncSessionLocal() as db:
            try:
                conditions = []
                if level:
                    conditions.append(SystemLogModel.level == level)
                if start_time:
                    start_time = to_naive_beijing(datetime.fromisoformat(start_time))
                    conditions.append(SystemLogModel.created_at >= start_time)
                if end_time:
                    end_time = to_naive_beijing(datetime.fromisoformat(end_time))
                    conditions.append(SystemLogModel.created_at <= end_time)

                total_result = await db.execute(
                    select(func.count())
                    .select_from(SystemLogModel)
                    .where(and_(*conditions))
                )
                total = total_result.scalar()

                result = await db.execute(
                    select(SystemLogModel)
                    .where(and_(*conditions))
                    .order_by(SystemLogModel.created_at.desc())
                    .offset(skip)
                    .limit(limit)
                )
                logs = result.scalars().all()

                return True, 200, "获取系统日志成功", total, logs
            except Exception as e:
                return False, 500, f"获取系统日志失败: {str(e)}", 0, []

    async def get_system_log_by_id(
        self, log_id: str
    ) -> tuple[bool, int, str, SystemLogModel | None]:
        """根据ID获取系统日志详情。.

        通过日志ID查询单条系统日志的详细信息。

        Args:
            log_id: 系统日志ID

        Returns:
            返回元组包含：
            - bool: 操作是否成功
            - int: HTTP状态码
            - str: 响应消息
            - SystemLogModel | None: 系统日志对象，未找到时为None

        Raises:
            Exception: 数据库查询异常时可能抛出
        """
        async with AsyncSessionLocal() as db:
            try:
                result = await db.execute(
                    select(SystemLogModel).where(SystemLogModel.id == log_id)
                )
                log = result.scalars().first()
                if log:
                    return True, 200, "获取系统日志成功", log
                else:
                    return False, 404, "未找到对应的系统日志", None
            except Exception as e:
                return False, 500, f"获取系统日志失败: {str(e)}", None

    async def get_admin_logs(
        self,
        user_name: None | str = None,
        level: None | str = None,
        start_time: None | str = None,
        end_time: None | str = None,
        skip: int = 0,
        limit: int = 10,
    ) -> tuple[bool, int, str, int, list]:
        """分页查询管理员日志。.

        查询所有管理的操作日志。
        支持按用户名、日志级别、时间范围筛选。

        Args:
            user_name: 管理员用户名模糊匹配，可选
            level: 日志级别筛选（INFO、WARNING、ERROR等），可选
            start_time: 开始时间，ISO格式字符串，可选
            end_time: 结束时间，ISO格式字符串，可选
            skip: 跳过的记录数，默认为0
            limit: 限制返回的记录数，默认为10

        Returns:
            返回元组包含：
            - bool: 操作是否成功
            - int: HTTP状态码
            - str: 响应消息
            - int: 总记录数
            - list: 管理员日志列表，包含用户名等详细信息

        Raises:
            Exception: 数据库查询异常时可能抛出
        """
        async with AsyncSessionLocal() as db:
            try:
                # 条件列表
                conditions = []

                # 添加其他查询条件
                if user_name:
                    conditions.append(
                        UserModel.username.like(f"%{user_name}%")
                    )  # 注意字段名是 username

                if level:
                    conditions.append(UserLogModel.level == level)

                if start_time:
                    start_dt = to_naive_beijing(datetime.fromisoformat(start_time))
                    conditions.append(UserLogModel.created_at >= start_dt)

                if end_time:
                    end_dt = to_naive_beijing(datetime.fromisoformat(end_time))
                    conditions.append(UserLogModel.created_at <= end_dt)

                # === 总数查询（必须 join）===
                total_query = (
                    select(func.count())
                    .select_from(UserLogModel)
                    .join(UserLogModel.user)  # 必须 join 才能访问 UserModel 字段
                    .where(and_(*conditions))
                )
                total_result = await db.execute(total_query)
                total = total_result.scalar_one()

                # === 数据查询（带 join 和排序）===
                result = await db.execute(
                    select(UserLogModel)
                    .join(UserLogModel.user)  # 必须 join
                    .where(and_(*conditions))
                    .order_by(UserLogModel.created_at.desc())
                    .offset(skip)
                    .limit(limit)
                )
                logs = result.scalars().all()

                # 构造返回数据
                data = [
                    {
                        "id": log.id,
                        "user_id": log.user_id,
                        "user_name": log.user.username,  # 注意字段名是 username
                        "level": log.level,
                        "message": log.message,
                        "created_at": log.created_at,
                        "updated_at": log.updated_at,
                    }
                    for log in logs
                ]

                return True, 200, "获取管理日志成功", total, data
            except Exception as e:
                return False, 500, f"获取管理日志失败: {str(e)}", 0, []

    async def get_admin_log_by_id(
        self, log_id: str
    ) -> tuple[bool, int, str, dict | None]:
        """根据ID获取管理员日志详情。.

        通过日志ID查询单条管理员日志的详细信息。
        只能查询管理员（company_id为None）的日志。

        Args:
            log_id: 用户日志ID

        Returns:
            返回元组包含：
            - bool: 操作是否成功
            - int: HTTP状态码
            - str: 响应消息
            - dict | None: 管理员日志详情，未找到时为None

        Raises:
            Exception: 数据库查询异常时可能抛出
        """
        async with AsyncSessionLocal() as db:
            try:
                result = await db.execute(
                    select(UserLogModel)
                    .join(UserLogModel.user)
                    .where(UserLogModel.id == log_id)
                )
                log = result.scalars().first()

                if not log:
                    return False, 404, "未找到对应的管理日志", None

                data = {
                    "id": log.id,
                    "user_id": log.user_id,
                    "user_name": log.user.username,
                    "level": log.level,
                    "message": log.message,
                    "created_at": log.created_at,
                    "updated_at": log.updated_at,
                }
                return True, 200, "获取管理日志成功", data
            except Exception as e:
                # 可选：记录日志
                return False, 500, f"查询失败: {str(e)}", None

    async def get_user_logs(
        self,
        user_name: None | str = None,
        level: None | str = None,
        start_time: None | str = None,
        end_time: None | str = None,
        skip: int = 0,
        limit: int = 10,
    ) -> tuple[bool, int, str, int, list]:
        """分页查询普通用户日志。.

        查询所有普通用户（company_id不为None）的操作日志。
        支持按用户名、日志级别、时间范围筛选。

        Args:
            user_name: 用户名模糊匹配，可选
            level: 日志级别筛选（INFO、WARNING、ERROR等），可选
            start_time: 开始时间，ISO格式字符串，可选
            end_time: 结束时间，ISO格式字符串，可选
            skip: 跳过的记录数，默认为0
            limit: 限制返回的记录数，默认为10

        Returns:
            返回元组包含：
            - bool: 操作是否成功
            - int: HTTP状态码
            - str: 响应消息
            - int: 总记录数
            - list: 用户日志列表，包含用户名等详细信息

        Raises:
            Exception: 数据库查询异常时可能抛出
        """
        async with AsyncSessionLocal() as db:
            try:
                # 解析时间
                start_dt = None
                end_dt = None
                if start_time:
                    try:
                        start_dt = to_naive_beijing(datetime.fromisoformat(start_time))
                    except ValueError:
                        return False, 400, "start_time 格式无效，应为 ISO 格式", 0, []
                if end_time:
                    try:
                        end_dt = to_naive_beijing(datetime.fromisoformat(end_time))
                    except ValueError:
                        return False, 400, "end_time 格式无效，应为 ISO 格式", 0, []

                # 构建 UserLog 查询子句
                user_log_stmt = select(
                    UserLogModel.id,
                    UserLogModel.user_id,
                    UserModel.username.label("user_name"),
                    literal("non-transaction").label("log_type"),
                    UserLogModel.action,
                    UserLogModel.level,
                    UserLogModel.message,
                    UserLogModel.created_at,
                    UserLogModel.updated_at,
                ).join(UserLogModel.user)

                # 添加过滤条件
                if user_name:
                    user_log_stmt = user_log_stmt.where(
                        UserModel.username.like(f"%{user_name}%")
                    )
                if level:
                    user_log_stmt = user_log_stmt.where(UserLogModel.level == level)
                if start_dt:
                    user_log_stmt = user_log_stmt.where(
                        UserLogModel.created_at >= start_dt
                    )
                if end_dt:
                    user_log_stmt = user_log_stmt.where(
                        UserLogModel.created_at <= end_dt
                    )

                # === 正确的总数查询：先 union all 两个 count，再 sum ===
                count_union = union_all(
                    select(func.count().label("cnt")).select_from(
                        user_log_stmt.subquery()
                    ),
                ).subquery()

                total_query = select(func.sum(count_union.c.cnt))
                total_result = await db.execute(total_query)
                total = total_result.scalar() or 0

                # === 数据查询：UNION ALL 合并排序分页 ===
                combined_stmt = (
                    union_all(user_log_stmt)
                    .order_by(text("created_at DESC"))
                    .offset(skip)
                    .limit(limit)
                )

                result = await db.execute(combined_stmt)
                rows = result.fetchall()

                data = [
                    {
                        "id": row.id,
                        "user_id": row.user_id,
                        "user_name": row.user_name,
                        "level": row.level,
                        "message": row.message,
                        "created_at": row.created_at,
                        "updated_at": row.updated_at,
                    }
                    for row in rows
                ]

                return True, 200, "获取用户日志成功", total, data

            except Exception as e:
                # 可选：记录日志
                return False, 500, f"查询失败: {str(e)}", 0, []

    async def get_user_log_by_id(
        self, log_id: str
    ) -> tuple[bool, int, str, dict | None]:
        """根据ID获取普通用户日志详情。.

        通过日志ID查询单条普通用户日志的详细信息。
        只能查询普通用户（company_id不为None）的日志。

        Args:
            log_id: 用户日志ID

        Returns:
            返回元组包含：
            - bool: 操作是否成功
            - int: HTTP状态码
            - str: 响应消息
            - dict | None: 用户日志详情，未找到时为None

        Raises:
            Exception: 数据库查询异常时可能抛出
        """
        async with AsyncSessionLocal() as db:
            try:
                stmt = (
                    select(UserLogModel)
                    .join(UserLogModel.user)
                    .where(UserLogModel.id == log_id)
                )

                result = await db.execute(stmt)
                log = result.scalars().first()

                if not log:
                    return False, 404, "未找到对应的用户日志", None

                # 判断是哪种日志以便设置 log_type
                log_data = {
                    "id": log.id,
                    "user_id": log.user_id,
                    "user_name": log.user.username,
                    "level": log.level,
                    "message": log.message,
                    "created_at": log.created_at,
                    "updated_at": log.updated_at,
                }

                return True, 200, "获取用户日志成功", log_data

            except Exception as e:
                return False, 500, f"查询失败: {str(e)}", None


admin_log_service = AdminLogService()
