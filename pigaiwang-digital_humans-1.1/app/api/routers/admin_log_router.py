"""日志管理API路由。

提供日志查询和管理相关的API端点，包括：
- 系统日志查询和导出
- 用户行为日志查询和导出
- 管理员操作日志查询和导出
- 支持多维度筛选（时间、级别、用户名等）
- 分页查询和Excel导出功能
"""

from fastapi import APIRouter
from loguru import logger

from app.api.form_response.admin_log_response import (
    AdminLogResponseModel,
    SystemLogResponseModel,
    UserLogResponseModel,
)
from app.api.form_response.base import BaseResponseModel, PaginatedResponseModel
from app.api.form_validation.admin_log_validation import (
    AdminLogsRequest,
    SystemLogsRequest,
    UserLogsRequest,
)
from app.auth import UserClaims, get_current_user_dependency  # 假设你还保留了这个依赖
from app.services.admin_log_service import admin_log_service

router = APIRouter(tags=["admin_log"])


@router.post(
    "/system/logs",
    response_model=PaginatedResponseModel[list[SystemLogResponseModel]],
    summary="获取系统日志（分页）",
)
async def get_system_logs(
    system_logs_request: SystemLogsRequest,
    current_user: UserClaims = get_current_user_dependency,  # 可选：如果不需要登录，可删除这一行
):
    """分页查询系统日志，支持按日志级别和时间范围过滤。"""
    log = logger.bind(
        log_type="user", user_id=current_user.user_id if current_user else "anonymous"
    )

    res, code, msg, total, data = await admin_log_service.get_system_logs(
        level=system_logs_request.level,
        start_time=system_logs_request.start_time,
        end_time=system_logs_request.end_time,
        skip=system_logs_request.skip,
        limit=system_logs_request.limit,
    )

    if not res:
        log.error(msg)
    else:
        log.info(msg)

    return {
        "res": res,
        "code": code,
        "message": msg,
        "total": total,
        "skip": system_logs_request.skip,
        "limit": system_logs_request.limit,
        "data": data,
    }


@router.get(
    "/system/log",
    response_model=BaseResponseModel[SystemLogResponseModel],
    summary="通过id获取系统日志详情",
)
async def get_system_log_by_id(
    log_id: str,
    current_user: UserClaims = get_current_user_dependency,  # 可选
):
    """根据日志ID查询单条系统日志的详细信息。"""
    log = logger.bind(
        log_type="user", user_id=current_user.user_id if current_user else "anonymous"
    )

    res, code, msg, data = await admin_log_service.get_system_log_by_id(log_id=log_id)

    if not res:
        log.error(msg)
    else:
        log.info(msg)

    return {
        "res": res,
        "code": code,
        "message": msg,
        "data": data,
    }


@router.post(
    "/admin/logs",
    response_model=PaginatedResponseModel[list[AdminLogResponseModel]],
    summary="获取管理日志（分页）",
)
async def get_admin_logs(
    admin_logs_request: AdminLogsRequest,
    current_user: UserClaims = get_current_user_dependency,  # 可选
):
    """分页查询管理日志，记录管理员的所有操作行为。"""
    log = logger.bind(
        log_type="user", user_id=current_user.user_id if current_user else "anonymous"
    )

    res, code, msg, total, data = await admin_log_service.get_admin_logs(
        user_name=admin_logs_request.user_name,
        level=admin_logs_request.level,
        start_time=admin_logs_request.start_time,
        end_time=admin_logs_request.end_time,
        skip=admin_logs_request.skip,
        limit=admin_logs_request.limit,
    )

    if not res:
        log.error(msg)
    else:
        log.info(msg)

    return {
        "res": res,
        "code": code,
        "message": msg,
        "total": total,
        "skip": admin_logs_request.skip,
        "limit": admin_logs_request.limit,
        "data": data,
    }


@router.get(
    "/admin/log",
    response_model=BaseResponseModel[AdminLogResponseModel],
    summary="通过id获取管理日志详情",
)
async def get_admin_log_by_id(
    log_id: str,
    current_user: UserClaims = get_current_user_dependency,  # 可选
):
    """根据日志ID查询单条管理日志的详细信息。"""
    log = logger.bind(
        log_type="user", user_id=current_user.user_id if current_user else "anonymous"
    )

    res, code, msg, data = await admin_log_service.get_admin_log_by_id(log_id=log_id)

    if not res:
        log.error(msg)
    else:
        log.info(msg)

    return {
        "res": res,
        "code": code,
        "message": msg,
        "data": data,
    }


@router.post(
    "/user/logs",
    response_model=PaginatedResponseModel[list[UserLogResponseModel]],
    summary="获取用户日志（分页）",
)
async def get_user_logs(
    user_logs_request: UserLogsRequest,
    current_user: UserClaims = get_current_user_dependency,  # 可选
):
    """分页查询用户日志，记录普通用户的操作行为。"""
    log = logger.bind(
        log_type="user", user_id=current_user.user_id if current_user else "anonymous"
    )

    res, code, msg, total, data = await admin_log_service.get_user_logs(
        user_name=user_logs_request.user_name,
        level=user_logs_request.level,
        start_time=user_logs_request.start_time,
        end_time=user_logs_request.end_time,
        skip=user_logs_request.skip,
        limit=user_logs_request.limit,
    )

    if not res:
        log.error(msg)
    else:
        log.info(msg)

    return {
        "res": res,
        "code": code,
        "message": msg,
        "total": total,
        "skip": user_logs_request.skip,
        "limit": user_logs_request.limit,
        "data": data,
    }


@router.get(
    "/user/log",
    response_model=BaseResponseModel[UserLogResponseModel],
    summary="通过id获取用户日志详情",
)
async def get_user_log_by_id(
    log_id: str,
    current_user: UserClaims = get_current_user_dependency,  # 可选
):
    """根据日志ID查询单条用户日志的详细信息。"""
    log = logger.bind(
        log_type="user", user_id=current_user.user_id if current_user else "anonymous"
    )

    res, code, msg, data = await admin_log_service.get_user_log_by_id(log_id=log_id)

    if not res:
        log.error(msg)
    else:
        log.info(msg)

    return {
        "res": res,
        "code": code,
        "message": msg,
        "data": data,
    }
