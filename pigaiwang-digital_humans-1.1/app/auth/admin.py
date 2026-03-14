"""管理员基类模块。

定义系统管理员的基础功能：
- 管理员用户ID列表管理
- 管理员用户验证（基于用户名或ID）
- 应用启动时自动初始化默认管理员账号
"""

from loguru import logger
from sqlalchemy import select

from app.common.enums import UserStatus
from app.configs.config import base_configs
from app.storage import AsyncSessionLocal, UserModel
from app.utils.validation import validation_service


class AdminBase:
    """管理员基类（简化版，无角色表依赖）。

    负责在系统启动时自动创建/确保默认管理员用户存在。
    管理员身份判断直接基于用户ID列表（从配置读取并初始化后填充）。

    Attributes:
        admin_user_id_list: 已确认的超级管理员用户ID列表
    """

    def __init__(self):
        """初始化方法"""
        self.admin_user_id_list: list[str] = []

    def check_admin_user(self, user_id: str) -> bool:
        """检查是否为管理员用户（基于ID）"""
        return user_id in self.admin_user_id_list

    def check_admin_username(self, username: str) -> bool:
        """备选检查：基于用户名判断是否管理员（较宽松）"""
        return any(
            admin.username == username for admin in base_configs.DEFAULT_SYSTEM_ADMINS
        )

    async def init_admin(self):
        """初始化默认管理员用户"""
        await self.create_admin()

    async def create_admin(self) -> None:
        """确保所有配置中的默认管理员用户都存在于数据库中"""
        async with AsyncSessionLocal() as session:
            try:
                for admin in base_configs.DEFAULT_SYSTEM_ADMINS:
                    username = admin.username
                    password = admin.password
                    phone = admin.phone or ""

                    # 查询用户是否存在
                    stmt = select(UserModel).where(UserModel.username == username)
                    result = await session.execute(stmt)
                    user = result.scalar_one_or_none()

                    if not user:
                        # 创建新管理员用户
                        password_hash = validation_service.get_hashed_password(password)
                        user = UserModel(
                            username=username,
                            password_hash=password_hash,
                            phone=phone,
                            status=UserStatus.USING,  # 直接设为正常状态
                            is_admin=True,
                        )
                        session.add(user)
                        await session.flush()  # 获取生成的 id
                        logger.info(f"已创建默认管理员用户：{username} (ID: {user.id})")
                    else:
                        # 已存在，检查状态是否正常（可选）
                        if user.status != UserStatus.USING:
                            user.status = UserStatus.USING
                            logger.warning(f"管理员 {username} 状态异常，已恢复为正常")
                        else:
                            logger.debug(f"管理员用户已存在：{username}")

                    # 收集用户ID，用于后续快速判断
                    if user.id not in self.admin_user_id_list:
                        self.admin_user_id_list.append(user.id)

                await session.commit()
                logger.success(
                    f"默认管理员初始化完成，共 {len(self.admin_user_id_list)} 个管理员用户"
                )

            except Exception as e:
                await session.rollback()
                logger.bind(log_type="system").error(f"管理员初始化失败: {str(e)}")
                print(f"✗ 管理员初始化失败: {str(e)}")
                # 建议开发阶段不要直接 sys.exit()，可改为 raise 或记录
                # sys.exit(1)


admin_base = AdminBase()
