"""Scholar Guard Backend 主程序模块.

该模块负责 FastAPI 应用的初始化、配置和启动。包括数据库初始化、
路由管理、中间件注册、日志配置、任务队列管理等核心功能。
"""

import importlib
import logging
import multiprocessing
import os
import sys
import time
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler

import uvicorn
from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from loguru import logger

from app.common.time_ import human_duration
from app.configs import base_configs
from app.services.demo_service import demo_service
from app.services.student_service import student_service
from app.storage import init_db, stop_db
from app.utils.async_worker_id_allocator import worker_id_allocator
from app.utils.handle_exceptions import (
    init_loop_exc_handler,
    register_exception_handlers,
)
from app.utils.middlewares import register_middlewares
from app.utils.snowflake_id import snowflake_id_gen


def setup_logging():
    """配置 Uvicorn 日志处理器.

    设置 RotatingFileHandler 来记录 uvicorn 和 uvicorn.access 的日志，
    支持日志文件轮转，避免日志文件过大。

    日志文件位置：PROJECT_LOG_DIR/fastapi.log
    - 单个文件最大：100MB
    - 保留备份数：5个
    - 编码格式：UTF-8
    """
    logger_handler: RotatingFileHandler = RotatingFileHandler(
        base_configs.PROJECT_LOG_DIR + "/fastapi.log",
        maxBytes=100 * 1024 * 1024,  # 单个日志文件最大 10MB
        backupCount=5,  # 最多保留 5 个旧日志文件
        encoding="utf-8",  # 避免中文乱码
    )
    logging.getLogger("uvicorn").addHandler(logger_handler)
    logging.getLogger("uvicorn.access").addHandler(logger_handler)


router_lis: list[str] = []


def _router_prefix_name(module_base_name: str) -> str:
    """Convert router module name to URL prefix suffix."""

    if module_base_name.endswith("_router"):
        return module_base_name[: -len("_router")]
    if module_base_name.endswith("router"):
        return module_base_name[: -len("router")]
    return module_base_name

routers_dir = os.path.join(base_configs.PROJECT_DIR, "app/api/routers")
for filename in os.listdir(routers_dir):
    name: str = filename.split(".")[0]
    if name in {"admin_base_router", "admin_log_router"}:
        continue
    if name.endswith("router") and filename != "__init__":
        router_lis.append(name)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """管理 FastAPI 应用的启动和关闭生命周期.

    负责应用启动时的初始化工作和关闭时的清理工作。
    启动阶段包括：数据库初始化、权限管理器初始化、日志配置、任务队列启动等。
    关闭阶段包括：优雅停机、日志队列清理、数据库连接关闭等。

    Args:
        app (FastAPI): FastAPI 应用实例

    Yields:
        None: 应用运行期间的控制权交给 FastAPI

    Raises:
        Exception: 启动阶段或运行期间的任何异常
    """
    print("获取 worker_id")
    base_configs.WORKER_ID = await worker_id_allocator.acquire()
    print(f"获取到 worker_id: {base_configs.WORKER_ID}")
    # -----------------------------------------------------------
    snowflake_id_gen.init_generator()
    log = logger.bind(log_type="system")
    _pid = os.getpid()  # 区分不同 worker 进程
    _t0 = time.perf_counter()  # 计算运行时长（单调时钟）

    try:
        print("初始化数据库")
        await init_db()  # 初始化数据库
        print("数据库初始化完成")

        print("初始化s3存储桶")
        print("s3存储桶初始化完成")

        # 初始化事件循环级异常处理器
        await demo_service.bootstrap()
        await student_service.bootstrap()
        await init_loop_exc_handler()

        print("🔍 开始动态加载路由模块...")
        include_routers(app)  # 动态加载路由
        print("✅ 路由加载完毕")

        setup_logging()  # 配置日志

        log.info(f"进程ID:{_pid} 正在启动服务")

        log.info(
            f"进程ID: {_pid} 启动服务 端口号: {base_configs.PROJECT_PORT}, 服务单元数: {base_configs.PROJECT_WORKERS}"
        )
    except Exception as e:
        # —— 启动阶段失败（yield 之前报错） ——
        log.error(f"进程ID:{_pid} 服务启动失败, 错误:{str(e)}")
        raise
    try:
        yield  # FastAPI 继续运行
    # 捕获会导致进程退出的顶层异常
    except Exception as e:
        log.error(f"进程ID: {_pid} 服务运行期间发生错误: {str(e)}")
        raise
    finally:
        # 关闭事件
        uptime = time.perf_counter() - _t0
        log.info(
            f"进程ID: {_pid} 停止服务, 开始执行优雅停机流程, 服务累计运行 {human_duration(uptime)}"
        )
        try:
            await stop_db()
            log.info("数据库连接池已关闭")
        except Exception as e:
            log.error(f"数据库连接池关闭失败: {str(e)}")

        log.info(f"进程 {_pid} 优雅停机完成")

        # 8. 关闭事件
        print("关闭事件")
        print("退出服务")


def include_routers(app: FastAPI):
    """动态加载并注册路由模块.

    根据预定义的路由模块列表，动态导入各个路由模块并将其
    注册到 FastAPI 应用中。支持开发和生产环境的不同处理方式。

    Args:
        app (FastAPI): FastAPI 应用实例

    Raises:
        AssertionError: 当模块的 router 属性不是 APIRouter 实例时
        SystemExit: 生产环境下导入失败时退出程序
    """
    if base_configs.ENV == "dev":
        for module_base_name in router_lis:
            module_name = f".api.routers.{module_base_name}"
            try:
                module = importlib.import_module(module_name, package="app")
                print(f"  ✅ 导入模块: {module_name}")
                if hasattr(module, "router"):
                    assert isinstance(module.router, APIRouter), (
                        f"{module_name}.router is not APIRouter"
                    )
                    prefix = f"{base_configs.API_PREFIX}/{_router_prefix_name(module_base_name)}"
                    app.include_router(module.router, prefix=prefix)
                    print(f"  📦 挂载路由 -> 前缀: {prefix}")
                else:
                    print(f"  ❌ 模块 {module_name} 中未找到 'router' 实例")
            except Exception as e:
                print(f"  ❌ 无法导入 {module_name}: {e}")
    else:
        for module_base_name in router_lis:
            module_name = f".api.routers.{module_base_name}"
            try:
                module = importlib.import_module(module_name, package="app")
                if hasattr(module, "router"):
                    assert isinstance(module.router, APIRouter), (
                        f"{module_base_name}.router is not APIRouter"
                    )
                    prefix = f"{base_configs.API_PREFIX}/{_router_prefix_name(module_base_name)}"
                    app.include_router(module.router, prefix=prefix)
                else:
                    sys.exit()
            except Exception:
                sys.exit()


if base_configs.ENV != "dev":
    app = FastAPI(
        lifespan=lifespan,
        title=base_configs.PROJECT_NAME,
        docs_url=None,  # 禁用 /docs
        redoc_url=None,  # 禁用 /redoc
        openapi_url=None,
    )  # 禁用 /openapi.json
else:
    app = FastAPI(lifespan=lifespan, title=base_configs.PROJECT_NAME)


# 调用注册函数，注册中间件
register_middlewares(app)

# 2. 注册异常处理器
register_exception_handlers(app)

# 添加 CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 配置静态资源挂载路径
app.mount(
    "/static_resources",
    StaticFiles(directory=base_configs.PROJECT_DATA_DIR),
    name="static_resources",
)


def main():
    """主函数 - 启动 FastAPI 应用服务.

    负责启动整个应用程序，包括：
    - 检查运行环境（开发/生产）
    - 配置并启动 Uvicorn 服务器
    - 处理服务停止时的清理工作

    使用多进程模式运行，支持配置多个 worker 进程。
    """
    if base_configs.ENV == "dev":
        print("注意! 当前为开发环境")
    multiprocessing.freeze_support()
    # 启动 Uvicorn 服务器
    print(
        f"Starting server on http://{base_configs.PROJECT_HOST}:{base_configs.PROJECT_PORT}"
    )

    try:
        uvicorn.run(
            app="app.main:app",
            # app=app,
            host=base_configs.PROJECT_HOST,
            port=base_configs.PROJECT_PORT,
            workers=base_configs.PROJECT_WORKERS,
        )
    except Exception as e:
        print("服务停止", e)


if __name__ == "__main__":
    main()
