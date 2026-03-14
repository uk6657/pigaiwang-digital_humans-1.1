"""Minimal auth service for the digital human demo project."""

from dataclasses import dataclass

from fastapi import status
from sqlalchemy import select

from app.auth import jwt_manager
from app.common.time_ import time_now
from app.storage import AsyncSessionLocal, UserModel, UserType
from app.utils.validation import validation_service


@dataclass(frozen=True)
class _SeedUser:
    username: str
    password: str
    user_type: int
    display_name: str


DEFAULT_DEMO_USERS: tuple[_SeedUser, ...] = (
    _SeedUser(
        username="teacher1",
        password="123456",
        user_type=UserType.teacher.value,
        display_name="演示老师",
    ),
    _SeedUser(
        username="teacher2",
        password="123456",
        user_type=UserType.operator.value,
        display_name="演示后台",
    ),
)


class DemoAuthService:
    """Small login service used to verify DB connectivity."""

    async def ensure_default_users(self) -> None:
        """Create demo login accounts if they do not exist yet."""

        async with AsyncSessionLocal() as session:
            changed = False

            for seed_user in DEFAULT_DEMO_USERS:
                stmt = select(UserModel).where(UserModel.username == seed_user.username)
                result = await session.execute(stmt)
                user = result.scalar_one_or_none()

                password_hash = validation_service.get_hashed_password(seed_user.password)

                if user is None:
                    user = UserModel(
                        username=seed_user.username,
                        password_hash=password_hash,
                        type=seed_user.user_type,
                        display_name=seed_user.display_name,
                        status=1,
                        is_active=True,
                    )
                    session.add(user)
                    changed = True
                    continue

                user.password_hash = password_hash
                user.type = seed_user.user_type
                user.display_name = seed_user.display_name
                user.status = 1
                user.is_active = True
                changed = True

            if changed:
                await session.commit()

    async def login(
        self,
        username: str,
        password: str,
        device_id: str | None = None,
    ) -> tuple[bool, int, str, dict | None]:
        """Login with username and password."""

        await self.ensure_default_users()

        async with AsyncSessionLocal() as session:
            stmt = select(UserModel).where(UserModel.username == username)
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()

            if user is None:
                return False, status.HTTP_400_BAD_REQUEST, "用户名或密码错误", None

            if not user.is_active or user.is_deleted:
                return False, status.HTTP_403_FORBIDDEN, "账号已停用", None

            if not validation_service.verify_password(password, user.password_hash):
                return False, status.HTTP_400_BAD_REQUEST, "用户名或密码错误", None

            user_id = str(user.id)
            username_value = user.username
            user_type = user.type
            display_name = user.display_name

            token_info = await jwt_manager.generate_token(
                user_id,
                device_id=device_id,
                store_in_redis=False,
            )

            user.last_login_at = time_now()
            await session.commit()

            return (
                True,
                status.HTTP_200_OK,
                "登录成功",
                {
                    "user": {
                        "id": user_id,
                        "username": username_value,
                        "type": user_type,
                        "display_name": display_name,
                    },
                    "token_info": token_info,
                },
            )


demo_auth_service = DemoAuthService()
