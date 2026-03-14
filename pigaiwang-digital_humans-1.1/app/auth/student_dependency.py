"""Auth dependencies for student APIs."""

from fastapi import Depends, HTTPException, status
from sqlalchemy import select

from app.auth.demo_dependency import get_current_demo_claims
from app.storage import AsyncSessionLocal, StudentModel


async def get_current_student(claims=Depends(get_current_demo_claims)) -> StudentModel:
    """Load the current student from database."""

    user_id = claims.user_id
    if not user_id.startswith("student:"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Student token required",
        )

    student_id = int(user_id.split(":", 1)[1])
    async with AsyncSessionLocal() as session:
        stmt = select(StudentModel).where(StudentModel.student_id == student_id)
        student = (await session.execute(stmt)).scalar_one_or_none()
        if student is None or not student.is_active or student.is_deleted:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Current student is invalid",
            )
        return student
