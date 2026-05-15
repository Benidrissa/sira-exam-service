#!/usr/bin/env python3
"""Create a DAMA DMBOK demo exam on staging for UAT validation.

Usage:
    python scripts/create_demo_exam.py

Requires:
    pip install requests
    Staging API must be running with DEBUG=true (dev token endpoint enabled).
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import requests

STAGING_API = "https://sira-exam-api.elearning.portfolio2.kimbetien.com/api/v1"
PDF_PATH = Path(__file__).parent.parent / "docs" / "DAMA DMBOK 2nd Edition.pdf"

GENERATION_BRIEF = {
    "test_objective": (
        "Assess understanding of core data management disciplines "
        "as defined in DAMA DMBOK v2 — governance, quality, architecture, "
        "master data, and analytics."
    ),
    "scenarios_brief": [
        {"title": "Data Governance & Stewardship", "question_count": 3},
        {"title": "Data Quality Management", "question_count": 3},
        {"title": "Data Architecture & Modeling", "question_count": 3},
        {"title": "Master & Reference Data Management", "question_count": 2},
        {"title": "Data Warehousing & Business Intelligence", "question_count": 2},
    ],
}


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def step(msg: str) -> None:
    print(f"\n{'='*60}\n▶  {msg}")


def ok(msg: str) -> None:
    print(f"   ✅  {msg}")


def poll(
    token: str,
    url: str,
    done_condition: str,
    interval: int = 5,
    timeout: int = 180,
) -> dict:
    """Poll url until done_condition field equals 'done' or status matches."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = requests.get(url, headers=_headers(token), timeout=30)
        r.raise_for_status()
        data = r.json()
        state = data.get("status") or data.get("extraction_status") or ""
        print(f"   … status={state}", end="\r", flush=True)
        if state in (done_condition, "done", "review", "published"):
            print()
            return data
        if state in ("failed", "error"):
            print()
            raise RuntimeError(f"Step failed: {data}")
        time.sleep(interval)
    raise TimeoutError(f"Timed out waiting for {done_condition} at {url}")


def main() -> None:
    if not PDF_PATH.exists():
        sys.exit(f"❌  PDF not found: {PDF_PATH}")

    # ── 1. Get teacher token ───────────────────────────────────────────────
    step("1/8  Getting teacher token")
    r = requests.get(f"{STAGING_API}/dev/tokens?role=expert", timeout=15)
    if r.status_code != 200:
        sys.exit(
            f"❌  Dev token endpoint returned {r.status_code}.\n"
            "    Make sure the backend is deployed with DEBUG=true."
        )
    teacher_token = r.json()["access_token"]
    ok("teacher_token obtained (role=expert)")

    # ── 2. Get student token ───────────────────────────────────────────────
    r = requests.get(f"{STAGING_API}/dev/tokens?role=user", timeout=15)
    r.raise_for_status()
    student_token = r.json()["access_token"]
    ok("student_token obtained (role=user)")

    # ── 3. Create exam bank ────────────────────────────────────────────────
    step("2/8  Creating exam bank")
    r = requests.post(
        f"{STAGING_API}/exam/banks",
        json={
            "title_fr": "DAMA DMBOK v2 — Examen de Gestion des Données",
            "title_en": "DAMA DMBOK v2 — Data Management Exam",
            "subject": "Data Management",
            "language": "fr",
        },
        headers=_headers(teacher_token),
        timeout=30,
    )
    r.raise_for_status()
    bank = r.json()
    bank_id = bank["id"]
    ok(f"bank_id = {bank_id}")

    # ── 4. Upload PDF source ───────────────────────────────────────────────
    step(f"3/8  Uploading PDF ({PDF_PATH.stat().st_size // 1024 // 1024} MB)")
    with PDF_PATH.open("rb") as f:
        r = requests.post(
            f"{STAGING_API}/exam/banks/{bank_id}/sources",
            files={"file": (PDF_PATH.name, f, "application/pdf")},
            headers=_headers(teacher_token),
            timeout=120,
        )
    r.raise_for_status()
    source = r.json()
    source_id = source["id"]
    ok(f"source_id = {source_id}  status={source['extraction_status']}")

    # ── 5. Poll extraction ─────────────────────────────────────────────────
    step("4/8  Waiting for PDF extraction (up to 2 min)")
    poll(
        teacher_token,
        f"{STAGING_API}/exam/banks/{bank_id}/sources/{source_id}",
        done_condition="done",
        interval=5,
        timeout=120,
    )
    ok("extraction complete")

    # ── 6. Trigger generation ──────────────────────────────────────────────
    step("5/8  Triggering AI question generation")
    r = requests.post(
        f"{STAGING_API}/exam/banks/{bank_id}/generate",
        json=GENERATION_BRIEF,
        headers=_headers(teacher_token),
        timeout=30,
    )
    r.raise_for_status()
    ok(f"generation task enqueued  task_id={r.json().get('task_id')}")

    # ── 7. Poll generation ─────────────────────────────────────────────────
    step("6/8  Waiting for AI generation (up to 5 min)")
    poll(
        teacher_token,
        f"{STAGING_API}/exam/banks/{bank_id}/generation/status",
        done_condition="review",
        interval=10,
        timeout=300,
    )
    ok("bank status = review — questions ready")

    # ── 8. Validate-all (publishes bank) ───────────────────────────────────
    step("7/8  Validating all questions and publishing bank")
    r = requests.post(
        f"{STAGING_API}/exam/banks/{bank_id}/validate-all",
        headers=_headers(teacher_token),
        timeout=30,
    )
    r.raise_for_status()
    result = r.json()
    count = result.get("validated_count")
    bstatus = result.get("bank_status")
    ok(f"validated {count} questions  bank_status={bstatus}")

    # ── 9. Create ExamTest ─────────────────────────────────────────────────
    step("8/8  Creating ExamTest (30 min timer, shuffle on)")
    r = requests.post(
        f"{STAGING_API}/exam/banks/{bank_id}/tests",
        json={
            "title": "DAMA DMBOK Demo Test — UAT",
            "time_limit_minutes": 30,
            "shuffle_questions": True,
            "show_feedback": False,
        },
        headers=_headers(teacher_token),
        timeout=30,
    )
    r.raise_for_status()
    test = r.json()
    test_id = test["id"]
    # Tests are auto-published from published banks (status should already be published)
    # Belt-and-suspenders: PATCH to ensure published
    requests.patch(
        f"{STAGING_API}/exam/tests/{test_id}",
        json={"status": "published"},
        headers=_headers(teacher_token),
        timeout=10,
    )
    ok(f"test_id = {test_id}  status=published")

    # ── Summary ────────────────────────────────────────────────────────────
    frontend = "https://sira-exam.elearning.portfolio2.kimbetien.com"
    print(f"""
{'='*60}
✅  DEMO EXAM CREATED SUCCESSFULLY
{'='*60}

Bank ID  : {bank_id}
Test ID  : {test_id}

Teacher token (copy to browser cookie 'access_token'):
  {teacher_token}

Student token (copy to browser cookie 'access_token'):
  {student_token}

Browser UAT links:
  Login page  : {frontend}/login
  Exam player : {frontend}/exams/{test_id}/play
  Review board: {frontend}/banks/{bank_id}/review
  Grading     : {frontend}/exams/{bank_id}/results

API smoke test:
  curl -H "Authorization: Bearer <teacher_token>" \\
    {STAGING_API}/exam/banks/{bank_id}
{'='*60}
""")


if __name__ == "__main__":
    main()
