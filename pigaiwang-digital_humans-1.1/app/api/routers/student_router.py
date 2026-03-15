"""Student task and script router."""

from fastapi import APIRouter, Depends

from app.api.form_response import BaseResponseModel
from app.api.form_response.student_response import (
    GroupTaskResponseModel,
    StudentRenameResponseModel,
    StudentScriptsResponseModel,
    StudentSummaryResponseModel,
    TaskScriptBatchResponseModel,
)
from app.api.form_validation.student_validation import (
    StudentRenameRequest,
    TaskScriptBatchRequest,
)
from app.auth.demo_dependency import get_current_demo_claims, get_current_demo_user
from app.services.student_service import student_service
from app.storage import UserModel

router = APIRouter(tags=["student"])


@router.get(
    "/students/{student_id}",
    response_model=BaseResponseModel[StudentSummaryResponseModel],
    summary="Get one student by id",
)
async def get_student(
    student_id: int,
    claims=Depends(get_current_demo_claims),
):
    """Return one student by id for any authenticated teacher or student token."""

    student = await student_service.get_student(student_id)

    return {
        "res": True,
        "code": 200,
        "message": "Student fetched successfully",
        "data": {
            "student_id": str(student.student_id),
            "group_id": student.group_id,
            "username": student.username,
            "student_name": student.student_name,
        },
    }


@router.patch(
    "/students/{student_id}/name",
    response_model=BaseResponseModel[StudentRenameResponseModel],
    summary="Rename one student",
)
async def rename_student(
    student_id: int,
    request: StudentRenameRequest,
    claims=Depends(get_current_demo_claims),
):
    """Update one student's display name for any authenticated teacher or student token."""

    payload = await student_service.rename_student(
        student_id=student_id,
        student_name=request.student_name,
    )
    return {
        "res": True,
        "code": 200,
        "message": "Student name updated successfully",
        "data": payload,
    }


@router.get(
    "/students/{student_id}/task",
    response_model=BaseResponseModel[GroupTaskResponseModel],
    summary="Get one student's task",
)
async def get_student_task(
    student_id: int,
    claims=Depends(get_current_demo_claims),
):
    """Return one student's task for any authenticated teacher or student token."""

    payload = await student_service.get_student_task(student_id)
    return {
        "res": True,
        "code": 200,
        "message": "Student task fetched successfully",
        "data": payload,
    }


@router.get(
    "/students/{student_id}/scripts",
    response_model=BaseResponseModel[StudentScriptsResponseModel],
    summary="Get one student's scripts",
)
async def get_student_scripts_by_id(
    student_id: int,
    claims=Depends(get_current_demo_claims),
):
    """Return one student's scripts for any authenticated teacher or student token."""

    payload = await student_service.get_student_scripts(student_id)
    return {
        "res": True,
        "code": 200,
        "message": "Student scripts fetched successfully",
        "data": payload,
    }


@router.put(
    "/tasks/config-batch",
    response_model=BaseResponseModel[TaskScriptBatchResponseModel],
    summary="Replace all student tasks and scripts",
)
async def save_task_script_batch(
    request: TaskScriptBatchRequest,
    current_user: UserModel = Depends(get_current_demo_user),
):
    """Replace all student tasks and scripts with the submitted payload."""

    payload = await student_service.save_task_script_batch(request.model_dump())
    return {
        "res": True,
        "code": 200,
        "message": "Task and script config saved successfully",
        "data": payload,
    }


@router.get(
    "/tasks/config-batch",
    response_model=BaseResponseModel[TaskScriptBatchResponseModel],
    summary="Get all student tasks and scripts",
)
async def get_task_script_batch(
    claims=Depends(get_current_demo_claims),
):
    """Return the full stored task/script payload for any authenticated token."""

    payload = await student_service.get_full_task_script_payload()
    return {
        "res": True,
        "code": 200,
        "message": "Task and script config fetched successfully",
        "data": payload,
    }


@router.get(
    "/groups/{group_id}/tasks",
    response_model=BaseResponseModel[GroupTaskResponseModel],
    summary="Get all tasks for one group",
)
async def get_group_tasks(
    group_id: int,
    current_user: UserModel = Depends(get_current_demo_user),
):
    """Return all student tasks for one group."""

    payload = await student_service.get_group_tasks(group_id)
    return {
        "res": True,
        "code": 200,
        "message": "Group tasks fetched successfully",
        "data": payload,
    }
