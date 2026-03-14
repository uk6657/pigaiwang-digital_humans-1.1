"""Authorization authentication related modules"""

from .jwt_manager import (
    UserClaims,
    get_current_user_dependency,
    jwt_manager,
)


class _AdminBaseFallback:
    admin_role_id = ""
    admin_user_id_list: list[str] = []

    def check_admin_user(self, user_id: str) -> bool:
        return False

    def check_admin_username(self, username: str) -> bool:
        return False

    async def init_admin(self) -> None:
        return None


try:
    from .admin import admin_base
except ImportError:
    admin_base = _AdminBaseFallback()

__all__ = [
    "jwt_manager",
    "get_current_user_dependency",
    "UserClaims",
    "admin_base",
]
