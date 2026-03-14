"""Auth dependencies for the digital human demo APIs."""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import select

from app.auth.jwt_manager import UserClaims, jwt_manager, security
from app.storage import AsyncSessionLocal, UserModel


async def get_current_demo_claims(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> UserClaims:
    """Validate bearer token for demo routes without requiring Redis session state."""

    token = credentials.credentials
    return await jwt_manager.verify_token(token, check_redis=False)


async def get_current_demo_user(
    claims: UserClaims = Depends(get_current_demo_claims),
) -> UserModel:
    """Load the current demo user from database."""

    async with AsyncSessionLocal() as session:
        stmt = select(UserModel).where(UserModel.id == int(claims.user_id))
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()

        if user is None or not user.is_active or user.is_deleted:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Current user is invalid or disabled",
            )

        return user

