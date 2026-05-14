"""Celery task: generate exam scenarios and questions via Claude AI."""

from __future__ import annotations

import asyncio
import uuid

import structlog

from app.tasks.celery_app import celery_app

logger = structlog.get_logger(__name__)

SAVE_EXAM_TOOL = {
    "name": "save_exam",
    "description": "Save the generated exam scenarios and questions to the database.",
    "input_schema": {
        "type": "object",
        "properties": {
            "scenarios": {
                "type": "array",
                "description": "Exam scenarios (case studies or reading passages).",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "objective": {"type": "string"},
                        "context_text": {"type": "string"},
                        "order_index": {"type": "integer", "minimum": 0},
                    },
                    "required": ["title", "objective", "context_text", "order_index"],
                },
            },
            "questions": {
                "type": "array",
                "description": "Questions distributed across scenarios.",
                "items": {
                    "type": "object",
                    "properties": {
                        "scenario_index": {
                            "type": "integer",
                            "description": "Index into scenarios[] (0-based).",
                        },
                        "question_type": {"type": "string", "enum": ["mcq", "dissertation"]},
                        "title": {"type": "string"},
                        "description": {"type": "string"},
                        "difficulty": {"type": "string", "enum": ["easy", "medium", "hard"]},
                        "order_index": {"type": "integer"},
                        "category": {"type": "string"},
                        "options": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "label": {"type": "string"},
                                    "text": {"type": "string"},
                                },
                            },
                        },
                        "correct_answer_indices": {
                            "type": "array",
                            "items": {"type": "integer"},
                        },
                        "explanation": {"type": "string"},
                        "model_answer": {"type": "string"},
                        "rubric": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "criterion": {"type": "string"},
                                    "max_points": {"type": "number"},
                                    "description": {"type": "string"},
                                },
                            },
                        },
                    },
                    "required": [
                        "scenario_index",
                        "question_type",
                        "description",
                        "difficulty",
                        "order_index",
                    ],
                },
            },
        },
        "required": ["scenarios", "questions"],
    },
}


@celery_app.task(name="generate_exam_task", bind=True, max_retries=2)
def generate_exam_task(
    self,  # type: ignore[no-untyped-def]
    bank_id: str,
    test_objective: str,
    scenarios_brief: list[dict],
) -> dict:
    return asyncio.run(_run_generation(bank_id, test_objective, scenarios_brief))


@celery_app.task(name="regenerate_scenario_task", bind=True, max_retries=2)
def regenerate_scenario_task(
    self,  # type: ignore[no-untyped-def]
    bank_id: str,
    scenario_id: str,
    test_objective: str,
) -> dict:
    return asyncio.run(_run_regeneration(bank_id, scenario_id, test_objective))


async def _run_generation(
    bank_id: str,
    test_objective: str,
    scenarios_brief: list[dict],
) -> dict:

    from sqlalchemy import select

    from app.core.config import settings
    from app.core.database import celery_db
    from app.domain.models.exam import (
        BankStatus,
        Difficulty,
        ExamBank,
        ExamQuestion,
        ExamScenario,
        ExamSource,
        QuestionType,
    )

    async with celery_db() as db:
        bank = await db.get(ExamBank, uuid.UUID(bank_id))
        if not bank:
            logger.error("generate_exam_bank_not_found", bank_id=bank_id)
            return {"status": "error", "detail": "Bank not found"}

        bank.status = BankStatus.generating
        await db.commit()

        try:
            # Collect source text from all done sources
            sources_result = await db.execute(
                select(ExamSource).where(ExamSource.bank_id == uuid.UUID(bank_id))
            )
            sources = sources_result.scalars().all()
            context = "\n\n---\n\n".join(s.raw_text for s in sources if s.raw_text)[:8000]

            exam_data = await _call_claude(
                settings.exam_anthropic_api_key,
                test_objective=test_objective,
                scenarios_brief=scenarios_brief,
                context=context,
            )

            # Persist scenarios + questions
            scenario_id_map: dict[int, uuid.UUID] = {}
            for idx, sc in enumerate(exam_data.get("scenarios", [])):
                scenario = ExamScenario(
                    bank_id=uuid.UUID(bank_id),
                    title=sc["title"],
                    objective=sc.get("objective"),
                    context_text=sc.get("context_text"),
                    order_index=sc.get("order_index", idx),
                )
                db.add(scenario)
                await db.flush()
                scenario_id_map[idx] = scenario.id

            for q_data in exam_data.get("questions", []):
                sc_idx = q_data.get("scenario_index", 0)
                question = ExamQuestion(
                    bank_id=uuid.UUID(bank_id),
                    scenario_id=scenario_id_map.get(sc_idx),
                    question_type=QuestionType(q_data["question_type"]),
                    title=q_data.get("title"),
                    description=q_data["description"],
                    difficulty=Difficulty(q_data.get("difficulty", "medium")),
                    order_index=q_data.get("order_index", 0),
                    category=q_data.get("category"),
                    options=q_data.get("options"),
                    correct_answer_indices=q_data.get("correct_answer_indices"),
                    explanation=q_data.get("explanation"),
                    model_answer=q_data.get("model_answer"),
                    rubric=q_data.get("rubric"),
                    ai_generated=True,
                    validated=False,
                )
                db.add(question)

            bank.status = BankStatus.review
            bank.generation_error = None
            await db.commit()

            logger.info(
                "exam_generated",
                bank_id=bank_id,
                scenarios=len(exam_data.get("scenarios", [])),
                questions=len(exam_data.get("questions", [])),
            )
            return {
                "status": "done",
                "bank_id": bank_id,
                "scenario_count": len(exam_data.get("scenarios", [])),
                "question_count": len(exam_data.get("questions", [])),
            }

        except Exception as exc:
            logger.error("exam_generation_failed", bank_id=bank_id, error=str(exc))
            bank.status = BankStatus.draft
            bank.generation_error = str(exc)[:500]
            await db.commit()
            raise


async def _run_regeneration(
    bank_id: str,
    scenario_id: str,
    test_objective: str,
) -> dict:

    from sqlalchemy import delete, select

    from app.core.config import settings
    from app.core.database import celery_db
    from app.domain.models.exam import (
        BankStatus,
        Difficulty,
        ExamBank,
        ExamQuestion,
        ExamScenario,
        ExamSource,
        QuestionType,
    )

    async with celery_db() as db:
        bank = await db.get(ExamBank, uuid.UUID(bank_id))
        scenario = await db.get(ExamScenario, uuid.UUID(scenario_id))
        if not bank or not scenario:
            return {"status": "error", "detail": "Bank or scenario not found"}

        bank.status = BankStatus.generating
        await db.commit()

        try:
            sources_result = await db.execute(
                select(ExamSource).where(ExamSource.bank_id == uuid.UUID(bank_id))
            )
            context = "\n\n---\n\n".join(
                s.raw_text for s in sources_result.scalars().all() if s.raw_text
            )[:8000]

            scenarios_brief = [{"title": scenario.title, "objective": scenario.objective or ""}]
            exam_data = await _call_claude(
                settings.exam_anthropic_api_key,
                test_objective=test_objective,
                scenarios_brief=scenarios_brief,
                context=context,
            )

            # Delete existing questions for this scenario only
            await db.execute(
                delete(ExamQuestion).where(ExamQuestion.scenario_id == uuid.UUID(scenario_id))
            )

            for q_data in exam_data.get("questions", []):
                question = ExamQuestion(
                    bank_id=uuid.UUID(bank_id),
                    scenario_id=uuid.UUID(scenario_id),
                    question_type=QuestionType(q_data["question_type"]),
                    title=q_data.get("title"),
                    description=q_data["description"],
                    difficulty=Difficulty(q_data.get("difficulty", "medium")),
                    order_index=q_data.get("order_index", 0),
                    options=q_data.get("options"),
                    correct_answer_indices=q_data.get("correct_answer_indices"),
                    explanation=q_data.get("explanation"),
                    model_answer=q_data.get("model_answer"),
                    rubric=q_data.get("rubric"),
                    ai_generated=True,
                    validated=False,
                )
                db.add(question)

            bank.status = BankStatus.review
            bank.generation_error = None
            await db.commit()
            return {"status": "done", "scenario_id": scenario_id}

        except Exception as exc:
            logger.error("regeneration_failed", scenario_id=scenario_id, error=str(exc))
            bank.status = BankStatus.draft
            bank.generation_error = str(exc)[:500]
            await db.commit()
            raise


async def _call_claude(
    api_key: str,
    *,
    test_objective: str,
    scenarios_brief: list[dict],
    context: str,
) -> dict:
    """Call Claude with forced save_exam tool use. Returns parsed tool input."""
    import json

    from anthropic import AsyncAnthropic

    client = AsyncAnthropic(api_key=api_key, timeout=300.0)

    user_msg = (
        f"Generate an exam with the following objective: {test_objective}\n\n"
        f"Scenarios requested:\n{json.dumps(scenarios_brief, indent=2)}\n\n"
        f"Source material:\n{context or '(no source material provided)'}"
    )

    response = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8000,
        tools=[SAVE_EXAM_TOOL],
        tool_choice={"type": "tool", "name": "save_exam"},
        messages=[{"role": "user", "content": user_msg}],
    )

    for block in response.content:
        if hasattr(block, "type") and block.type == "tool_use" and block.name == "save_exam":
            return block.input  # type: ignore[return-value]

    raise ValueError(f"Claude did not call save_exam; stop_reason={response.stop_reason}")
