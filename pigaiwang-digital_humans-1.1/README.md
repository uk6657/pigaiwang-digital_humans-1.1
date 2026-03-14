
# ai manhua Backend

<div align="center">

![FastAPI](https://img.shields.io/badge/FastAPI-0.116.1-green.svg)
![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
</div>

## 快速开始

### 环境要求

- Python 3.10
- PostgreSQL (有具体镜像)
- Redis (有具体镜像)
- UV 包管理器（必须!）


### 安装步骤

1. **安装依赖**

```bash
# 安装uv(linux)
curl -LsSf https://astral.sh/uv/install.sh | sh

# shell 补全设置
echo 'eval "$(uv generate-shell-completion bash)"' >> ~/.bashrc
echo 'eval "$(uvx --generate-shell-completion bash)"' >> ~/.bashrc

source ~/.bashrc

# windows参考官网
https://docs.astral.sh/uv/guides/install-python/#getting-started
```


```bash
# 使用 UV 安装依赖
uv sync

# 安装 pre-commit hooks，非常重要!
uv run pre-commit install
```

说明：项目已通过 `uv` 纳入 `openpyxl` 依赖，拉取最新代码后执行一次 `uv sync` 即可安装。

2. **配置环境变量**
```bash
# 复制环境变量模板
cp conf/examples.env conf/.env

# 编辑配置文件
vim conf/.env
```

3. **启动服务**

api开发模式（支持热更新，不启动任务队列）：
```bash
uv run dev.py
```

启动任务服务以及任务队列和定时任务（推荐）：
```bash
uv run honcho start
```

生产模式：
```bash
uv run main.py
```

开发时需要安装新的依赖
```bash
uv add package_name

# 例如新增 Excel 读写依赖
uv add openpyxl
```

### 验证安装

访问以下地址验证服务是否正常运行：

- API 文档：http://localhost:8000/docs
- ReDoc 文档：http://localhost:8000/redoc
- OpenAPI 规范：http://localhost:8000/openapi.json

## 项目结构

```
scholar-guard-backend/
├── app/                          # 核心应用代码
│   ├── api/                      # API 接口层
│   │   ├── form_validation/      # Pydantic 请求验证模型
│   │   ├── form_response/        # 响应数据模型
│   │   └── routers/              # API 路由实现
│   ├── auth/                     # 认证授权模块
│   │   ├── jwt_manager.py        # JWT 令牌管理
│   ├── services/                 # 业务逻辑层
│   ├── storage/                  # 数据层（SQLAlchemy 模型）
│   ├── core/                     # 核心组件（Redis,任务队列）
│   ├── utils/                    # 工具模块
│   ├── common/                   # 通用模块
│   └── configs/                  # 配置管理
├── conf/                         # 配置文件
│   ├── .env                      # 环境变量
├── deploy/                       # 部署相关文件
├── docs/                         # 项目文档
├── docker/                       # Docker 脚本
├── tasks/                        # 任务队列相关
├── main.py                       # 生产环境入口
├── dev.py                        # 开发环境入口
├── setup.py                      # Cython 编译脚本
├── build.py                      # PyInstaller 打包脚本
└── pyproject.toml               # 项目配置
```

### 模块说明

#### app/api - API 接口层
- 处理 HTTP 请求和响应
- 数据验证和序列化
- 路由注册和权限装饰

#### app/services - 业务逻辑层
- 核心业务逻辑实现

#### app/storage - 数据访问层
- SQLAlchemy 数据模型

#### app/auth - 认证授权
- JWT 令牌管理
- 用户认证和授权

#### app/core - 核心组件
- Redis 连接管理
- S3 连接管理

## 开发指南

### 代码规范

项目使用 Ruff 进行代码检查和格式化：

```bash
# 检查代码
uv run ruff check .

# 格式化代码
uv run ruff format .

# 类型检查
uv run ty check .

# 提交前的全面检查
uv run pre-commit run -a
```

### 开发流程

1. **创建功能分支**
```bash
git checkout -b feature/new-feature
```
- 分支命名规范 
```
功能开发：feature/{功能名称}
 例：feature/user-login、feature/search-bar
修复 bug：bugfix/{bug描述}
 例：bugfix/fix-login-issue、bugfix/correct-typo-in-readme
热修复：hotfix/{问题描述}
 例：hotfix/crash-on-launch、hotfix/fix-api-error
发布准备：release/{版本号}
 例：release/1.2.0、release/2.0.0
开发环境或测试：dev/{环境/测试名称}
 例：dev/test-api-endpoints、dev/integration-test
```

2. **开发功能**
- 遵循项目架构分层
- 编写类型注解
- 添加必要的日志

3. **提交代码**

- 提交规范 
```
git commit -m"[type]: 提交说明"其中[type]类型如下所示，且[type]后冒号为半角英文":

'feat'，// 添加新功能
'fix'，// 修复bug
'docs'，// 修改文档
'style'，//不影响代码含义的更改(比如格式化代码)
'refactor'，//重构已有代码(非新增功能或修bug)perf'，// 提高性能的代码更改
test'，// 添加或修改测试
'revert'，//用于撤销以前的commit
'chore'，//对构建或者辅助工具的更改
```

```bash
# 运行 pre-commit hooks(必须检查通过!!!)
pre-commit run --all-files

# 提交代码
git add .
git commit -m "feat: add new feature"
git push
```

### 添加新功能

1. **创建 API 路由**
```python
# app/api/routers/new_feature_router.py
from fastapi import APIRouter, Depends
from app.auth.permission_manager import permission_required

router = APIRouter(prefix="/api/v1/new-feature", tags=["新功能"])

@router.post("/create")
@permission_required("new-feature:create")
async def create_new_feature():
    # 实现逻辑
    pass
```

2. **实现业务逻辑**
```python
# app/services/new_feature_service.py
class NewFeatureService:
    async def create(self, data: NewFeatureCreate) -> NewFeature:
        # 业务逻辑实现
        pass
```

3. **添加数据模型**
```python
# app/storage/database_models.py
class NewFeature(AbstractBaseModel):
    __tablename__ = "new_features"

    name = Column(String(100), nullable=False)
    # 其他字段...
```

### 添加新的任务处理器（有后台调度的worker）

任务队列采用**按状态分表**设计，任务在四张表之间流转：`TaskPending` → `TaskRunning` → `TaskCompleted`/`TaskFailed`。

#### 1. 定义任务类型

在 `app/tasks/enums.py` 中添加：

```python
class TaskType(IntEnum):
    PLAGIARISM_CHECK = 1    # 查重任务
    REPORT_GENERATE = 2     # 报告生成
    FILE_PROCESS = 3        # 文件处理
    YOUR_NEW_TYPE = 4       # 新增类型

    @property
    def display_name(self) -> str:
        names = {
            # ...
            TaskType.YOUR_NEW_TYPE: "你的任务名称",
        }
        return names.get(self, "未知类型")
```

#### 2. 实现任务处理器

在 `app/tasks/handlers/` 目录下创建处理器：

```python
# app/tasks/handlers/your_handler.py
from typing import TYPE_CHECKING

from app.storage import AsyncSessionLocal
from app.tasks.enums import TaskType
from app.tasks.exceptions import TaskCancelledError
from app.tasks.handler import register_handler
from app.tasks.models import TaskRunning
from app.tasks.service import TaskService

if TYPE_CHECKING:
    from loguru import Logger


@register_handler(TaskType.YOUR_NEW_TYPE)
async def your_handler(task: TaskRunning, logger: "Logger") -> None:
    """你的任务处理器
    
    Args:
        task: 任务对象，包含 task.id, task.related_id, task.creator_id 等
        logger: 任务专属 logger，日志记录到独立文件
    """
    logger.info(f"开始处理任务，关联ID: {task.related_id}")
    
    # 执行业务逻辑
    for i in range(100):
        await process_item(i)
        
        # 重要：定期检查是否被取消
        if i % 20 == 0:
            async with AsyncSessionLocal() as session:
                service = TaskService(session)
                if await service.is_cancelling(task.id):
                    raise TaskCancelledError(task.id)
    
    logger.info("任务完成")
```

#### 3. 注册处理器

在 `app/tasks/handlers/__init__.py` 中导入：

```python
from . import your_handler  # 新增
```

#### 4. 创建和提交任务

```python
from app.tasks import TaskService, TaskType, submit_task

async def create_your_task(db: AsyncSession, related_id: str, user_id: str):
    service = TaskService(db)
    
    task = await service.create_task(
        task_type=TaskType.YOUR_NEW_TYPE,
        related_id=related_id,
        creator_id=user_id,
        task_name="任务名称",
    )
    await db.commit()
    
    await submit_task(task.id)  # 提交到队列
    return task
```

### 添加新的broker_task

broker_task 是taskiq的原生任务，具体使用方法可以参考taskiq官方文档。

在该项目中的使用规范可以参考app/tasks/broker_tasks/test.py

#### 1. 添加代码文件

在`app/tasks/broker_tasks`下添加定义任务函数的代码文件，具体写法可以参考已有的`test.py`。

在 `app/tasks/handlers/__init__.py` 中导入：

```python
from . import your_task  # noqa: F401
```

#### 2. 任务调用

此部分参考`taskiq`的官方文档即可，在本项目中可以查看`app/api/routers/task_test_router.py`

### 测试

* 暂无

## 部署指南

### Docker 部署

1. **构建镜像**
```bash
docker build -t scholar-guard-backend .
```

2. **使用 Docker Compose**
```bash
cd deploy/docker
docker-compose up -d
```

### 生产部署
* 待补充

</div>
