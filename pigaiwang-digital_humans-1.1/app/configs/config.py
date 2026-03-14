"""项目全局配置（从 .env 读取）"""

import os
from typing import ClassVar, Literal

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AdminAccount(BaseModel):
    """单个管理员账户配置"""

    username: str
    password: str
    phone: str | None = None


class Settings(BaseSettings):
    """项目全局配置（从 .env / 环境变量加载）"""

    model_config = SettingsConfigDict(
        env_file="./conf/.env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",  # 可选：支持 REDIS__URL 这种嵌套写法
        extra="ignore",
    )

    # ==================== 基础服务配置 ====================
    ENV: Literal["dev", "test", "prod"] = "dev"
    PROJECT_PORT: int = 8000
    PROJECT_HOST: str = "0.0.0.0"
    PROJECT_NAME: str = "ai-manhua"
    
    PROJECT_WORKERS: int = 1  # gunicorn/uvicorn worker 数量
    API_PREFIX: str = "/api/v1"
    PROJECT_DIR: str = os.getcwd()
    PROJECT_LOG_DIR: str = os.path.join(PROJECT_DIR, "logs")
    PROJECT_DATA_DIR: str = os.path.join(PROJECT_DIR, "data")
    WORKER_ID: int = -1  # 工作进程id，默认为-1，生成雪花id时会处理
    WORKER_PID: int = os.getpid()
    # 任务管理配置
    BACKLOG: int = 64  # 待执行队列最大长度（防止内存爆）
    POLL_SEC: float = 0.3  # 轮询间隔（秒）
    # ==================== 数据库 ====================
    DATABASE_URL: str = "sqlite+aiosqlite:///ai_manhua.db"
    # 生产建议：postgresql+asyncpg://postgres:123456@db:5432/ai_manhua
    DATABASE_ECHO: bool = True  # 开发时开，生产关

    # ==================== 对象存储（MinIO / AWS S3） ====================
    S3_URL: str = "http://localhost:9000"
    S3_PUBLIC_URL: str | None = None
    S3_ACCESS_KEY: str = "minioadmin"
    S3_SECRET_KEY: str = "minioadmin"
    QUESTION_IMAGE_BUCKET: str = "pigaiwang-dev-question-images"
    S3_BUCKET_NAME: str = "ai-manhua" 
     # ← 新增，很重要
    S3_REGION: str = "us-east-1"
    S3_SECURE: bool = False  # 本地 MinIO 用 False
    S3_MAX_POOL_CONNECTIONS: int = 50
    S3_MULTIPART_THRESHOLD: int = 8 * 1024 * 1024  # 8MB
    S3_MULTIPART_CHUNKSIZE: int = 8 * 1024 * 1024
    S3_MAX_CONCURRENCY: int = 10
    S3_OBJECT_PUBLIC_READ: bool = False
    S3_PUBLIC_READ_POLICY: bool = False
    S3_USE_PRESIGNED_DOWNLOAD_URL: bool = False
    S3_PRESIGNED_DOWNLOAD_EXPIRES: int = 3600

    # ==================== JWT 认证 ====================
    SECRET_KEY: str = "change-me-to-very-long-random-secret-key-64+chars"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 建议 1 天

    # ==================== 默认管理员（仅首次初始化使用） ====================
    DEFAULT_SYSTEM_ADMINS: list[AdminAccount] = [
        AdminAccount(username="admin", password="Admin123!", phone=None)
    ]
    DEFAULT_ADMIN_ROLE: str = "admin"

    # ==================== Redis ====================
    REDIS_URL: str = "redis://localhost:6379/0"

    # ==================== AI 模型相关 API Key ====================
    DEEPSEEK_API_KEY: str = ""
    QWEN_IMAGE_API_KEY: str = ""
    NANOBANANA_API_KEY: str = ""
    TONGYI_WANXIANG_API_KEY: str = ""
    INDEX_TTS_API_KEY: str = ""
    SUNO_API_KEY: str = ""

    # ==================== 通用文本大模型（OpenAI 兼容）====================
    # 当 ai_models 表未配置时，可使用该组配置作为兜底，方便本地快速测试。
    # 示例（通义千问兼容模式）：
    # - LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
    # - LLM_MODEL_KEY=qwen3-max
    # - LLM_VISION_MODEL_KEY=qwen-vl-max-latest
    # - LLM_API_KEY=sk-xxxx
    LLM_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    LLM_MODEL_KEY: str = "qwen3.5-plus"
    LLM_VISION_MODEL_KEY: str = "qwen3.5-plus"
    LLM_API_KEY: str = Field(default="", validation_alias="DASHSCOPE_API_KEY")
    LLM_TIMEOUT_SEC: float = 60.0
    LLM_MAX_RETRIES: int = 2
    LLM_TRUST_ENV_PROXY: bool = False

    # ==================== 业务限制 ====================
    FREE_DAILY_LIMIT: int = 20  # 免费用户每天生成次数
    DEFAULT_UPSCALE_FACTOR: int = 2  # 默认高清放大倍数

    # ==================== 工具路径 ====================
    FFMPEG_PATH: str = "/usr/bin/ffmpeg"  # 根据系统调整

    # 注解防止 mypy / IDE 报错
    init_settings: ClassVar[str]  # type: ignore

    def init_settings(self) -> None:
        """初始化目录等操作"""
        os.makedirs(self.PROJECT_LOG_DIR, exist_ok=True)
        os.makedirs(self.PROJECT_DATA_DIR, exist_ok=True)


# 全局单例配置对象
base_configs: Settings = Settings()
base_configs.init_settings()  # type: ignore
