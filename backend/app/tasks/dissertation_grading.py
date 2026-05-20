"""Celery task: grade dissertation answers via Claude AI (FR-1.8)."""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime

import structlog

from app.tasks.celery_app import celery_app

logger = structlog.get_logger(__name__)

GRADE_DISSERTATION_TOOL = {
    "name": "grade_dissertation",
    "description": "Submit grading results for a student's dissertation answer.",
    "input_schema": {
        "type": "object",
        "properties": {
            "overall_score": {
                "type": "number",
                "minimum": 0,
                "maximum": 100,
                "description": "Overall percentage score (0–100).",
            },
            "criterion_scores": {
                "type": "object",
                "additionalProperties": {"type": "number"},
                "description": "Map of criterion name → points earned.",
            },
            "feedback": {
                "type": "string",
                "description": "Constructive feedback for the student.",
            },
        },
        "required": ["overall_score", "criterion_scores", "feedback"],
    },
}

_GRADING_PROMPT = """\
You are an expert educator grading a student's essay answer.

QUESTION:
{question_description}

MODEL ANSWER (reference):
{model_answer}

GRADING RUBRIC:
{rubric_json}

STUDENT ANSWER:
{student_answer}

---

Evaluate the student's answer strictly against the rubric.
Use the grade_dissertation tool to submit your assessment."""


@celery_app.task(name="ai_correct_dissertation_task", bind=True, max_retries=2)
def ai_correct_dissertation_task(
    self,  # type: ignore[no-untyped-def]
    answer_id: str,
) -> dict:
    return asyncio.run(_grade(answer_id))


async def _grade(answer_id: str) -> dict:
    from anthropic import AsyncAnthropic

    from app.core.config import settings
    from app.core.database import AsyncSessionLocal
    from app.domain.models.exam import (
        DissertationAnswer,
        DissertationStatus,
        ExamQuestion,
    )

    async with AsyncSessionLocal() as db:
        answer = await db.get(DissertationAnswer, uuid.UUID(answer_id))
        if not answer:
            logger.error("dissertation_answer_not_found", answer_id=answer_id)
            return {"status": "error", "detail": "Answer not found"}

        question = await db.get(ExamQuestion, answer.question_id)
        if not question:
            logger.error("question_not_found", answer_id=answer_id)
            return {"status": "error", "detail": "Question not found"}

        try:
            rubric_json = (
                json.dumps(question.rubric, ensure_ascii=False) if question.rubric else "[]"
            )
            prompt = _GRADING_PROMPT.format(
                question_description=question.description,
                model_answer=question.model_answer or "(no model answer provided)",
                rubric_json=rubric_json,
                student_answer=answer.answer_text or "",
            )

            client = AsyncAnthropic(api_key=settings.exam_anthropic_api_key, timeout=180.0)
            response = await client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=2000,
                tools=[GRADE_DISSERTATION_TOOL],
                tool_choice={"type": "tool", "name": "grade_dissertation"},
                messages=[{"role": "user", "content": prompt}],
            )

            grade = None
            for block in response.content:
                if (
                    hasattr(block, "type")
                    and block.type == "tool_use"
                    and block.name == "grade_dissertation"
                ):
                    grade = block.input
                    break

            if grade is None:
                raise ValueError(
                    f"Claude did not call grade_dissertation; stop_reason={response.stop_reason}"
                )

            answer.ai_score = float(grade["overall_score"])
            answer.criterion_scores = grade["criterion_scores"]
            answer.ai_feedback = grade["feedback"]
            answer.ai_scored_at = datetime.now(tz=UTC)
            answer.status = DissertationStatus.ai_scored
            await db.commit()

            logger.info(
                "dissertation_graded",
                answer_id=answer_id,
                score=answer.ai_score,
            )
            return {"status": "done", "answer_id": answer_id, "score": answer.ai_score}

        except Exception as exc:
            logger.error("dissertation_grading_failed", answer_id=answer_id, error=str(exc))
            raise
