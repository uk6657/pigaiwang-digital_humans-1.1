"""加密工具模块。

提供文本加密和解密功能，用于敏感信息（如API密钥）的安全存储。
使用 Fernet 对称加密算法（AES-128）。
"""

from cryptography.fernet import Fernet

from app.core.config import settings

# 懒加载，避免在导入时就初始化
_fernet = None


def get_fernet() -> Fernet:
    """获取或初始化 Fernet 实例。"""
    global _fernet
    if _fernet is None:
        # 从配置读取加密密钥，必须是 32 字节 URL-safe base64 编码
        key = getattr(settings, "ENCRYPTION_KEY", None)
        if not key:
            # 开发环境：如果没有设置密钥，生成一个（注意：重启后无法解密之前的数据）
            key = Fernet.generate_key()
            # 建议打印出来让用户设置到配置中
            print(f"[WARNING] 未设置 ENCRYPTION_KEY，生成临时密钥: {key.decode()}")
        if isinstance(key, str):
            key = key.encode()
        _fernet = Fernet(key)
    return _fernet


def encrypt_text(text: str) -> str:
    """加密文本。

    Args:
        text: 要加密的明文（如 API 密钥）

    Returns:
        加密后的密文（URL-safe base64 格式）

    Raises:
        ValueError: 加密失败时抛出
    """
    if not text:
        return text
    try:
        f = get_fernet()
        return f.encrypt(text.encode()).decode()
    except Exception as e:
        raise ValueError(f"加密失败: {str(e)}")


def decrypt_text(encrypted_text: str) -> str:
    """解密文本。

    Args:
        encrypted_text: 密文

    Returns:
        解密后的明文

    Raises:
        ValueError: 解密失败（密钥错误或数据损坏）时抛出
    """
    if not encrypted_text:
        return encrypted_text
    try:
        f = get_fernet()
        return f.decrypt(encrypted_text.encode()).decode()
    except Exception as e:
        raise ValueError(f"解密失败: {str(e)}")
