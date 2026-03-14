"""中间件模块.

提供FastAPI中间件功能，包括：
- HTTP请求/响应日志记录中间件
- 请求ID生成和上下文传递
- 客户端IP获取
- 请求处理耗时统计
- 结构化访问日志记录

支持请求追踪链路，便于问题排查和性能分析。
"""

import contextvars
import uuid
from time import perf_counter

from fastapi import FastAPI, Request
from loguru import logger

# ---- HTTP请求/响应日志记录中间件（函数式）----
request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default="-"
)


def get_client_ip(req: Request) -> str:
    """获取客户端真实IP地址.

    优先从X-Forwarded-For头获取代理服务器转发的客户端IP，
    如果没有则使用连接的客户端IP.

    Args:
        req: FastAPI请求对象

    Returns:
        str: 客户端IP地址，如果无法获取则返回"-"

    Note:
        - 支持代理服务器场景下的IP获取
        - X-Forwarded-For可能包含多个IP，取第一个
    """
    xff = req.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return req.client.host if req.client else "-"


# SKIP_PATHS = {"/health", "/metrics", "/docs", "/openapi.json"}


async def access_log_middleware(request: Request, call_next):
    """HTTP请求/响应日志记录中间件.

    为每个HTTP请求生成唯一的请求ID，记录详细的请求和响应信息。
    包括客户端IP、请求方法、路径、参数、处理时间等。

    Args:
        request: FastAPI请求对象
        call_next: 下一个中间件或路由处理函数

    Returns:
        Response: 处理后的HTTP响应对象，会添加x-request-id头

    Raises:
        Exception: 重新抛出请求处理过程中的任何异常

    Note:
        - 自动生成或传递请求ID，支持请求链路追踪
        - 记录完整的请求生命周期信息
        - 异常情况下也会记录处理时间和错误信息
    """
    log = logger.bind(log_type="system")
    # 生成或透传 request_id，并回写到响应
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    request_id_ctx.set(request_id)

    # if request.url.path in SKIP_PATHS:
    #     response = await call_next(request)
    #     response.headers["x-request-id"] = request_id
    #     return response

    start = perf_counter()
    method = request.method
    path = request.url.path
    query = str(request.url.query)
    client_ip = get_client_ip(request)
    ua = request.headers.get("user-agent", "-")
    referer = request.headers.get("referer", "-")
    host = request.headers.get("host", "-")
    scheme = request.url.scheme
    req_size = request.headers.get("content-length")

    log.info(
        f"HTTP请求: 客户端{client_ip}使用{scheme}协议/方案, 通过用户代理: {ua}, 向{host}{path}?{query}发送{method}请求。"
        f"本次请求: 请求ID: {request_id}, 请求体声明的长度: {req_size} 字节, 来源: {referer}"
    )

    try:
        response = await call_next(request)
        duration_ms = int((perf_counter() - start) * 1000)
        resp_size = response.headers.get("content-length")

        log.info(
            f"请求ID为 {request_id}的HTTP响应: 请求处理耗时: {duration_ms} 毫秒, 响应体声明的长度: {resp_size} 字节"
        )

        response.headers["x-request-id"] = request_id
        return response

    except Exception as e:
        duration_ms = int((perf_counter() - start) * 1000)
        log.error(
            f"请求ID为 {request_id}的请求在处理过程中发生异常: {str(e)}, 请求处理耗时:{duration_ms} 毫秒"
        )
        raise


# ------------------- HTTP请求/响应日志记录中间件 注册函数 -------------------


def register_middlewares(app: FastAPI):
    """在传入的 FastAPI 实例上注册所有中间件."""
    # 方式 A: 直接使用 app.middleware() 装饰器的方式调用
    # 在定义中间件后，通过一个函数来执行注册动作
    app.middleware("http")(access_log_middleware)

    # 如果有其他中间件，也可以在这里注册
    # app.middleware("http")(some_other_middleware)

    # 方式 B: 使用 BaseHTTPMiddleware 类 (更面向对象)
    # class AccessLogMiddleware(BaseHTTPMiddleware):
    #     async def dispatch(self, request: Request, call_next):
    #         return await access_log_middleware(request, call_next)
    # app.add_middleware(AccessLogMiddleware)
