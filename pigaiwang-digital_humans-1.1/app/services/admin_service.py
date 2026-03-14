"""管理员服务模块。

该模块提供了管理员账号管理的核心功能，包括登录认证、用户管理、
状态管理和日志导出等功能。
"""

import base64
import io
import random
from datetime import datetime
from urllib.parse import quote

import pandas as pd
from captcha.image import ImageCaptcha
from fastapi import status
from fastapi.responses import StreamingResponse
from sqlalchemy import case, func, select, update
from sqlalchemy.exc import IntegrityError

from app.api.form_response.admin_response import (
    ExportSystemLogFields,
    ExportUserLogFields,
    systemLogEToC,
    userLogEToC,
)
from app.auth import jwt_manager
from app.auth.admin import admin_base  # ← 加这一行
from app.common.enums import UserStatus
from app.common.time_ import time_now, time_now_naive, to_naive_beijing, zone_info
from app.core import redis_client
from app.storage import (
    AsyncSessionLocal,
    SystemLogModel,
    UserLogModel,
    UserModel,
)
from app.utils.snowflake_id import generate_id
from app.utils.validation import validation_service

image = ImageCaptcha(width=160, height=60)


class AdminService:
    """管理员服务类。

    提供管理员登录认证、账号管理、状态管理等功能。
    支持手机验证码和密码两种登录方式。
    """

    async def get_code_image(self) -> tuple[bool, int, str, dict | None]:
        """获取图形验证码"""
        image_code = str(random.randint(1000, 9999))
        code_image_id = generate_id()
        code_image = image.generate(image_code)
        code_image_base64 = base64.b64encode(code_image.getvalue()).decode("utf-8")
        print(f"{code_image_id}-图形验证码：{image_code}")  # TODO: 部署时删除

        # 使用 Redis 存储验证码，60秒过期
        await redis_client.setex(f"code_image:{code_image_id}", 60, image_code)

        response = {
            "code_image_id": code_image_id,
            "code_image_base64": f"data:image/png;base64,{code_image_base64}",
        }
        return True, status.HTTP_200_OK, "成功返回验证码图形", response

    async def login_by_phone_and_password(
        self,
        phone: str,
        password: str,
        image_code: str,
        image_id: str,
        device_id: str | None = None,
    ) -> tuple[bool, int, str, dict | None]:
        """通过手机号和密码进行管理员登录"""
        # TODO: 暂时取消验证码验证
        # if not await validation_service.verify_digit_code(image_id, image_code):
        #     return False, status.HTTP_400_BAD_REQUEST, "图形码错误", None
        async with AsyncSessionLocal() as session:
            try:
                result = await session.execute(
                    select(UserModel).where(UserModel.phone == phone)
                )
                user = result.scalars().first()

                if not user or not validation_service.verify_password(
                    password, user.password_hash
                ):
                    return False, status.HTTP_400_BAD_REQUEST, "手机号或密码错误", None

                if user.status == UserStatus.DISABLE.value:
                    return False, status.HTTP_400_BAD_REQUEST, "该账号已被禁用", None

                token_info = await jwt_manager.generate_token(
                    user.id, device_id=device_id
                )
                message = "登录成功"

                # 更新最后登录时间
                stmt = (
                    update(UserModel)
                    .where(UserModel.id == user.id)
                    .values(last_login_at=time_now_naive())
                )
                await session.execute(stmt)
                await session.commit()
                await session.refresh(user)

                return (
                    True,
                    status.HTTP_200_OK,
                    message,
                    {
                        "user_id": user.id,
                        "username": user.username,
                        "token_info": token_info,
                    },
                )
            except Exception as e:
                await session.rollback()
                return (
                    False,
                    status.HTTP_500_INTERNAL_SERVER_ERROR,
                    "操作失败，请稍后重试" + str(e),
                    None,
                )

    async def login_by_verification_code(
        self,
        phone: str,
        verification_code: str,
        image_code: str,
        image_id: str,
        device_id: str | None = None,
    ) -> tuple[bool, int, str, dict | None]:
        """通过手机验证码进行管理员登录"""
        if not await validation_service.verify_digit_code(image_id, image_code):
            return False, status.HTTP_400_BAD_REQUEST, "图形码错误", None

        if not await validation_service.validate_phone_verification_code(
            phone, verification_code
        ):
            return False, status.HTTP_400_BAD_REQUEST, "手机验证码错误或已失效", None

        async with AsyncSessionLocal() as session:
            try:
                result = await session.execute(
                    select(UserModel).where(UserModel.phone == phone)
                )
                user = result.scalars().first()

                if not user:
                    return False, status.HTTP_400_BAD_REQUEST, "用户不存在", None

                if user.status == UserStatus.DISABLE.value:
                    return False, status.HTTP_400_BAD_REQUEST, "该账号已被禁用", None

                token_info = await jwt_manager.generate_token(
                    user.id, device_id=device_id
                )
                message = "登录成功"

                stmt = (
                    update(UserModel)
                    .where(UserModel.id == user.id)
                    .values(last_login_at=time_now_naive())
                )
                await session.execute(stmt)
                await session.commit()
                await session.refresh(user)

                return (
                    True,
                    status.HTTP_200_OK,
                    message,
                    {
                        "username": user.username,
                        "token_info": token_info,
                    },
                )
            except Exception:
                await session.rollback()
                return (
                    False,
                    status.HTTP_500_INTERNAL_SERVER_ERROR,
                    "操作失败，请稍后重试",
                    None,
                )

    async def login_by_password(
        self,
        username: str,
        password: str,
        image_code: str,
        image_id: str,
        device_id: str | None = None,
    ) -> tuple[bool, int, str, dict | None]:
        """通过用户名和密码进行管理员登录"""
        if not await validation_service.verify_digit_code(image_id, image_code):
            return False, status.HTTP_400_BAD_REQUEST, "图形码错误", None

        async with AsyncSessionLocal() as session:
            try:
                result = await session.execute(
                    select(UserModel).where(UserModel.username == username)
                )
                user = result.scalars().first()

                if not user or not validation_service.verify_password(
                    password, user.password_hash
                ):
                    return False, status.HTTP_400_BAD_REQUEST, "用户名或密码错误", None

                if user.status == UserStatus.DISABLE.value:
                    return False, status.HTTP_400_BAD_REQUEST, "该账号已被禁用", None

                token_info = await jwt_manager.generate_token(
                    user.id, device_id=device_id
                )
                message = "登录成功"

                stmt = (
                    update(UserModel)
                    .where(UserModel.id == user.id)
                    .values(last_login_at=time_now_naive())
                )
                await session.execute(stmt)
                await session.commit()
                await session.refresh(user)

                return (
                    True,
                    status.HTTP_200_OK,
                    message,
                    {
                        "user_id": user.id,
                        "username": user.username,
                        "token_info": token_info,
                    },
                )
            except Exception:
                await session.rollback()
                return (
                    False,
                    status.HTTP_500_INTERNAL_SERVER_ERROR,
                    "操作失败，请稍后重试",
                    None,
                )

    async def soft_delete_admin(
        self, admin_id: str, user_id: str
    ) -> tuple[bool, int, str, None]:
        """软删除管理员账号"""
        if admin_id == user_id:
            return False, status.HTTP_400_BAD_REQUEST, "无法删除当前账号", None

        async with AsyncSessionLocal() as session:
            try:
                result = await session.execute(
                    select(UserModel).where(
                        UserModel.id == user_id, UserModel.is_deleted == 0
                    )
                )
                admin = result.scalars().first()

                if not admin:
                    return (
                        False,
                        status.HTTP_400_BAD_REQUEST,
                        "用户不存在或已删除",
                        None,
                    )

                current_time = time_now()
                stmt = (
                    update(UserModel)
                    .where(UserModel.id == user_id)
                    .values(
                        username=f"{admin.username}_{current_time}",
                        phone=f"{admin.phone}_{current_time}",
                        is_deleted=1,
                        status=UserStatus.DISABLE.value,
                    )
                )
                await session.execute(stmt)
                await session.commit()

                # 强制下线
                await jwt_manager.logout_user(user_id)

                return True, status.HTTP_200_OK, "删除成功", None
            except Exception:
                await session.rollback()
                return (
                    False,
                    status.HTTP_500_INTERNAL_SERVER_ERROR,
                    "操作失败，请稍后重试",
                    None,
                )

    async def update_user(
        self, user_id: str, username: str, phone: str
    ) -> tuple[bool, int, str, None]:
        """更新用户基本信息"""
        stmt = (
            update(UserModel)
            .where(UserModel.id == user_id)
            .values(username=username, phone=phone)
        )
        async with AsyncSessionLocal() as session:
            try:
                await session.execute(stmt)
                await session.commit()
                return True, status.HTTP_200_OK, "成功更新用户信息", None
            except IntegrityError as e:
                await session.rollback()
                if "UniqueViolation" in str(e):
                    if "users_username" in str(e):
                        return False, status.HTTP_409_CONFLICT, "该用户名已被注册", None
                    elif "users_phone" in str(e):
                        return (
                            False,
                            status.HTTP_409_CONFLICT,
                            "该手机号已被其他用户绑定",
                            None,
                        )
                return (
                    False,
                    status.HTTP_400_BAD_REQUEST,
                    "操作失败，数据无效或数据库错误",
                    None,
                )
            except Exception:
                await session.rollback()
                return (
                    False,
                    status.HTTP_500_INTERNAL_SERVER_ERROR,
                    "操作失败，请稍后重试",
                    None,
                )

    async def update_admin_info(
        self, user_id: str, username: str, phone: str
    ) -> tuple[bool, int, str, None]:
        """更新管理员信息"""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(UserModel).where(UserModel.id == user_id)
            )
            admin = result.scalars().first()
            if not admin:
                return False, status.HTTP_400_BAD_REQUEST, "用户不存在", None
            return await self.update_user(user_id, username, phone)

    async def get_admins_info(
        self,
        skip: int,
        limit: int | None,
        phone_substring: str | None = None,
        user_status: int | None = None,
    ) -> tuple[bool, int, str, list | None, int]:
        """分页查询管理员列表"""
        base_stmt = select(UserModel).where(UserModel.is_deleted == 0)

        if phone_substring:
            normalized = "".join(phone_substring.split()).lower()
            base_stmt = base_stmt.where(
                func.lower(
                    func.regexp_replace(UserModel.phone, r"\s+", "", "g")
                ).contains(normalized)
            )

        if user_status is not None:
            base_stmt = base_stmt.where(UserModel.status == user_status)

        async with AsyncSessionLocal() as session:
            try:
                # 总数
                count_stmt = select(func.count()).select_from(base_stmt.subquery())
                total = (await session.execute(count_stmt)).scalar() or 0

                # 分页数据
                stmt = base_stmt.offset(skip).order_by(UserModel.created_at.desc())
                if limit is not None:
                    stmt = stmt.limit(limit)

                result = await session.execute(stmt)
                admins = result.scalars().all()

                # 增强数据：在线状态
                enhanced_admins = []
                for admin in admins:
                    admin_dict = {
                        k: v for k, v in admin.__dict__.items() if not k.startswith("_")
                    }
                    admin_dict["is_online"] = await redis_client.exists(
                        f"user_token:{admin.id}"
                    )
                    enhanced_admins.append(admin_dict)

                return True, status.HTTP_200_OK, "查询成功", enhanced_admins, total
            except Exception:
                return (
                    False,
                    status.HTTP_500_INTERNAL_SERVER_ERROR,
                    "操作失败，请稍后重试",
                    None,
                    0,
                )

    async def add_admin(
        self, username: str, phone: str, password: str, user_status: int
    ) -> tuple[bool, int, str, None]:
        """创建新的管理员账号"""
        password_hash = validation_service.get_hashed_password(password)
        new_user = UserModel(
            username=username,
            phone=phone,
            password_hash=password_hash,
            status=user_status,
        )
        async with AsyncSessionLocal() as session:
            try:
                session.add(new_user)
                await session.commit()
                return True, status.HTTP_200_OK, "创建成功", None
            except IntegrityError as e:
                await session.rollback()
                if "UniqueViolation" in str(e):
                    if "users_username" in str(e):
                        return False, status.HTTP_409_CONFLICT, "该用户名已被注册", None
                    elif "users_phone" in str(e):
                        return (
                            False,
                            status.HTTP_409_CONFLICT,
                            "该手机号已被其他用户绑定",
                            None,
                        )
                return (
                    False,
                    status.HTTP_400_BAD_REQUEST,
                    "创建失败，数据无效或数据库错误",
                    None,
                )
            except Exception:
                await session.rollback()
                return (
                    False,
                    status.HTTP_500_INTERNAL_SERVER_ERROR,
                    "创建失败，请稍后重试",
                    None,
                )

    async def change_status(
        self, user_id: str, user_status: int
    ) -> tuple[bool, int, str, None]:
        """修改用户状态"""
        stmt = (
            update(UserModel).where(UserModel.id == user_id).values(status=user_status)
        )
        async with AsyncSessionLocal() as session:
            try:
                await session.execute(stmt)
                if user_status == UserStatus.DISABLE.value:
                    await jwt_manager.logout_user(user_id)
                await session.commit()
                return True, status.HTTP_200_OK, "修改成功", None
            except Exception:
                await session.rollback()
                return (
                    False,
                    status.HTTP_500_INTERNAL_SERVER_ERROR,
                    "操作失败，请稍后重试",
                    None,
                )

    async def change_admin_status(
        self, admin_id: str, user_id: str, user_status: int
    ) -> tuple[bool, int, str, None]:
        """修改管理员状态（不能改自己）"""
        if admin_id == user_id:
            return False, status.HTTP_400_BAD_REQUEST, "无法改变当前账号状态", None

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(UserModel).where(UserModel.id == user_id)
            )
            if not result.scalars().first():
                return False, status.HTTP_400_BAD_REQUEST, "用户不存在", None
            return await self.change_status(user_id, user_status)

    def get_admin_user_id(self) -> tuple[bool, int, str, dict[str, list[str]] | None]:
        """获取超级管理员用户ID列表"""
        return (
            True,
            status.HTTP_200_OK,
            "超级管理员ID获取成功",
            {"admin_user_ids": admin_base.admin_user_id_list},
        )

    async def logout(self, user_id: str) -> tuple[bool, int, str, None]:
        """用户退出登录"""
        try:
            await jwt_manager.logout_user(user_id)
            return True, status.HTTP_200_OK, "安全退出", None
        except Exception:
            return (
                False,
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                "操作失败，请稍后重试",
                None,
            )

    async def force_logout(self, user_id: str) -> tuple[bool, int, str, None]:
        """强制用户下线"""
        try:
            if await jwt_manager.is_user_online(user_id):
                await jwt_manager.logout_user(user_id)
                return True, status.HTTP_200_OK, "操作成功", None
            return (
                False,
                status.HTTP_400_BAD_REQUEST,
                "用户不在线，无法执行此操作",
                None,
            )
        except Exception:
            return (
                False,
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                "操作失败，请稍后重试",
                None,
            )

    async def force_logout_admin(
        self, admin_id: str, user_id: str
    ) -> tuple[bool, int, str, None]:
        """强制管理员下线（不能强制自己）"""
        if admin_id == user_id:
            return False, status.HTTP_400_BAD_REQUEST, "无法强制下线当前账号", None

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(UserModel).where(UserModel.id == user_id)
            )
            if not result.scalars().first():
                return False, status.HTTP_400_BAD_REQUEST, "用户不存在", None
            return await self.force_logout(user_id)

    async def export_system_logs(
        self,
        log,
        level: str | None,
        is_desc: bool,
        start_time: datetime | None,
        end_time: datetime | None,
        total: int | None,
    ) -> StreamingResponse | None:
        """导出系统日志到Excel文件"""
        start_time = to_naive_beijing(start_time)
        end_time = to_naive_beijing(end_time)

        row_number_col = (
            func.row_number()
            .over(
                order_by=SystemLogModel.created_at.desc()
                if is_desc
                else SystemLogModel.created_at.asc()
            )
            .label("序号")
        )

        created_at_col = func.to_char(
            func.timezone(zone_info.key, SystemLogModel.created_at),
            "YYYY-MM-DD HH24:MI:SS",
        ).label(systemLogEToC["created_at"])

        columns = [
            getattr(SystemLogModel, field).label(systemLogEToC[field])
            for field in ExportSystemLogFields.model_fields.keys()
        ]

        stmt = select(row_number_col, *columns, created_at_col)

        if total is not None:
            stmt = stmt.limit(total)
        if level is not None:
            stmt = stmt.where(SystemLogModel.level == level)
        if start_time:
            stmt = stmt.where(SystemLogModel.created_at >= start_time)
        if end_time:
            stmt = stmt.where(SystemLogModel.created_at <= end_time)

        if is_desc:
            stmt = stmt.order_by(SystemLogModel.created_at.desc())
        else:
            stmt = stmt.order_by(SystemLogModel.created_at.asc())

        async with AsyncSessionLocal() as session:
            try:
                data = await session.execute(stmt)
                system_logs = data.fetchall()
                col_names = data.keys()

                df = pd.DataFrame(system_logs, columns=col_names)
                output = io.BytesIO()

                with pd.ExcelWriter(output, engine="openpyxl") as writer:
                    df.to_excel(writer, index=False, sheet_name="系统日志")

                output.seek(0)

                filename = "系统日志.xlsx"
                encoded_filename = quote(filename)

                headers = {
                    "Content-Disposition": f'attachment; filename="{encoded_filename}"; filename*=UTF-8\'{encoded_filename}'
                }

                log.info("成功导出系统日志")
                return StreamingResponse(
                    output,
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers=headers,
                )
            except Exception as e:
                log.error(f"系统日志导出失败，错误:{str(e)}")
                return None

    async def export_user_logs(
        self,
        log,
        level: str | None,
        user_name: str | None,
        is_desc: bool,
        start_time: datetime | None,
        end_time: datetime | None,
        total: int | None,
        is_user: bool = True,
    ) -> StreamingResponse | None:
        """导出用户日志或管理日志到Excel文件"""
        start_time = to_naive_beijing(start_time)
        end_time = to_naive_beijing(end_time)

        filename = "用户日志.xlsx" if is_user else "管理日志.xlsx"
        sheet_name = "用户日志" if is_user else "管理日志"

        row_number_col = (
            func.row_number()
            .over(
                order_by=UserLogModel.created_at.desc()
                if is_desc
                else UserLogModel.created_at.asc()
            )
            .label("序号")
        )

        created_at_col = func.to_char(
            func.timezone(zone_info.key, UserLogModel.created_at),
            "YYYY-MM-DD HH24:MI:SS",
        ).label(userLogEToC["created_at"])

        columns = [
            getattr(UserLogModel, field).label(userLogEToC[field])
            for field in ExportUserLogFields.model_fields.keys()
        ]

        stmt = select(
            row_number_col,
            UserModel.username.label(userLogEToC["username"]),
            *columns,
            case(
                (UserModel.is_deleted == 0, "否"), (UserModel.is_deleted == 1, "是")
            ).label(userLogEToC["is_deleted"]),
            created_at_col,
        ).outerjoin(UserModel, UserModel.id == UserLogModel.user_id)

        if total is not None:
            stmt = stmt.limit(total)
        if level is not None:
            stmt = stmt.where(UserLogModel.level == level)
        if start_time:
            stmt = stmt.where(UserLogModel.created_at >= start_time)
        if end_time:
            stmt = stmt.where(UserLogModel.created_at <= end_time)
        if user_name:
            stmt = stmt.where(UserModel.username.like(f"%{user_name}%"))

        if is_desc:
            stmt = stmt.order_by(UserLogModel.created_at.desc())
        else:
            stmt = stmt.order_by(UserLogModel.created_at.asc())

        async with AsyncSessionLocal() as session:
            try:
                data = await session.execute(stmt)
                user_logs = data.fetchall()
                col_names = data.keys()

                df = pd.DataFrame(user_logs, columns=col_names)
                output = io.BytesIO()

                with pd.ExcelWriter(output, engine="openpyxl") as writer:
                    df.to_excel(writer, index=False, sheet_name=sheet_name)

                output.seek(0)

                encoded_filename = quote(filename)
                headers = {
                    "Content-Disposition": f'attachment; filename="{encoded_filename}"; filename*=UTF-8\'{encoded_filename}'
                }

                log.info(f"{filename}导出成功")
                return StreamingResponse(
                    output,
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers=headers,
                )
            except Exception as e:
                log.error(f"{filename}导出失败，错误:{str(e)}")
                return None

    def normalized_sql_str(self, column):
        """标准化SQL字符串，用于模糊查询"""
        return func.lower(func.regexp_replace(column, r"\s+", "", "g"))


admin_service = AdminService()
