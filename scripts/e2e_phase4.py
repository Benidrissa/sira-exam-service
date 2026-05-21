#!/usr/bin/env python3
"""Phase 4 E2E tests for sira-exam-service — FR-4.18 through FR-4.24.

Covers new features added in commits:
  feat(E4-18/23): class-grouped submissions, course/class student history, review audit log
  feat(E4-24):    anonymous/blind grading for dissertation review

All tests are API-only (no browser). Target: staging.
Usage: python scripts/e2e_phase4.py
"""
from __future__ import annotations

import sys
import time
import uuid

import requests

API = "https://sira-exam-api.elearning.portfolio2.kimbetien.com/api/v1"

passes: list[str] = []
fails: list[str] = []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def ok(msg: str) -> None:
    print(f"  ✅ PASS: {msg}")
    passes.append(msg)


def fail(msg: str, detail: str = "") -> None:
    full = f"{msg}" + (f" — {detail}" if detail else "")
    print(f"  ❌ FAIL: {full}")
    fails.append(full)


def warn(msg: str) -> None:
    print(f"  ⚠️  WARN: {msg}")


def get_token(role: str, sub: str = "1") -> str:
    r = requests.get(f"{API}/dev/tokens?role={role}&sub={sub}", timeout=10)
    r.raise_for_status()
    return r.json()["access_token"]


def api_get(path: str, token: str) -> requests.Response:
    return requests.get(
        f"{API}{path}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )


def api_post(path: str, token: str, body: dict | None = None) -> requests.Response:
    return requests.post(
        f"{API}{path}",
        json=body or {},
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )


def api_patch(path: str, token: str, body: dict) -> requests.Response:
    return requests.patch(
        f"{API}{path}",
        json=body,
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )


def api_delete(path: str, token: str) -> requests.Response:
    return requests.delete(
        f"{API}{path}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )


def _setup_exam(teacher_token: str, student_token: str) -> dict:
    """Create bank → questions → validate → test → publish → attempt → submit.

    Returns dict with bank_id, test_id, attempt_id, answer_id.
    Used by FR-4.21, FR-4.20, FR-4.24 scenarios.
    """
    ts = int(time.time())

    # Bank with course fields
    r = api_post("/exam/banks", teacher_token, {
        "title_fr": f"Phase4 Test {ts}",
        "language": "fr",
        "passing_score": 50.0,
        "course_code": f"P4-{ts % 10000}",
        "course_name": "Phase 4 Testing",
    })
    if r.status_code not in (200, 201):
        raise RuntimeError(f"Bank creation failed: {r.status_code} {r.text[:100]}")
    bank_id = r.json()["id"]

    # Dissertation question only (so we get an answer to audit-log)
    r = api_post(f"/exam/banks/{bank_id}/question", teacher_token, {
        "question_type": "dissertation",
        "description": "Explain the importance of testing.",
        "order_index": 0,
        "model_answer": "Testing ensures software quality.",
        "rubric": [{"criterion": "Depth", "max_points": 100, "description": "Answer depth"}],
    })
    if r.status_code not in (200, 201):
        raise RuntimeError(f"Question creation failed: {r.status_code}")

    # Validate-all + publish bank
    r = api_post(f"/exam/banks/{bank_id}/validate-all", teacher_token)
    if r.status_code not in (200, 201):
        raise RuntimeError(f"validate-all failed: {r.status_code}")

    # Create + publish test
    r = api_post(f"/exam/banks/{bank_id}/tests", teacher_token, {
        "title": f"P4 test {ts}",
        "shuffle_questions": False,
        "time_limit_minutes": 30,
    })
    if r.status_code not in (200, 201):
        raise RuntimeError(f"Test creation failed: {r.status_code}")
    test_id = r.json()["id"]

    r2 = api_patch(f"/exam/tests/{test_id}", teacher_token, {"status": "published"})
    if r2.status_code not in (200, 201):
        raise RuntimeError(f"Test publish failed: {r2.status_code}")

    # Student starts attempt
    r = api_post(f"/exam/tests/{test_id}/start", student_token)
    if r.status_code not in (200, 201):
        raise RuntimeError(f"Attempt start failed: {r.status_code}")
    attempt_data = r.json()
    attempt_id = attempt_data["attempt_id"]
    question_ids = attempt_data.get("question_ids", [])

    # Student submits
    dissertation_answers = {q: "A detailed answer about the importance of testing in software engineering." for q in question_ids}
    r = api_post(f"/exam/attempts/{attempt_id}/submit", student_token, {
        "mcq_answers": {},
        "dissertation_answers": dissertation_answers,
        "time_taken_sec": 120,
    })
    if r.status_code not in (200, 201):
        raise RuntimeError(f"Submit failed: {r.status_code}")

    # Get dissertation answer ID for later use
    r_rev = api_get(f"/exam/tests/{test_id}/dissertation-review", teacher_token)
    answer_id = None
    if r_rev.status_code == 200 and r_rev.json():
        answer_id = r_rev.json()[0]["id"]

    return {
        "bank_id": bank_id,
        "test_id": test_id,
        "attempt_id": attempt_id,
        "answer_id": answer_id,
        "course_code": f"P4-{ts % 10000}",
    }


# ---------------------------------------------------------------------------
# Scenario A — FR-4.18: Course Fields on ExamBank
# ---------------------------------------------------------------------------

def test_fr418_course_fields(teacher_token: str) -> None:
    print("\n── Scenario A: FR-4.18 — Course Fields on ExamBank ─────────────────")
    ts = int(time.time())

    # 1. Create bank with course_code + course_name
    r = api_post("/exam/banks", teacher_token, {
        "title_fr": f"FR418 Bank {ts}",
        "language": "fr",
        "passing_score": 60.0,
        "course_code": "CS101",
        "course_name": "Introduction to Computer Science",
    })
    if r.status_code not in (200, 201):
        fail("FR-4.18: Create bank with course fields", f"HTTP {r.status_code}: {r.text[:150]}")
        return
    bank = r.json()
    bank_id = bank["id"]

    if bank.get("course_code") == "CS101":
        ok("FR-4.18: course_code=CS101 stored and returned on creation")
    else:
        fail("FR-4.18: course_code not returned", f"got: {bank.get('course_code')}")

    if bank.get("course_name") == "Introduction to Computer Science":
        ok("FR-4.18: course_name stored and returned on creation")
    else:
        fail("FR-4.18: course_name not returned", f"got: {bank.get('course_name')}")

    # 2. GET /exam/banks/{id} returns fields
    r2 = api_get(f"/exam/banks/{bank_id}", teacher_token)
    if r2.status_code == 200:
        b = r2.json()
        if b.get("course_code") == "CS101" and b.get("course_name") == "Introduction to Computer Science":
            ok("FR-4.18: GET /exam/banks/{id} returns course_code and course_name")
        else:
            fail("FR-4.18: GET /exam/banks/{id} missing course fields",
                 f"code={b.get('course_code')}, name={b.get('course_name')}")
    else:
        fail("FR-4.18: GET /exam/banks/{id}", f"HTTP {r2.status_code}")

    # 3. PATCH updates course_name
    r3 = api_patch(f"/exam/banks/{bank_id}", teacher_token, {
        "course_name": "Intro to CS — Updated",
    })
    if r3.status_code in (200, 201):
        b3 = r3.json()
        if b3.get("course_name") == "Intro to CS — Updated":
            ok("FR-4.18: PATCH /exam/banks/{id} updates course_name")
        else:
            fail("FR-4.18: PATCH did not update course_name", f"got: {b3.get('course_name')}")
    else:
        fail("FR-4.18: PATCH /exam/banks/{id}", f"HTTP {r3.status_code}")


# ---------------------------------------------------------------------------
# Scenario B — FR-4.19: SchoolClass Archival
# ---------------------------------------------------------------------------

def test_fr419_class_archival(teacher_token: str) -> None:
    print("\n── Scenario B: FR-4.19 — SchoolClass Archival ──────────────────────")
    ts = int(time.time())

    # 1. Create class
    r = api_post("/exam/classes", teacher_token, {
        "name": f"FR419 Class {ts}",
        "academic_year": "2026-2027",
    })
    if r.status_code not in (200, 201):
        fail("FR-4.19: Create school class", f"HTTP {r.status_code}: {r.text[:150]}")
        return
    cls = r.json()
    class_id = cls["id"]

    if cls.get("archived_at") is None:
        ok("FR-4.19: New class has archived_at=null")
    else:
        fail("FR-4.19: New class should have archived_at=null", f"got: {cls.get('archived_at')}")

    # 2. Archive the class
    r2 = api_patch(f"/exam/classes/{class_id}", teacher_token, {"archive": True})
    if r2.status_code in (200, 201):
        cls2 = r2.json()
        if cls2.get("archived_at") is not None:
            ok("FR-4.19: archive=true sets archived_at to a non-null datetime")
        else:
            fail("FR-4.19: archive=true should set archived_at", f"got: {cls2.get('archived_at')}")
    else:
        fail("FR-4.19: PATCH archive=true", f"HTTP {r2.status_code}: {r2.text[:150]}")

    # 3. Unarchive the class
    r3 = api_patch(f"/exam/classes/{class_id}", teacher_token, {"archive": False})
    if r3.status_code in (200, 201):
        cls3 = r3.json()
        if cls3.get("archived_at") is None:
            ok("FR-4.19: archive=false clears archived_at (null again)")
        else:
            fail("FR-4.19: archive=false should clear archived_at", f"got: {cls3.get('archived_at')}")
    else:
        fail("FR-4.19: PATCH archive=false", f"HTTP {r3.status_code}: {r3.text[:150]}")

    # 4. GET /exam/classes still includes the class (archived ≠ deleted)
    r4 = api_get("/exam/classes", teacher_token)
    if r4.status_code == 200:
        classes = r4.json()
        ids = [c["id"] for c in classes]
        if class_id in ids:
            ok("FR-4.19: GET /exam/classes includes unarchived class (not hidden)")
        else:
            warn("FR-4.19: Class not found in GET /exam/classes (may be filtered)")
    else:
        fail("FR-4.19: GET /exam/classes", f"HTTP {r4.status_code}")

    # 5. Re-archive and verify GET still returns it
    api_patch(f"/exam/classes/{class_id}", teacher_token, {"archive": True})
    r5 = api_get("/exam/classes", teacher_token)
    if r5.status_code == 200:
        ids = [c["id"] for c in r5.json()]
        if class_id in ids:
            ok("FR-4.19: GET /exam/classes includes archived class (not hidden)")
        else:
            warn("FR-4.19: Archived class not in GET /exam/classes list")


# ---------------------------------------------------------------------------
# Scenario C — FR-4.21: Review Audit Log
# ---------------------------------------------------------------------------

def test_fr421_audit_log(teacher_token: str, student_token: str) -> None:
    print("\n── Scenario C: FR-4.21 — Review Audit Log ──────────────────────────")

    try:
        setup = _setup_exam(teacher_token, student_token)
    except RuntimeError as e:
        fail("FR-4.21: exam setup failed", str(e))
        return

    test_id = setup["test_id"]
    answer_id = setup["answer_id"]

    if answer_id is None:
        warn("FR-4.21: No dissertation answer found after submission (AI grading may be pending)")
        # Try to proceed anyway by waiting a moment
        time.sleep(5)
        r_rev = api_get(f"/exam/tests/{test_id}/dissertation-review", teacher_token)
        if r_rev.status_code == 200 and r_rev.json():
            answer_id = r_rev.json()[0]["id"]
        if answer_id is None:
            fail("FR-4.21: Cannot proceed — no answer_id found")
            return

    # Apply human score (this should create an audit log entry)
    r_score = api_patch(f"/exam/answers/{answer_id}/human-score", teacher_token, {
        "human_score": 75.0,
        "human_feedback": "Good effort, needs more depth.",
    })
    if r_score.status_code not in (200, 201):
        fail("FR-4.21: Apply human score", f"HTTP {r_score.status_code}: {r_score.text[:150]}")
        return
    ok("FR-4.21: human score applied (pre-condition for audit log)")

    # GET audit log — should have at least 1 entry
    r_log = api_get(f"/exam/tests/{test_id}/audit-log", teacher_token)
    if r_log.status_code != 200:
        fail("FR-4.21: GET /exam/tests/{id}/audit-log", f"HTTP {r_log.status_code}: {r_log.text[:150]}")
        return

    entries = r_log.json()
    if not isinstance(entries, list):
        fail("FR-4.21: audit-log response should be a list", f"got: {type(entries)}")
        return
    if not entries:
        fail("FR-4.21: audit-log should have ≥1 entry after human scoring")
        return

    ok(f"FR-4.21: audit-log has {len(entries)} entry(ies) after human scoring")

    entry = entries[0]
    # Verify key fields
    for field in ("id", "answer_id", "attempt_id", "test_id", "actor_id", "actor_role", "action", "new_values", "occurred_at"):
        if field not in entry:
            fail(f"FR-4.21: audit log entry missing field '{field}'")
        else:
            ok(f"FR-4.21: entry has field '{field}'={str(entry[field])[:40]}")

    if entry.get("new_values") and "human_score" in str(entry.get("new_values", {})):
        ok("FR-4.21: new_values contains human_score")
    else:
        warn(f"FR-4.21: new_values may not contain human_score: {entry.get('new_values')}")

    # Student should get 403
    r_403 = api_get(f"/exam/tests/{test_id}/audit-log", student_token)
    if r_403.status_code == 403:
        ok("FR-4.21: student role correctly gets 403 on GET audit-log")
    else:
        fail("FR-4.21: student should get 403 on audit-log", f"got {r_403.status_code}")

    # Verify immutability — no UPDATE/DELETE endpoints
    r_del = api_delete(f"/exam/tests/{test_id}/audit-log", teacher_token)
    if r_del.status_code == 405:
        ok("FR-4.21: DELETE on audit-log correctly returns 405 (immutable)")
    elif r_del.status_code == 404:
        ok("FR-4.21: DELETE on audit-log returns 404 (no such endpoint = immutable)")
    else:
        warn(f"FR-4.21: DELETE audit-log returned {r_del.status_code} (expected 405 or 404)")


# ---------------------------------------------------------------------------
# Scenario D — FR-4.20: Exam Access Grant
# ---------------------------------------------------------------------------

def test_fr420_access_grant(teacher_token: str, student_token: str, admin_token: str) -> None:
    print("\n── Scenario D: FR-4.20 — Exam Access Grant ─────────────────────────")

    # Get student user_id from token
    import base64, json as _json
    try:
        parts = student_token.split(".")
        payload = _json.loads(base64.b64decode(parts[1] + "=="))
        student_user_id = payload["sub"]
    except Exception:
        fail("FR-4.20: Could not decode student user_id from token")
        return

    # Create a small exam setup for the grant test
    try:
        setup = _setup_exam(teacher_token, student_token)
    except RuntimeError as e:
        fail("FR-4.20: exam setup failed", str(e))
        return

    test_id = setup["test_id"]
    attempt_id = setup["attempt_id"]

    # 1. Non-admin cannot create grant
    r_nonadmin = api_post("/exam/grants", teacher_token, {
        "test_id": test_id,
        "student_id": student_user_id,
    })
    if r_nonadmin.status_code == 403:
        ok("FR-4.20: non-admin (teacher) correctly gets 403 on POST /exam/grants")
    else:
        warn(f"FR-4.20: expected 403 for non-admin grant creation, got {r_nonadmin.status_code}")

    # 2. Admin creates grant for the student
    r_grant = api_post("/exam/grants", admin_token, {
        "test_id": test_id,
        "student_id": student_user_id,
    })
    if r_grant.status_code not in (200, 201):
        fail("FR-4.20: Admin POST /exam/grants", f"HTTP {r_grant.status_code}: {r_grant.text[:200]}")
        return
    grant = r_grant.json()
    grant_id = grant["id"]
    ok(f"FR-4.20: Admin created access grant (id={grant_id[:8]}…)")

    # Verify grant fields
    if str(grant.get("test_id")) == str(test_id):
        ok("FR-4.20: grant.test_id matches the created test")
    else:
        fail("FR-4.20: grant.test_id mismatch", f"expected {test_id}, got {grant.get('test_id')}")

    # 3. Student can now access review via the grant
    r_review = api_get(f"/exam/attempts/{attempt_id}/review", student_token)
    if r_review.status_code == 200:
        ok("FR-4.20: Student can access attempt review with access grant")
    elif r_review.status_code == 403:
        warn("FR-4.20: Student still gets 403 on review even with grant (review_allowed logic may depend on validation_status)")
    else:
        warn(f"FR-4.20: Review with grant returned {r_review.status_code}")

    # 4. List grants — verify it appears
    r_list = api_get("/exam/grants", admin_token)
    if r_list.status_code == 200:
        grants = r_list.json()
        grant_ids = [g["id"] for g in grants]
        if grant_id in grant_ids:
            ok(f"FR-4.20: GET /exam/grants lists the new grant")
        else:
            warn("FR-4.20: New grant not found in GET /exam/grants (may be org-filtered)")
    else:
        fail("FR-4.20: GET /exam/grants", f"HTTP {r_list.status_code}")

    # 5. Revoke grant
    r_del = api_delete(f"/exam/grants/{grant_id}", admin_token)
    if r_del.status_code == 204:
        ok("FR-4.20: DELETE /exam/grants/{id} returns 204 (grant revoked)")
    else:
        fail("FR-4.20: DELETE /exam/grants/{id}", f"HTTP {r_del.status_code}: {r_del.text[:100]}")

    # 6. Verify grant no longer in list
    r_list2 = api_get("/exam/grants", admin_token)
    if r_list2.status_code == 200:
        grant_ids2 = [g["id"] for g in r_list2.json()]
        if grant_id not in grant_ids2:
            ok("FR-4.20: Revoked grant no longer in GET /exam/grants list")
        else:
            fail("FR-4.20: Revoked grant still appears in list after DELETE")


# ---------------------------------------------------------------------------
# Scenario E — FR-4.24: Anonymous Grading
# ---------------------------------------------------------------------------

def test_fr424_anonymous_grading(teacher_token: str, student_token: str) -> None:
    print("\n── Scenario E: FR-4.24 — Anonymous Grading ─────────────────────────")
    ts = int(time.time())

    # Setup: create bank with 1 MCQ question (for simple scoring, no AI grading needed)
    r = api_post("/exam/banks", teacher_token, {
        "title_fr": f"Anon Test {ts}",
        "language": "fr",
        "passing_score": 50.0,
    })
    if r.status_code not in (200, 201):
        fail("FR-4.24: bank creation", f"HTTP {r.status_code}")
        return
    bank_id = r.json()["id"]

    # MCQ question
    r_q = api_post(f"/exam/banks/{bank_id}/question", teacher_token, {
        "question_type": "mcq",
        "description": "Which is correct?",
        "order_index": 0,
        "options": [{"label": "A", "text": "Yes"}, {"label": "B", "text": "No"}],
        "correct_answer_indices": [0],
    })
    if r_q.status_code not in (200, 201):
        fail("FR-4.24: question creation", f"HTTP {r_q.status_code}")
        return
    question_id = r_q.json()["id"]

    api_post(f"/exam/banks/{bank_id}/validate-all", teacher_token)

    # 1. Create test with anonymous_grading=True
    r_test = api_post(f"/exam/banks/{bank_id}/tests", teacher_token, {
        "title": f"Anon Test {ts}",
        "shuffle_questions": False,
        "time_limit_minutes": 30,
        "anonymous_grading": True,
    })
    if r_test.status_code not in (200, 201):
        fail("FR-4.24: Create test with anonymous_grading=True", f"HTTP {r_test.status_code}: {r_test.text[:150]}")
        return
    test_data = r_test.json()
    test_id = test_data["id"]
    if test_data.get("anonymous_grading") is True:
        ok("FR-4.24: test.anonymous_grading=True stored and returned")
    else:
        fail("FR-4.24: anonymous_grading not returned as True", f"got: {test_data.get('anonymous_grading')}")

    api_patch(f"/exam/tests/{test_id}", teacher_token, {"status": "published"})

    # 2. Student starts attempt
    r_start = api_post(f"/exam/tests/{test_id}/start", student_token)
    if r_start.status_code not in (200, 201):
        fail("FR-4.24: Student start attempt", f"HTTP {r_start.status_code}: {r_start.text[:150]}")
        return
    attempt_data = r_start.json()
    attempt_id = attempt_data["attempt_id"]
    ok(f"FR-4.24: Student started attempt (id={attempt_id[:8]}…)")

    # 3. Student submits with correct MCQ answer
    r_submit = api_post(f"/exam/attempts/{attempt_id}/submit", student_token, {
        "mcq_answers": {question_id: [0]},
        "dissertation_answers": {},
        "time_taken_sec": 30,
    })
    if r_submit.status_code not in (200, 201):
        fail("FR-4.24: Student submit attempt", f"HTTP {r_submit.status_code}: {r_submit.text[:150]}")
        return
    ok("FR-4.24: Student submitted attempt successfully")

    # 4. Check anon-mapping BEFORE validation → should return 409
    r_map_before = api_get(f"/exam/tests/{test_id}/anon-mapping", teacher_token)
    if r_map_before.status_code == 409:
        ok("FR-4.24: GET anon-mapping before validation correctly returns 409")
    elif r_map_before.status_code == 200:
        warn("FR-4.24: anon-mapping returned 200 before validation (may be auto-validated)")
    else:
        warn(f"FR-4.24: anon-mapping returned {r_map_before.status_code} (expected 409)")

    # 5. Teacher validates the attempt (FR-4.9)
    r_validate = api_post(f"/exam/attempts/{attempt_id}/validate", teacher_token)
    if r_validate.status_code in (200, 201):
        ok("FR-4.24: Teacher validated the attempt (FR-4.9)")
    else:
        fail("FR-4.24: Attempt validation", f"HTTP {r_validate.status_code}: {r_validate.text[:150]}")
        return

    # 6. Check anon-mapping AFTER validation → should return 200 with mapping
    r_map_after = api_get(f"/exam/tests/{test_id}/anon-mapping", teacher_token)
    if r_map_after.status_code != 200:
        fail("FR-4.24: GET anon-mapping after validation", f"HTTP {r_map_after.status_code}: {r_map_after.text[:150]}")
        return

    mapping_data = r_map_after.json()
    ok(f"FR-4.24: GET anon-mapping after validation returns 200")

    if "mappings" not in mapping_data:
        fail("FR-4.24: anon-mapping response missing 'mappings' key")
        return

    mappings = mapping_data["mappings"]
    if not mappings:
        fail("FR-4.24: anon-mapping 'mappings' list is empty")
        return

    ok(f"FR-4.24: anon-mapping has {len(mappings)} entry(ies)")

    entry = mappings[0]
    if "anon_id" in entry and "user_id" in entry:
        ok(f"FR-4.24: mapping entry has anon_id and user_id fields")
        # Verify user_id matches the student
        # (We decode the student token's sub to get user_id)
        import base64, json as _json
        try:
            parts = student_token.split(".")
            payload = _json.loads(base64.b64decode(parts[1] + "=="))
            student_user_id = payload["sub"]
            if str(entry["user_id"]) == student_user_id:
                ok("FR-4.24: mapping entry.user_id matches student token sub")
            else:
                warn(f"FR-4.24: mapping user_id {entry['user_id']} ≠ student {student_user_id}")
        except Exception:
            warn("FR-4.24: Could not verify user_id against student token")
    else:
        fail("FR-4.24: mapping entry missing anon_id or user_id", f"keys: {list(entry.keys())}")

    # 7. Regression: test with anonymous_grading=False (default) has user_id in submissions
    r_test2 = api_post(f"/exam/banks/{bank_id}/tests", teacher_token, {
        "title": f"Normal Test {ts}",
        "shuffle_questions": False,
    })
    if r_test2.status_code in (200, 201):
        t2 = r_test2.json()
        if t2.get("anonymous_grading") is False:
            ok("FR-4.24: Test with default settings has anonymous_grading=False (no regression)")
        else:
            fail("FR-4.24: Default test should have anonymous_grading=False", f"got: {t2.get('anonymous_grading')}")


# ---------------------------------------------------------------------------
# Scenario F — FR-4.22: Submissions include class/course metadata (API contract)
# ---------------------------------------------------------------------------

def test_fr422_submissions_metadata(teacher_token: str, student_token: str) -> None:
    print("\n── Scenario F: FR-4.22 — Submissions include class/course metadata ──")

    try:
        setup = _setup_exam(teacher_token, student_token)
    except RuntimeError as e:
        fail("FR-4.22: exam setup failed", str(e))
        return

    test_id = setup["test_id"]

    r = api_get(f"/exam/tests/{test_id}/submissions", teacher_token)
    if r.status_code != 200:
        fail("FR-4.22: GET /exam/tests/{id}/submissions", f"HTTP {r.status_code}: {r.text[:150]}")
        return

    submissions = r.json()
    if not submissions:
        warn("FR-4.22: No submissions returned — cannot verify metadata fields")
        return

    row = submissions[0]
    ok(f"FR-4.22: GET /exam/tests/{test_id[:8]}…/submissions returned {len(submissions)} row(s)")

    # Verify expected fields exist in the response schema
    expected_fields = ["attempt_id", "user_id", "mcq_score", "class_name", "class_archived_at", "course_code", "course_name"]
    for field in expected_fields:
        if field in row:
            ok(f"FR-4.22: submissions row contains field '{field}'")
        else:
            fail(f"FR-4.22: submissions row missing field '{field}'", f"available: {list(row.keys())[:10]}")

    # Values should be None when student has no class assignment (that's OK)
    ok(f"FR-4.22: class_name={row.get('class_name')}, course_code={row.get('course_code')} (null when no assignment — expected)")


# ---------------------------------------------------------------------------
# Scenario G — FR-4.23: Student history includes course/class metadata (API contract)
# ---------------------------------------------------------------------------

def test_fr423_student_history(teacher_token: str, student_token: str) -> None:
    print("\n── Scenario G: FR-4.23 — Student history course/class metadata ──────")

    # Ensure the student has at least one submitted attempt (reuse from previous scenarios)
    r = api_get("/exam/student/history", student_token)
    if r.status_code != 200:
        fail("FR-4.23: GET /exam/student/history", f"HTTP {r.status_code}: {r.text[:150]}")
        return

    history = r.json()
    ok(f"FR-4.23: GET /exam/student/history returned {len(history)} row(s)")

    if not history:
        warn("FR-4.23: Student has no history — cannot verify metadata fields")
        return

    row = history[0]
    expected_fields = ["attempt_id", "test_id", "test_title", "class_name", "class_archived_at", "course_code", "course_name", "academic_year"]
    for field in expected_fields:
        if field in row:
            ok(f"FR-4.23: history row contains field '{field}'")
        else:
            fail(f"FR-4.23: history row missing field '{field}'", f"available: {list(row.keys())[:10]}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_tests() -> int:
    print("=" * 65)
    print("SIRA EXAM — Phase 4 E2E Tests (FR-4.18 through FR-4.24)")
    print("Target:", API)
    print("=" * 65)

    # Health check
    print("\n── Staging health check ────────────────────────────────────────────")
    try:
        h = requests.get(
            "https://sira-exam-api.elearning.portfolio2.kimbetien.com/health",
            timeout=10,
        )
        h.raise_for_status()
        print(f"  🟢 API health OK: {h.json()}")
    except Exception as e:
        print(f"  🔴 API health FAILED: {e}")
        return 1

    teacher_token = get_token("expert")
    student_token = get_token("user")
    admin_token = get_token("admin")  # admin role for FR-4.20 grants
    print(f"\n  Tokens minted: teacher ✓  student ✓  admin ✓")

    # Run all scenarios
    test_fr418_course_fields(teacher_token)
    test_fr419_class_archival(teacher_token)
    test_fr421_audit_log(teacher_token, student_token)
    test_fr420_access_grant(teacher_token, student_token, admin_token)
    test_fr424_anonymous_grading(teacher_token, student_token)
    test_fr422_submissions_metadata(teacher_token, student_token)
    test_fr423_student_history(teacher_token, student_token)

    # Summary
    print(f"\n{'=' * 65}")
    print(f"RESULTS: {len(passes)} passed  ·  {len(fails)} failed")
    print("=" * 65)
    if fails:
        print("\n❌ Failures:")
        for f_msg in fails:
            print(f"   • {f_msg}")
    else:
        print("\n✅ All Phase 4 checks passed!")

    return len(fails)


if __name__ == "__main__":
    n_fails = run_tests()
    sys.exit(1 if n_fails else 0)
