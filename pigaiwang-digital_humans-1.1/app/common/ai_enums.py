"""AI 模型管理相关枚举定义.

提供：
- 模型类型枚举（文生文、文生图、图生视频等）
- 任务状态枚举（PENDING、SUBMITTED、PROCESSING等）
- AI 服务提供商枚举
- 任务类型枚举
"""

from enum import Enum


class ModelType(str, Enum):
    """模型类型枚举."""

    TEXT_TO_TEXT = "text_to_text"  # 如: GPT-4, Claude, Qwen-Max
    TEXT_TO_IMAGE = "text_to_image"  # 如: DALL-E, Flux, 通义万相
    IMAGE_TO_IMAGE = "image_to_image"  # 如: Midjourney img2img, SD img2img
    IMAGE_TO_VIDEO = "image_to_video"  # 如: Kling, Vidu, Runway
    REFERENCE_TO_VIDEO = "reference_to_video"  # 基于参考视频生成
    TEXT_TO_VIDEO = "text_to_video"  # 如: Sora, Runway Gen-2
    TEXT_TO_AUDIO = "text_to_audio"  # 如: TTS模型


class TaskType(str, Enum):
    """任务类型枚举（用于代码内部调用）.

    与 ModelType 对应，但使用英文标识符，便于代码中调用。
    """

    TEXT_TO_TEXT = "text_to_text"
    TEXT_TO_IMAGE = "text_to_image"
    IMAGE_TO_IMAGE = "image_to_image"
    IMAGE_TO_VIDEO = "image_to_video"
    REFERENCE_TO_VIDEO = "reference_to_video"
    TEXT_TO_VIDEO = "text_to_video"
    TEXT_TO_AUDIO = "text_to_audio"


class TaskStatus(str, Enum):
    """任务状态枚举."""

    PENDING = "PENDING"  # 待提交
    SUBMITTED = "SUBMITTED"  # 已提交给厂商，等待处理
    PROCESSING = "PROCESSING"  # 厂商处理中
    SUCCEEDED = "SUCCEEDED"  # 成功完成
    FAILED = "FAILED"  # 失败
    TIMEOUT = "TIMEOUT"  # 超时
    CANCELLED = "CANCELLED"  # 已取消


class Provider(str, Enum):
    """AI 服务提供商枚举."""

    OPENAI = "openai"  # OpenAI (GPT/DALL-E/Sora)
    ANTHROPIC = "anthropic"  # Anthropic (Claude)
    DASHSCOPE = "dashscope"  # 阿里云 DashScope (通义千问/万相)
    KLING = "kling"  # 可灵 (快手)
    VIDU = "vidu"  # Vidu (生数科技)
    VOLCANO = "volcano"  # 火山方舟 (字节跳动)
    MOONSHOT = "moonshot"  # Moonshot AI (月之暗面)
