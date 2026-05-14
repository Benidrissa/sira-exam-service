"""Exam API — generation, review, CRUD, taking. (stub — E1-1 through E1-9 fill this out)"""
from fastapi import APIRouter

router = APIRouter(prefix="/exam", tags=["exam"])


@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "sira-exam"}
