"""FastAPI dependency functions for auth and DB session."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthenticatedUser, verify_sira_token
from app.core.database import get_db


def _extract_token(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    # Also accept cookie (for frontend SSR)
    token = request.cookies.get("access_token", "")
    if token:
        return token
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(request: Request) -> AuthenticatedUser:
    token = _extract_token(request)
    return verify_sira_token(token)


def require_teacher(
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> AuthenticatedUser:
    if not user.is_teacher:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Teacher role required")
    return user


def require_admin(
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> AuthenticatedUser:
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")
    return user


def require_student(
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> AuthenticatedUser:
    if user.role != "user":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Student role required")
    return user


CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]
TeacherUser = Annotated[AuthenticatedUser, Depends(require_teacher)]
AdminUser = Annotated[AuthenticatedUser, Depends(require_admin)]
StudentUser = Annotated[AuthenticatedUser, Depends(require_student)]
DB = Annotated[AsyncSession, Depends(get_db)]
