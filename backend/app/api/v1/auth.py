"""Real password authentication endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import DB
from app.domain.services import auth_service
from app.schemas.auth import LoginRequest, LoginResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login(data: LoginRequest, db: DB) -> LoginResponse:
    """Authenticate with email + password and return an access token."""
    result = await auth_service.login(db, email=str(data.email), password=data.password)
    return LoginResponse(**result)
