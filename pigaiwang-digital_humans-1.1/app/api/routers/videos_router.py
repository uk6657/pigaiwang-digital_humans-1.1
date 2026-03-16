"""Routers for local video cache testing APIs."""

from fastapi import APIRouter, Depends

from app.api.form_response import BaseResponseModel
from app.api.form_response.demo_response import (
    VideoCacheManifestResponseModel,
    VideoCacheVersionResponseModel,
)
from app.auth.demo_dependency import get_current_demo_user
from app.services.demo_service import demo_service
from app.storage import UserModel

router = APIRouter(tags=["videos"])


@router.get(
    "/cache-manifest",
    response_model=BaseResponseModel[VideoCacheManifestResponseModel],
    summary="Get video cache manifest",
)
async def get_cache_manifest(
    current_user: UserModel = Depends(get_current_demo_user),
):
    """Return the full downloadable video manifest for local cache clients."""

    payload = await demo_service.list_cache_manifest()
    return {
        "res": True,
        "code": 200,
        "message": "Video cache manifest fetched successfully",
        "data": {"videos": payload},
    }


@router.get(
    "/downloadable-manifest",
    response_model=BaseResponseModel[VideoCacheManifestResponseModel],
    summary="Get downloadable uploaded videos",
)
async def get_downloadable_manifest(
    current_user: UserModel = Depends(get_current_demo_user),
):
    """Return only videos that are real uploaded files and can be downloaded."""

    payload = await demo_service.list_downloadable_manifest()
    return {
        "res": True,
        "code": 200,
        "message": "Downloadable video manifest fetched successfully",
        "data": {"videos": payload},
    }


@router.get(
    "/cache-versions",
    response_model=BaseResponseModel[VideoCacheVersionResponseModel],
    summary="Get video cache versions",
)
async def get_cache_versions(
    current_user: UserModel = Depends(get_current_demo_user),
):
    """Return compact version info for local cache update checks."""

    payload = await demo_service.list_cache_versions()
    return {
        "res": True,
        "code": 200,
        "message": "Video cache versions fetched successfully",
        "data": {"videos": payload},
    }


@router.get(
    "/{video_id}/download",
    summary="Download original video file",
    response_model=None,
)
async def download_video(
    video_id: int,
    current_user: UserModel = Depends(get_current_demo_user),
):
    """Download the original uploaded video file for local caching."""

    return await demo_service.download_video_file(video_id)
