"""枚举类型定义模块

定义系统中使用的各种枚举类型，包括动作类型、权限级别、登录方式、用户状态等。
"""

from enum import Enum, IntEnum


class AuthActionType(str, Enum):
    """动作类型枚举"""

    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    EXECUTE = "execute"
    LIST = "list"


class PermissionLevel(str, Enum):
    """权限级别枚举"""

    MODULE = "module"
    INTERFACE = "interface"
    ACTION = "action"


class LoginType(int, Enum):
    """登录方式枚举"""

    LOGINBYPASSWORD = 1
    LOGINBYVERIFICATIONCODE = 2


class UserStatus(int, Enum):
    """用户状态枚举"""

    DISABLE = 0
    USING = 1
    CHECKING = 2


class UserIsDeleted(int, Enum):
    """用户软删除状态枚举"""

    DELETED = 0
    NOTDELETED = 1


class BucketMenu(str, Enum):
    """s3 bucket枚举"""

    # ── 核心生成内容（强烈建议分开）
    USER_MATERIALS = "user-materials"  # 用户上传的参考素材（角色/场景/道具/音频）
    GENERATED_IMAGES = "generated-images"  # AI 生成的单张图片
    GENERATED_VIDEOS = "generated-videos"  # AI 生成的视频片段/整集
    GENERATED_AUDIO = "generated-audio"  # 语音合成、音效、配乐
    EXPORTED_PROJECTS = "exported-projects"  # 用户最终导出的 mp4/zip/json 等
    GENERATED_TEXT = "generated-text"  # 剧本、大纲、分镜 json 等文本产物


class GenderType(IntEnum):
    """性别枚举"""

    MALE = 1  # 对应数据库的 1
    FEMALE = 2  # 对应数据库的 2


# TODO 是否考虑删除？
class DocumentProcessStage(str, Enum):
    """文档处理阶段枚举"""

    PENDING = "pending"  # 待上传
    UPLOADED = "uploaded"  # 已上传
    CHUNKING = "chunking"  # 分块中
    CHUNKED = "chunked"  # 分块完成
    CHUNK_CORRECTED = "chunk_corrected"  # 分块已矫正
    PREPROCESSING = "preprocessing"  # 预处理中
    READY = "ready"  # 就绪 (最终成功)
    FAILED = "failed"  # 失败


## TODO 是否考虑修改？
class TaskStatus(Enum):
    """任务状态枚举，用于 generation_tasks 表和前后端状态展示"""

    PENDING = "pending"  # 等待中（刚提交，还没开始）
    RUNNING = "running"  # 执行中
    SUCCESS = "success"  # 完成
    FAILED = "failed"  # 失败
    CANCELLED = "cancelled"  # 用户取消或超时

    def __str__(self):
        """返回枚举值的字符串表示"""
        return self.value


class Genre(str, Enum):
    """题材枚举类"""

    URBAN_FANTASY = "都市脑洞"
    URBAN_ROMANCE = "都市言情"
    ANCIENT_ROMANCE = "古风言情"
    HISTORICAL_FANTASY = "历史脑洞"
    XUANHUAN = "玄幻"
    FANTASY = "奇幻"
    CLASSIC_XIANXIA = "传统仙侠"
    XIANXIA_FANTASY = "仙侠脑洞"
    SCIENCE_FICTION = "科幻"
    MYSTERY = "悬疑"
    FOLKLORE = "民俗"
    WAR_GOD = "战神"
    COMEBACK = "逆袭"
    GROWTH = "成长"
    PERIOD_ROMANCE = "权谋"
    ERA_ROMANCE = "年代爱情"
    FARMING = "种田"
    SUPERNATURAL = "灵异"
    YOUTH = "青春"
    WUXIA = "武侠"
    ACTION = "动作"


class ProjectStatus(str, Enum):
    """项目状态枚举类"""

    STRUCTURE_RULES_GENERATING = "STRUCTURE_RULES_GENERATING"  # 结构规则生成中
    STRUCTURE_RULES_GENERATED_FAILED = (
        "STRUCTURE_RULES_GENERATED_FALED"  # 结构规则生成失败
    )
    STRUCTURE_RULES_GENERATED = "STRUCTURE_RULES_GENERATED"  # 结构规则已生成

    OUTLINE_GENERATING = "OUTLINE_GENERATING"  # 创意大纲生成中
    OUTLINE_GENERATED = "OUTLINE_GENERATED"  # 创意大纲已生成
    OUTLINE_GENERATED_FAILED = "OUTLINE_GENERATED_FALED"  # 创意大纲生成失败

    SCRIPT_GENERATING = "SCRIPT_GENERATING"  # 剧本生成中
    SCRIPT_GENERATED = "SCRIPT_GENERATED"  # 剧本已生成
    SCRIPT_GENERATED_FAILED = "SCRIPT_GENERATED_FALED"  # 剧本生成失败


class ScriptStatus(str, Enum):
    """剧集状态枚举类"""

    PENDING_CONFIRMATION = "PENDING_CONFIRMATION"  # 待确认
    COMPLETED = "COMPLETED"  # 已完成


class ScriptStyleConstraintType(str, Enum):
    """风格包约束枚举类"""

    GENERAL = "GENERAL"  # 通用约束
    GENRE_SPECIFIC = "GENRE_SPECIFIC"  # 特定题材约束


class MaterialType(str, Enum):
    """素材类型枚举类"""

    CHARACTER = "character"  # 角色
    SCENE = "scene"  # 场景
    PROP = "prop"  # 道具
    AUDIO = "audio"  # 音频


class AgeGroup(str, Enum):
    """年龄枚举类"""

    CHILD = "CHILD"  # 儿童
    TEEN = "TEEN"  # 少年
    YOUNG_ADULT = "YOUNG_ADULT"  # 青年
    MIDDLE_AGED = "MIDDLE_AGED"  # 中年
    ELDERLY = "ELDERLY"  # 老年


class AudioMaterialType(str, Enum):
    """音色枚举类"""

    NARRATION = "NARRATION"  # 旁白
    CHARACTER = "CHARACTER"  # 角色
    BACKGROUND_MUSIC = "BACKGROUND_MUSIC"  # 背景音
    SOUND_EFFECT = "SOUND_EFFECT"  # 音效


class SceneMaterialType(str, Enum):
    """音频适用场景枚举类"""

    GENERAL_SCENE = "GENERAL_SCENE"  # 通用场景
    ROLE_PLAYING = "ROLE_PLAYING"  # 角色扮演
    NOVEL_SCENE = "NOVEL_SCENE"  # 小说场景


class DirectorStyleType(str, Enum):
    """导演风格包类型枚举类"""

    ANIME_STYLE = "ANIME_STYLE"  # 动漫风格
    REALISTIC_STYLE = "REALISTIC_STYLE"  # 写实风格


# 风格包 type 前端中文到枚举值的映射（SCRIPT 用 ScriptStyleConstraintType，DIRECTOR 用 DirectorStyleType）
STYLE_PACKS_TYPE_CN_TO_EN = {
    "特定题材约束": ScriptStyleConstraintType.GENRE_SPECIFIC.value,
    "通用约束": ScriptStyleConstraintType.GENERAL.value,
    "动漫风格": DirectorStyleType.ANIME_STYLE.value,
    "写实风格": DirectorStyleType.REALISTIC_STYLE.value,
}

# 系统提示词 type：前端传中文，数据库存英文
SYSTEM_PROMPT_TYPE_CN_TO_EN = {
    "结构规则生成": "STRUCTURE_RULES_SYSTEM_PROMPT",
    "创意大纲生成": "OUTLINE_SYSTEM_PROMPT",
    "剧本生成": "SCRIPT_SYSTEM_PROMPT",
    "镜头参数生成": "SHOT_PARAMS_SYSTEM_PROMPT",
    "角色生成": "CHARACTER_SYSTEM_PROMPT",
    "场景生成": "SCENES_SYSTEM_PROMPT",
    "道具生成": "PROPS_SYSTEM_PROMPT",
}
