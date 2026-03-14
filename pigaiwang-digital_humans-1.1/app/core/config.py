"""应用配置模块。

管理全局配置参数和设置项。
"""


class Settings:
    """应用设置类。

    包含数据库、Redis、加密等核心配置。
    """

    # 加密密钥，必须是 32 字节 URL-safe base64 编码
    # 生成方式：python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    ENCRYPTION_KEY: str = "your-generated-key-here"


settings = Settings()
