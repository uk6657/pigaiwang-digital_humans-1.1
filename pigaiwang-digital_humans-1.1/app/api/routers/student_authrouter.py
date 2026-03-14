"""Student auth router."""

from fastapi import APIRouter

from app.api.form_response import BaseResponseModel
from app.api.form_response.student_response import StudentLoginResponseModel
from app.api.form_validation.student_validation import StudentLoginRequest
from app.services.student_service import student_service

router = APIRouter(tags=["student-auth"])


@router.post(
    "/login",
    response_model=BaseResponseModel[StudentLoginResponseModel],
    summary="Student login",
)
async def login(request: StudentLoginRequest):
    """Login for a student account."""

    res, code, message, data = await student_service.login(**request.model_dump())
    return {"res": res, "code": code, "message": message, "data": data}
