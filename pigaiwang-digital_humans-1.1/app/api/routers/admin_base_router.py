"""管理员认证相关API路由。

提供管理员登录认证相关的API端点，包括：
- 管理员登录认证
- 管理员退出登录
- 获取超级管理员ID
- 系统/管理日志导出

登录相关接口无需登录，其他接口需要登录。
"""

from fastapi import APIRouter
from loguru import logger

from app.api.form_response import BaseResponseModel
from app.api.form_response.admin_response import (
    AdminUserIDResponseModel,
    CodeImageResponseModel,
    LoginResponseModel,
)
from app.api.form_validation.admin_validation import (
    AdminLoginByPhonePasswordRequest,
    AdminLoginByUsernamePasswordRequest,
    ExportSystemLogsRequest,
    ExportUserLogsRequest,
)
from app.auth import UserClaims, get_current_user_dependency
from app.services.admin_service import admin_service

router = APIRouter(tags=["admin认证"])


@router.post(
    "/code_image",
    response_model=BaseResponseModel[CodeImageResponseModel],
    summary="获取数字验证码图形",
)
async def back_code_image():
    """获取数字验证码图形

    **说明：**
    - 随机生成一个四位数字，并转为字符串类型，作为数字验证码
    - 生成一张数字验证码图形，并进行 base64 编码
    - 生成雪花ID作为唯一标识
    - 将验证码ID和值存入 Redis，设置 60 秒过期
    - 返回 base64 编码的图形和 ID，客户端可直接渲染
    """
    log = logger.bind(log_type="system")
    res, code, message, data = await admin_service.get_code_image()
    log.info(message)
    return {"res": res, "code": code, "message": message, "data": data}


@router.post(
    "/username-login",
    response_model=BaseResponseModel[LoginResponseModel],
    summary="用户名密码登录",
)
async def login_by_username_password(
    login_request: AdminLoginByUsernamePasswordRequest,
):
    """管理员通过用户名密码登录系统，获取访问令牌。

    **说明：**
    - 该接口会对用户名密码进行格式校验
    """
    # _check_license_()  # 校验license是否过期，勿删

    payload = login_request.model_dump()
    log = logger.bind(log_type="user")

    log.info(f"用户名为 {login_request.username} 的管理员尝试登录管理后台")
    res, code, message, data = await admin_service.login_by_password(**payload)  # type: ignore
    log.info(message)
    return {"res": res, "code": code, "message": message, "data": data}


@router.post(
    "/phone-login",
    response_model=BaseResponseModel[LoginResponseModel],
    summary="手机号密码登录",
)
async def login_by_phone_password(login_request: AdminLoginByPhonePasswordRequest):
    """管理员通过手机号密码登录系统，获取访问令牌。

    **说明：**
    - 该接口会对手机号密码进行格式校验
    """
    # _check_license_()  # 校验license是否过期，勿删

    payload = login_request.model_dump()
    log = logger.bind(log_type="user")

    log.info(f"手机号为 {login_request.phone} 的管理员尝试登录管理后台")
    res, code, message, data = await admin_service.login_by_phone_and_password(
        **payload
    )  # type: ignore

    log.info(message)
    return {"res": res, "code": code, "message": message, "data": data}


@router.get(
    "/admin_user_id",
    response_model=BaseResponseModel[AdminUserIDResponseModel],
    summary="获取超级管理员ID",
)
async def get_admin_user_id(
    current_user: UserClaims = get_current_user_dependency,
):
    """获取系统中超级管理员的用户ID，用于前端标识超级管理员身份。

    **说明：**
    - 需要管理员登录后才能访问
    - 前端获取后用于标识超级管理员，实现特殊权限控制
    """
    log = logger.bind(log_type="user", user_id=current_user.user_id)
    log.info("尝试获取超级管理员ID")
    res, code, message, data = admin_service.get_admin_user_id()
    log.info(message)

    return {"res": res, "code": code, "message": message, "data": data}


@router.get(
    "/logout",
    response_model=BaseResponseModel,
    summary="退出登录",
)
async def logout(
    current_user: UserClaims = get_current_user_dependency,
):
    """管理员主动退出登录，清除服务器端的访问令牌使其失效。

    **说明：**
    - 退出后 token 立即失效，用户需要重新登录
    - 只影响当前设备，不影响其他设备登录状态
    """
    log = logger.bind(log_type="user", user_id=current_user.user_id)
    log.info("退出登录")
    res, code, message, data = await admin_service.logout(current_user.user_id)  # type: ignore
    log.info(message)
    return {"res": res, "code": code, "message": message, "data": data}


@router.post(
    "/export_system_logs",
    response_model=None,
    summary="导出系统日志",
)
async def export_system_logs(
    request: ExportSystemLogsRequest,
    current_user: UserClaims = get_current_user_dependency,
):
    """根据筛选条件导出系统日志数据为 Excel 文件，支持流式下载。

    **说明：**
    - 仅导出系统自动产生的日志，不包括用户操作日志
    - 返回 Excel 格式的文件流
    - 大量数据导出可能需要较长时间
    """
    log = logger.bind(log_type="user", user_id=current_user.user_id)
    log.info("尝试导出系统日志")
    return await admin_service.export_system_logs(log, **request.model_dump())  # type: ignore


@router.post(
    "/export_admin_logs",
    response_model=None,
    summary="导出管理日志",
)
async def export_admin_logs(
    request: ExportUserLogsRequest,
    current_user: UserClaims = get_current_user_dependency,
):
    """根据筛选条件导出管理员操作日志数据为 Excel 文件，支持流式下载。

    **说明：**
    - 仅导出管理员操作产生的日志，不包括系统自动日志
    - 返回 Excel 格式的文件流
    - 大量数据导出可能需要较长时间
    """
    log = logger.bind(log_type="user", user_id=current_user.user_id)
    log.info("尝试导出管理日志")
    return await admin_service.export_user_logs(
        log, **request.model_dump(), is_user=False
    )  # type: ignore
