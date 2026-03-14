"""全局异常处理器模块.

定义FastAPI应用的全局异常处理函数，统一处理各种异常情况：
- HTTP异常处理
- 请求参数验证异常处理
- 全局未捕获异常处理
- 事件循环异常处理

所有异常都会记录日志并返回统一的响应格式。
"""

import asyncio

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from loguru import logger
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.form_response import BaseResponseModel


# http 异常处理器
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """处理HTTP异常.

    捕获并处理HTTP层面的异常，如404、403等.
    记录错误日志并返回统一格式的错误响应。

    Args:
        request: FastAPI请求对象
        exc: HTTP异常对象，包含状态码和错误详情

    Returns:
        JSONResponse: 包含错误信息的JSON响应
    """
    log = logger.bind(log_type="system")
    log.error(f"请求异常 {request.method} {request.url.path} -> {exc.detail}")
    payload = BaseResponseModel(
        res=False,
        code=exc.status_code,
        message=exc.detail,
        data={"errors": exc.detail},  # 详细的验证错误信息
    )
    return JSONResponse(payload.model_dump(mode="json"), status_code=exc.status_code)


# 请求参数验证异常处理器
async def request_validation_exception_handler(
    request: Request, exc: RequestValidationError
):
    """处理请求参数验证异常.

    当请求参数不符合Pydantic模型定义时触发。
    返回详细的字段验证错误信息，帮助客户端调试。

    Args:
        request: FastAPI请求对象
        exc: 请求验证异常对象，包含具体的字段错误

    Returns:
        JSONResponse: 包含验证错误详情的JSON响应，状态码为422
    """
    log = logger.bind(log_type="system")
    log.error(f"请求参数验证失败 {request.method} {request.url.path} -> {exc.errors()}")
    response_status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    payload = BaseResponseModel(
        res=False,
        code=response_status_code,
        message="请求参数验证失败",
        data={"errors": exc.errors()},  # 详细的验证错误信息
    )
    return JSONResponse(
        payload.model_dump(mode="json"), status_code=response_status_code
    )


# 全局异常处理器（兜未捕获的请求异常）
async def all_exception_handler(request: Request, exc: Exception):
    """处理全局未捕获异常.

    作为最后的异常捕获点，处理所有未被特定处理器捕获的异常。
    确保系统不会因未处理异常而崩溃，并返回友好的错误信息。

    Args:
        request: FastAPI请求对象
        exc: 未捕获的异常对象

    Returns:
        JSONResponse: 包含错误信息的JSON响应，状态码为500

    Note:
        这是异常处理的最后一道防线，应该避免依赖可能抛出异常的代码
    """
    log = logger.bind(log_type="system")
    log.error(
        f"HTTP请求/响应过程中未捕获的异常 {request.method} {request.url.path} -> {str(exc)}"
    )
    response_status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    payload = BaseResponseModel(
        res=False, code=response_status_code, message=str(exc), data=None
    )
    return JSONResponse(
        payload.model_dump(mode="json"), status_code=response_status_code
    )


# 全局异常处理器 注册函数
def register_exception_handlers(app: FastAPI):
    """在传入的 FastAPI 实例上注册所有异常处理器."""
    app.exception_handler(StarletteHTTPException)(http_exception_handler)

    app.exception_handler(RequestValidationError)(request_validation_exception_handler)

    # 注册针对 Exception 类的全局处理器
    app.exception_handler(Exception)(all_exception_handler)

    # 如果您有针对特定 HTTP 错误的处理器，也可以在这里注册
    # 例如： app.exception_handler(404)(not_found_handler)


# 事件循环级异常处理器
def handle_loop_exc(loop, context):
    """处理事件循环级异常.

    捕获并记录asyncio事件循环中的异常。
    这些异常通常发生在后台任务或异步操作中。

    Args:
        loop: 异步事件循环对象
        context: 异常上下文字典，包含message和exception等信息

    Note:
        此函数不会阻止事件循环继续运行，仅记录错误信息
    """
    msg = context.get("message")
    log = logger.bind(log_type="system")
    log.error(f"事件循环级错误,上下文message:{msg}")
    if context.get("exception"):
        exc = context["exception"]
        log.error(f"事件循环级错误,上下文exception{exc}")


# 事件循环异常处理器 初始化函数
async def init_loop_exc_handler():
    """初始化事件循环异常处理器.

    获取当前运行的事件循环并设置异常处理函数。
    应该在应用启动时调用，以确保所有事件循环异常都被正确处理。

    Note:
        必须在异步上下文中调用此函数
    """
    loop = asyncio.get_running_loop()
    loop.set_exception_handler(handle_loop_exc)
