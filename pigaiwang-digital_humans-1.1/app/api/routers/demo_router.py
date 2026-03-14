"""Routers for the digital human demo APIs."""

from __future__ import annotations

import mimetypes
import re

from fastapi import APIRouter, Depends, File, Form, Header, Response, UploadFile
from fastapi.responses import StreamingResponse

from app.api.form_response import BaseResponseModel
from app.api.form_response.demo_response import (
    DemoGroupBatchConfigResponseModel,
    DemoGroupResponseModel,
    DemoGroupVideoConfigResponseModel,
    DemoUserResponseModel,
    DemoVideoResponseModel,
)
from app.api.form_validation.demo_validation import (
    DemoGroupBatchConfigRequest,
    GroupVideoConfigSaveRequest,
)
from app.auth.demo_dependency import get_current_demo_user
from app.services.demo_service import demo_service
from app.storage import UserModel

router = APIRouter(tags=["demo"])


def _video_to_dict(video) -> dict:
    """Normalize ORM rows and plain dicts into response payloads."""

    if isinstance(video, dict):
        return video
    return demo_service.serialize_video(video)


@router.get(
    "/me",
    response_model=BaseResponseModel[DemoUserResponseModel],
    summary="Get current demo user",
)
async def get_me(current_user: UserModel = Depends(get_current_demo_user)):
    """Return the currently authenticated user."""

    return {
        "res": True,
        "code": 200,
        "message": "Current user fetched successfully",
        "data": {
            "id": str(current_user.id),
            "username": current_user.username,
            "type": current_user.type,
            "display_name": current_user.display_name,
        },
    }


@router.get(
    "/groups",
    response_model=BaseResponseModel[list[DemoGroupResponseModel]],
    summary="List fixed demo groups",
)
async def list_groups(current_user: UserModel = Depends(get_current_demo_user)):
    """Return all available demo groups."""

    groups = await demo_service.list_groups()
    return {
        "res": True,
        "code": 200,
        "message": "Groups fetched successfully",
        "data": groups,
    }


@router.put(
    "/groups/config-batch",
    response_model=BaseResponseModel[DemoGroupBatchConfigResponseModel],
    summary="Save all group configs from frontend payload",
)
async def save_batch_group_config(
    request: DemoGroupBatchConfigRequest,
    current_user: UserModel = Depends(get_current_demo_user),
):
    """Save the full frontend group config payload."""

    payload = await demo_service.save_batch_group_config(
        [item.model_dump() for item in request.groups],
        updated_by=current_user.id,
    )
    return {
        "res": True,
        "code": 200,
        "message": "Batch group config saved successfully",
        "data": payload,
    }


@router.get(
    "/videos",
    response_model=BaseResponseModel[list[DemoVideoResponseModel]],
    summary="List video resources",
)
async def list_videos(
    group_id: int | None = None,
    current_user: UserModel = Depends(get_current_demo_user),
):
    """Return all videos, optionally filtered by group id."""

    videos = await demo_service.list_videos(group_id=group_id)
    return {
        "res": True,
        "code": 200,
        "message": "Videos fetched successfully",
        "data": [_video_to_dict(video) for video in videos],
    }


@router.post(
    "/videos",
    response_model=BaseResponseModel[DemoVideoResponseModel],
    summary="Upload a video file",
)
async def create_video(
    file: UploadFile = File(..., description="Video file to upload"),
    video_name: str = Form(...),
    description: str | None = Form(default=None),
    external_video_id: str | None = Form(default=None),
    current_user: UserModel = Depends(get_current_demo_user),
):
    """Upload a video file, persist it locally, and create/update metadata."""

    payload = await demo_service.upload_video(
        upload_file=file,
        video_name=video_name,
        description=description,
        external_video_id=external_video_id,
    )
    return {
        "res": True,
        "code": 200,
        "message": "Video created successfully",
        "data": payload,
    }


@router.get(
    "/videos/{video_id}",
    response_model=BaseResponseModel[DemoVideoResponseModel],
    summary="Get video detail",
)
async def get_video_detail(
    video_id: int,
    current_user: UserModel = Depends(get_current_demo_user),
):
    """Return metadata for a single video."""

    video = await demo_service.get_video_detail(video_id)
    return {
        "res": True,
        "code": 200,
        "message": "Video detail fetched successfully",
        "data": _video_to_dict(video),
    }


@router.delete(
    "/videos/{video_id}",
    response_model=BaseResponseModel[dict],
    summary="Delete a video",
)
async def delete_video(
    video_id: int,
    current_user: UserModel = Depends(get_current_demo_user),
):
    """Soft-delete a video."""

    await demo_service.delete_video(video_id)
    return {
        "res": True,
        "code": 200,
        "message": "Video deleted successfully",
        "data": {"id": video_id},
    }


@router.get(
    "/groups/{group_id}/videos",
    response_model=BaseResponseModel[DemoGroupVideoConfigResponseModel],
    summary="Get configured group videos",
)
async def get_group_videos(
    group_id: int,
    current_user: UserModel = Depends(get_current_demo_user),
):
    """Return the saved ordered video list for a group."""

    payload = await demo_service.get_group_video_config(group_id)
    return {
        "res": True,
        "code": 200,
        "message": "Group video config fetched successfully",
        "data": payload,
    }


@router.put(
    "/groups/{group_id}/videos",
    response_model=BaseResponseModel[DemoGroupVideoConfigResponseModel],
    summary="Save ordered group videos",
)
async def save_group_videos(
    group_id: int,
    request: GroupVideoConfigSaveRequest,
    current_user: UserModel = Depends(get_current_demo_user),
):
    """Persist the frontend-ordered video ids for a group."""

    payload = await demo_service.save_group_video_config(
        group_id=group_id,
        video_ids=request.video_ids,
        updated_by=current_user.id,
    )
    return {
        "res": True,
        "code": 200,
        "message": "Group video config saved successfully",
        "data": payload,
    }


@router.get(
    "/videos/{video_id}/stream",
    summary="Stream local video with HTTP range support",
    response_model=None,
)
async def stream_video(
    video_id: int,
    range_header: str | None = Header(default=None, alias="Range"),
):
    """Stream a local video file for HTML video playback."""

    file_path = await demo_service.get_video_path(video_id)
    file_size = file_path.stat().st_size
    media_type = mimetypes.guess_type(file_path.name)[0] or "video/mp4"

    start = 0
    end = file_size - 1
    status_code = 200
    headers = {"Accept-Ranges": "bytes"}

    if range_header:
        match = re.match(r"bytes=(\d*)-(\d*)", range_header)
        if match:
            start_str, end_str = match.groups()
            if start_str:
                start = int(start_str)
            if end_str:
                end = int(end_str)
            else:
                end = file_size - 1

            if start > end or start >= file_size:
                return Response(
                    status_code=416,
                    headers={"Content-Range": f"bytes */{file_size}"},
                )

            status_code = 206
            headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"

    content_length = end - start + 1
    headers["Content-Length"] = str(content_length)

    def file_iterator():
        with file_path.open("rb") as file_obj:
            file_obj.seek(start)
            remaining = content_length
            while remaining > 0:
                chunk = file_obj.read(min(1024 * 1024, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    return StreamingResponse(
        file_iterator(),
        status_code=status_code,
        media_type=media_type,
        headers=headers,
    )
