"""Sira Exam Service — FastAPI application entry point."""

from __future__ import annotations

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.exam import router as exam_router
from app.api.v1.proctor import router as proctor_router
from app.core.config import settings
from app.core.database import create_schema

logger = structlog.get_logger(__name__)

app = FastAPI(
    title="Sira Exam Service",
    description="AI-generated proctored exams for university accreditation",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url, "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(exam_router, prefix="/api/v1")
app.include_router(proctor_router, prefix="/api/v1")


@app.on_event("startup")
async def startup() -> None:
    await create_schema()
    from app.infrastructure.exam_evidence import ensure_exam_evidence_bucket
    from app.infrastructure.storage import get_exam_storage

    await get_exam_storage().ensure_bucket()
    await ensure_exam_evidence_bucket()
    logger.info("sira_exam_service_started", frontend_url=settings.frontend_url)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
