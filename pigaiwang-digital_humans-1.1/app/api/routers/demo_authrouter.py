"""Minimal auth router for the digital human demo project."""

from fastapi import APIRouter

from app.api.form_response import BaseResponseModel
from app.api.form_response.demo_auth_response import DemoLoginResponseModel
from app.api.form_validation.demo_auth_validation import DemoLoginRequest
from app.services.demo_auth_service import demo_auth_service

router = APIRouter(tags=["demo-auth"])


@router.post(
    "/login",
    response_model=BaseResponseModel[DemoLoginResponseModel],
    summary="Minimal login endpoint for demo users",
)
async def login(request: DemoLoginRequest):
    """Login for teacher/operator demo users."""

    res, code, message, data = await demo_auth_service.login(**request.model_dump())
    return {"res": res, "code": code, "message": message, "data": data}

