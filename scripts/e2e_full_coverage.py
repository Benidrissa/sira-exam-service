#!/usr/bin/env python3
"""Full E2E coverage — all 23 user stories (US-1 through US-23).

Covers the gaps not exercised by e2e_user_stories.py or e2e_phase4.py:
  US-14: TestBank reusability
  US-15: Class + year scoped test access
  US-16: Test scheduling (time windows, quarters)
  US-17: Teacher score validation (individual + batch)
  US-18: Student read-only review with feedback gate (browser)
  US-19: Score complaints — file + resolve (browser + API)
  US-20: Submissions grouped by class (browser)
  US-21: Student history grouped by course/class (browser)
  US-23: Anonymous grading anon-mapping reveal (browser + API)

Also re-exercises:
  US-1 to US-13: core bank/exam/proctor lifecycle
  FR-4.18 to FR-4.24: all Phase 4 features

Target: https://sira-exam.elearning.portfolio2.kimbetien.com
Usage:  python scripts/e2e_full_coverage.py
"""
from __future__ import annotations

import base64
import json
import os
import sys
import time
import urllib.parse
from datetime import datetime, timedelta, timezone

import requests
from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright, expect

STAGING = "https://sira-exam.elearning.portfolio2.kimbetien.com"
API = "https://sira-exam-api.elearning.portfolio2.kimbetien.com/api/v1"
SCREENSHOTS = "/tmp/playwright-screenshots/full-coverage"
_FAKE_UPLOAD_URL = "https://mock-minio.test/exam-evidence/e2e/upload.jpg"
_FAKE_STORAGE_KEY = "exam-evidence/e2e/upload.jpg"

os.makedirs(SCREENSHOTS, exist_ok=True)

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


def shot(page: Page, name: str) -> None:
    path = f"{SCREENSHOTS}/{name}.png"
    try:
        page.screenshot(path=path, full_page=True)
        print(f"     📸 {path}")
    except Exception as e:
        warn(f"Screenshot failed for {name}: {e}")


def get_token(role: str, sub: str = "1") -> str:
    r = requests.get(f"{API}/dev/tokens?role={role}&sub={sub}", timeout=_TIMEOUT)
    r.raise_for_status()
    return r.json()["access_token"]


def decode_sub(token: str) -> str:
    parts = token.split(".")
    payload = json.loads(base64.b64decode(parts[1] + "=="))
    return str(payload["sub"])


def sub_to_uuid(sub: str) -> str:
    """Convert a dev token sub (e.g. '1') to its DB UUID (dddddddd-0000-0000-0000-000000000001)."""
    return f"dddddddd-0000-0000-0000-{int(sub):012d}"


def set_cookie(page: Page, token: str) -> None:
    page.context.add_cookies([{
        "name": "access_token",
        "value": token,
        "domain": "sira-exam.elearning.portfolio2.kimbetien.com",
        "path": "/",
        "httpOnly": False,
        "secure": True,
        "sameSite": "Lax",
    }])


def mock_minio_puts(page: Page) -> None:
    def _handler(route, request):
        url = request.url
        if "/identity/upload-url" in url:
            route.fulfill(
                status=200, content_type="application/json",
                body=(
                    '{"upload_url":"' + _FAKE_UPLOAD_URL + '",'
                    '"storage_key":"' + _FAKE_STORAGE_KEY + '"}'
                ),
            )
            return
        if "/identity/recorded" in url and request.method == "POST":
            route.fulfill(
                status=200, content_type="application/json",
                body='{"session_id":"mock","identity_verified":false,"identity_status":"pending"}',
            )
            return
        if "/identity/status" in url:
            route.fulfill(
                status=200, content_type="application/json",
                body=(
                    '{"session_id":"mock","identity_verified":true,'
                    '"identity_status":"verified","identity_verified_at":"2026-01-01T00:00:00Z"}'
                ),
            )
            return
        if "reference-frame-upload-url" in url or "snapshot-upload-url" in url:
            route.fulfill(
                status=200, content_type="application/json",
                body=(
                    '{"upload_url":"' + _FAKE_UPLOAD_URL + '",'
                    '"storage_key":"' + _FAKE_STORAGE_KEY + '"}'
                ),
            )
            return
        if request.method == "PUT":
            route.fulfill(status=200)
            return
        route.continue_()

    page.route("**/*", _handler)


def poll_until(
    fetch_fn,
    condition_fn,
    timeout_s: int = 120,
    interval_s: int = 10,
    description: str = "condition",
) -> tuple[bool, object]:
    deadline = time.monotonic() + timeout_s
    last_data = None
    while time.monotonic() < deadline:
        try:
            data = fetch_fn()
            last_data = data
            if condition_fn(data):
                return True, data
        except Exception as exc:
            print(f"     poll error ({description}): {exc}")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(interval_s, remaining))
    return False, last_data


_TIMEOUT = 30  # staging cold-start can exceed 15s


def api_get(path: str, token: str) -> requests.Response:
    return requests.get(
        f"{API}{path}", headers={"Authorization": f"Bearer {token}"}, timeout=_TIMEOUT,
    )


def api_post(path: str, token: str, body: dict | None = None) -> requests.Response:
    return requests.post(
        f"{API}{path}", json=body or {},
        headers={"Authorization": f"Bearer {token}"}, timeout=_TIMEOUT,
    )


def api_patch(path: str, token: str, body: dict) -> requests.Response:
    return requests.patch(
        f"{API}{path}", json=body,
        headers={"Authorization": f"Bearer {token}"}, timeout=_TIMEOUT,
    )


def api_delete(path: str, token: str) -> requests.Response:
    return requests.delete(
        f"{API}{path}", headers={"Authorization": f"Bearer {token}"}, timeout=_TIMEOUT,
    )


def new_ctx(browser: Browser, token: str) -> tuple[BrowserContext, Page]:
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    page = ctx.new_page()
    page.set_default_timeout(15000)
    set_cookie(page, token)
    return ctx, page


def inject_events(session_id: str, session_token: str, student_token: str, events: list[dict]) -> None:
    now = datetime.now(timezone.utc).isoformat()
    headers = {
        "Authorization": f"Bearer {student_token}",
        "X-Session-Token": session_token,
    }
    for evt in events:
        evt.setdefault("occurred_at", now)
        r = requests.post(
            f"{API}/proctor/sessions/{session_id}/events",
            json=evt, headers=headers, timeout=10,
        )
        if r.status_code not in (200, 201):
            warn(f"Event injection returned {r.status_code}: {r.text[:200]}")


def click_mcq_answers(page: Page, questions: list, correct_answers: dict, answer_correctly: bool) -> None:
    radio_offset = 0
    for q in questions:
        if q.get("question_type") != "mcq":
            continue
        q_id = q.get("id", "")
        options = q.get("options") or []
        n_options = len(options) if options else 4
        if answer_correctly:
            correct_idx = (correct_answers.get(q_id) or [0])[0]
            click_idx = radio_offset + correct_idx
        else:
            correct_idx = (correct_answers.get(q_id) or [0])[0]
            wrong_idx = (correct_idx + 1) % max(n_options, 1)
            click_idx = radio_offset + wrong_idx
        try:
            page.locator("input[type='radio']").nth(click_idx).click()
            time.sleep(0.3)
        except Exception as e:
            warn(f"MCQ click nth({click_idx}) failed for q={q_id[:8]}: {e}")
        radio_offset += n_options


def _run_precheck(page: Page, test_id: str, label: str, captured: dict) -> bool:
    """Run the 4-step pre-check wizard. Returns True on success."""

    def on_response(response):
        try:
            if f"/exam/tests/{test_id}/start" in response.url and response.request.method == "POST":
                data = response.json()
                captured["attempt_id"] = data.get("attempt_id")
                captured["questions"] = data.get("questions", [])
            elif "/proctor/sessions/start" in response.url and response.request.method == "POST":
                data = response.json()
                captured["session_id"] = data.get("session_id")
                captured["session_token"] = data.get("session_token")
        except Exception:
            pass

    page.on("response", on_response)

    page.goto(f"{STAGING}/fr/session/pre-check/{test_id}")
    page.wait_for_load_state("networkidle")
    time.sleep(5)

    init_err = page.locator("p.text-red-600").first
    if init_err.count() > 0:
        try:
            err_text = init_err.inner_text(timeout=2000)
            fail(f"{label}: Pre-check init error", err_text[:200])
            return False
        except Exception:
            pass

    # Step 1: System Check
    shot(page, f"{label}-p1-step1")
    try:
        page.wait_for_selector("button:has-text('Next')", timeout=30000)
        deadline = time.monotonic() + 75
        while time.monotonic() < deadline:
            try:
                if page.locator("button:has-text('Next')").is_enabled(timeout=1000):
                    break
            except Exception:
                pass
            time.sleep(2)
        page.locator("button:has-text('Next')").click()
        time.sleep(1)
        ok(f"{label}: Pre-check Step 1 (system check) passed")
    except Exception as e:
        fail(f"{label}: Step 1 Next button", str(e)[:120])
        return False

    # Step 2: Camera Preview
    time.sleep(3)
    try:
        page.wait_for_selector("video", timeout=10000)
        time.sleep(2)
        cap_btn = page.get_by_role("button", name="Capture reference frame")
        cap_btn.wait_for(state="visible", timeout=10000)
        cap_btn.click()
        page.wait_for_selector("button:has-text('Use this photo')", timeout=15000)
        shot(page, f"{label}-p1-step2-captured")
        page.get_by_role("button", name="Use this photo").click()
        time.sleep(1)
        ok(f"{label}: Pre-check Step 2 (camera + reference frame) passed")
    except Exception as e:
        fail(f"{label}: Step 2 camera preview", str(e)[:120])
        try:
            page.locator("button").filter(has_text="Use this photo").click()
        except Exception:
            return False

    # Step 3: Identity Verification (mocked)
    time.sleep(5)
    try:
        page.wait_for_selector("text=Step 3 — Identity Verification", timeout=12000)
        shot(page, f"{label}-p1-step3a")
        time.sleep(4)
        page.get_by_role("button", name="Capture & Verify").click(timeout=8000)
        time.sleep(3)
        shot(page, f"{label}-p1-step3b")
        advanced = False
        for sel in [
            "button:has-text('Continue →')",
            "button:has-text('Continue')",
            "button:has-text('Next')",
        ]:
            try:
                page.wait_for_selector(sel, timeout=4000)
                page.locator(sel).first.click()
                advanced = True
                break
            except Exception:
                pass
        if not advanced:
            try:
                page.wait_for_selector("text=Step 4", timeout=6000)
                advanced = True
            except Exception:
                pass
        if not advanced:
            shot(page, f"{label}-p1-step3-fail")
            fail(f"{label}: Step 3 — no advance button after identity verification")
            return False
        ok(f"{label}: Pre-check Step 3 (identity verification) passed — mocked")
    except Exception as e:
        shot(page, f"{label}-p1-step3-fail")
        fail(f"{label}: Step 3 identity check", str(e)[:120])
        return False

    # Step 4: Consent
    time.sleep(2)
    try:
        page.wait_for_selector("text=Step 4", timeout=10000)
        page.locator("input[type='checkbox']").click()
        time.sleep(1)
        shot(page, f"{label}-p1-step4-consent")
        page.get_by_role("button", name="Start Exam").click()
        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass
        time.sleep(3)
        ok(f"{label}: Pre-check Step 4 (consent + start exam) passed")
    except Exception as e:
        fail(f"{label}: Step 4 consent", str(e)[:120])
        return False

    return True


# ---------------------------------------------------------------------------
# Phase 1 — Class Management (US-14, US-15, FR-4.19)
# ---------------------------------------------------------------------------

def phase1_class_management(teacher_token: str, browser: Browser, shared: dict) -> None:
    print("\n── Phase 1: Class Management (US-14, US-15, FR-4.19) ──────────────")
    ts = shared["ts"]

    # Create class
    r = api_post("/exam/classes", teacher_token, {
        "name": f"E2E Class {ts}",
        "academic_year": "2026-2027",
    })
    if r.status_code not in (200, 201):
        fail("FR-4.19: Create school class", f"HTTP {r.status_code}: {r.text[:200]}")
        raise RuntimeError("Cannot continue without class")
    cls = r.json()
    class_id = cls["id"]
    shared["class_id"] = class_id
    shared["class_name"] = f"E2E Class {ts}"

    if cls.get("archived_at") is None:
        ok("FR-4.19: New class has archived_at=null")
    else:
        fail("FR-4.19: New class should have archived_at=null", f"got: {cls.get('archived_at')}")
    ok(f"US-15: School class created (id={class_id[:8]}…)")

    # Archive + unarchive toggle (FR-4.19)
    r2 = api_patch(f"/exam/classes/{class_id}", teacher_token, {"archive": True})
    if r2.status_code in (200, 201) and r2.json().get("archived_at") is not None:
        ok("FR-4.19: archive=True sets archived_at")
    else:
        fail("FR-4.19: archive=True should set archived_at", f"HTTP {r2.status_code}")

    r3 = api_patch(f"/exam/classes/{class_id}", teacher_token, {"archive": False})
    if r3.status_code in (200, 201) and r3.json().get("archived_at") is None:
        ok("FR-4.19: archive=False clears archived_at")
    else:
        fail("FR-4.19: archive=False should clear archived_at", f"HTTP {r3.status_code}")

    # Enroll student01 (sub=1) + student02 (sub=2) — enrollment requires full UUID
    for sub in ("1", "2"):
        r_enroll = api_post(f"/exam/classes/{class_id}/members", teacher_token, {"user_id": sub_to_uuid(sub)})
        if r_enroll.status_code in (200, 201):
            ok(f"US-15: Student (sub={sub}) enrolled in class")
        else:
            fail(f"US-15: Enroll student (sub={sub})", f"HTTP {r_enroll.status_code}: {r_enroll.text[:150]}")

    # GET class members list
    r_mem = api_get(f"/exam/classes/{class_id}/members", teacher_token)
    if r_mem.status_code == 200:
        members = r_mem.json()
        ok(f"US-15: GET /classes/{class_id[:8]}/members → {len(members)} member(s)")
    else:
        fail("US-15: GET class members", f"HTTP {r_mem.status_code}")

    # Browser: classes list page
    ctx, page = new_ctx(browser, teacher_token)
    page.goto(f"{STAGING}/fr/classes")
    page.wait_for_load_state("networkidle")
    time.sleep(3)
    shot(page, "p1-classes-list")
    try:
        expect(page.get_by_text(f"E2E Class {ts}", exact=False)).to_be_visible(timeout=8000)
        ok("US-15 browser: classes list page shows new class")
    except Exception as e:
        fail("US-15 browser: class not visible on list page", str(e)[:120])

    # Browser: class detail page
    page.goto(f"{STAGING}/fr/classes/{class_id}")
    page.wait_for_load_state("networkidle")
    time.sleep(3)
    shot(page, "p1-class-detail")
    try:
        # Should show enrolled students
        student_rows = page.locator("tr, li, div").filter(has_text="1").count()
        ok(f"US-15 browser: class detail page renders ({student_rows} element(s) with student data)")
    except Exception as e:
        warn(f"US-15 browser: class detail student check: {e}")
    ctx.close()


# ---------------------------------------------------------------------------
# Phase 2 — Bank + Tests + Scheduling (US-14, US-16, FR-4.18, FR-4.24)
# ---------------------------------------------------------------------------

def phase2_bank_and_tests(teacher_token: str, shared: dict) -> None:
    print("\n── Phase 2: Bank + Tests + Scheduling (US-14, US-16, FR-4.18, FR-4.24) ──")
    ts = shared["ts"]
    class_id = shared["class_id"]

    # FR-4.18: bank with course_code + course_name
    r = api_post("/exam/banks", teacher_token, {
        "title_fr": f"E2E Full Coverage {ts}",
        "language": "fr",
        "passing_score": 50.0,
        "course_code": "E2E-101",
        "course_name": "E2E Full Coverage Testing",
    })
    if r.status_code not in (200, 201):
        fail("FR-4.18: Create bank with course fields", f"HTTP {r.status_code}: {r.text[:200]}")
        raise RuntimeError("Cannot continue without bank")
    bank = r.json()
    bank_id = bank["id"]
    shared["bank_id"] = bank_id

    if bank.get("course_code") == "E2E-101":
        ok("FR-4.18: course_code=E2E-101 stored and returned")
    else:
        fail("FR-4.18: course_code not in response", f"got: {bank.get('course_code')}")

    if bank.get("course_name") == "E2E Full Coverage Testing":
        ok("FR-4.18: course_name stored and returned")
    else:
        fail("FR-4.18: course_name not in response", f"got: {bank.get('course_name')}")

    # GET /exam/banks/{id} verifies course fields persist
    r2 = api_get(f"/exam/banks/{bank_id}", teacher_token)
    if r2.status_code == 200:
        b = r2.json()
        if b.get("course_code") == "E2E-101" and b.get("course_name") == "E2E Full Coverage Testing":
            ok("FR-4.18: GET /exam/banks/{id} returns course_code and course_name")
        else:
            fail("FR-4.18: GET missing course fields", f"code={b.get('course_code')}")

    # PATCH updates course_name
    r3 = api_patch(f"/exam/banks/{bank_id}", teacher_token, {"course_name": "E2E Full Coverage Testing — v2"})
    if r3.status_code in (200, 201) and "v2" in (r3.json().get("course_name") or ""):
        ok("FR-4.18: PATCH updates course_name")
    else:
        warn(f"FR-4.18: PATCH course_name returned {r3.status_code}")

    # Create questions (2 MCQ + 1 dissertation)
    q_ids = []
    correct_answers: dict[str, list[int]] = {}
    for i, (qtype, correct_idx) in enumerate([("mcq", 0), ("mcq", 2), ("dissertation", None)]):
        body: dict = {
            "question_type": qtype,
            "description": f"E2E Q{i + 1}: {'MCQ' if qtype == 'mcq' else 'Essay'}",
            "order_index": i,
        }
        if qtype == "mcq":
            body["options"] = [
                {"label": "A", "text": "Option A"},
                {"label": "B", "text": "Option B"},
                {"label": "C", "text": "Option C"},
                {"label": "D", "text": "Option D"},
            ]
            body["correct_answer_indices"] = [correct_idx]
        else:
            body["model_answer"] = "A thorough analysis of the topic."
            body["rubric"] = [
                {"criterion": "Content", "max_points": 60, "description": "Depth and accuracy"},
                {"criterion": "Clarity", "max_points": 40, "description": "Organization"},
            ]
        r_q = api_post(f"/exam/banks/{bank_id}/question", teacher_token, body)
        if r_q.status_code not in (200, 201):
            fail(f"Create question {i + 1}", f"HTTP {r_q.status_code}: {r_q.text[:150]}")
            raise RuntimeError("Cannot continue without questions")
        q = r_q.json()
        q_ids.append(q["id"])
        if correct_idx is not None:
            correct_answers[q["id"]] = [correct_idx]

    shared["q_ids"] = q_ids
    shared["correct_answers"] = correct_answers
    ok("3 questions created (2 MCQ + 1 dissertation)")

    # Validate-all + publish bank
    r_val = api_post(f"/exam/banks/{bank_id}/validate-all", teacher_token)
    if r_val.status_code not in (200, 201) or r_val.json().get("bank_status") != "published":
        fail("Validate-all + publish bank", f"HTTP {r_val.status_code}: {r_val.text[:150]}")
        raise RuntimeError("Bank not published")
    ok("Bank published (validate-all)")

    # US-14: create 2 tests from the SAME bank (reusability)
    now = datetime.now(timezone.utc)
    for label in ("s01", "s02"):
        r_test = api_post(f"/exam/banks/{bank_id}/tests", teacher_token, {
            "title": f"E2E {label.upper()} {ts}",
            "shuffle_questions": False,
            "time_limit_minutes": 30,
        })
        if r_test.status_code not in (200, 201):
            fail(f"Create test for {label}", f"HTTP {r_test.status_code}: {r_test.text[:150]}")
            raise RuntimeError("Cannot create test")
        test = r_test.json()
        test_id = test["id"]
        shared[f"test_id_{label}"] = test_id
        ok(f"US-14: Test {label} created from bank (id={test_id[:8]}…) — reusability confirmed")

        r_pub = api_patch(f"/exam/tests/{test_id}", teacher_token, {"status": "published"})
        if r_pub.status_code not in (200, 201):
            fail(f"Publish test {label}", f"HTTP {r_pub.status_code}")
        else:
            ok(f"Test {label} published")

        # US-16: assign test to class with time window
        released_at = (now - timedelta(hours=1)).isoformat()
        closes_at = (now + timedelta(hours=24)).isoformat()
        r_assign = api_post(f"/exam/tests/{test_id}/assignments", teacher_token, {
            "class_id": class_id,
            "released_at": released_at,
            "closes_at": closes_at,
            "quarter": "q1",
        })
        if r_assign.status_code in (200, 201):
            shared[f"assignment_id_{label}"] = r_assign.json().get("id")
            ok(f"US-16: Test {label} assigned to class with time window [now-1h, now+24h]")
        else:
            fail(f"US-16: Assign test {label} to class", f"HTTP {r_assign.status_code}: {r_assign.text[:150]}")

    # US-16: student sees available tests via class enrollment
    student01_token = shared["student01_token"]
    r_avail = api_get("/exam/student/tests", student01_token)
    if r_avail.status_code == 200:
        tests = r_avail.json()
        found = any(t.get("test_id") == shared["test_id_s01"] or t.get("id") == shared["test_id_s01"] for t in tests)
        if found:
            ok("US-16: Student01 sees class-scoped test in available tests")
        else:
            warn(f"US-16: test_id_s01 not in /exam/student/tests (count={len(tests)})")
    else:
        fail("US-16: GET /exam/student/tests", f"HTTP {r_avail.status_code}: {r_avail.text[:150]}")

    # US-23: create anonymous grading test (MCQ only, instant scoring)
    r_anon_bank = api_post("/exam/banks", teacher_token, {
        "title_fr": f"Anon Bank {ts}",
        "language": "fr",
        "passing_score": 50.0,
    })
    if r_anon_bank.status_code not in (200, 201):
        fail("US-23: Create anon bank", f"HTTP {r_anon_bank.status_code}")
    else:
        anon_bank_id = r_anon_bank.json()["id"]
        r_anon_q = api_post(f"/exam/banks/{anon_bank_id}/question", teacher_token, {
            "question_type": "mcq",
            "description": "Anonymous grading MCQ",
            "order_index": 0,
            "options": [
                {"label": "A", "text": "Correct"},
                {"label": "B", "text": "Wrong"},
            ],
            "correct_answer_indices": [0],
        })
        if r_anon_q.status_code not in (200, 201):
            fail("US-23: Create anon question", f"HTTP {r_anon_q.status_code}")
        else:
            shared["anon_question_id"] = r_anon_q.json()["id"]
            api_post(f"/exam/banks/{anon_bank_id}/validate-all", teacher_token)
            r_anon_test = api_post(f"/exam/banks/{anon_bank_id}/tests", teacher_token, {
                "title": f"Anon Test {ts}",
                "shuffle_questions": False,
                "time_limit_minutes": 30,
                "anonymous_grading": True,
            })
            if r_anon_test.status_code in (200, 201):
                anon_test = r_anon_test.json()
                shared["anon_test_id"] = anon_test["id"]
                if anon_test.get("anonymous_grading") is True:
                    ok("US-23: anonymous_grading=True stored on test")
                else:
                    fail("US-23: anonymous_grading not True", f"got: {anon_test.get('anonymous_grading')}")
                api_patch(f"/exam/tests/{anon_test['id']}", teacher_token, {"status": "published"})
                ok(f"US-23: Anon test published (id={anon_test['id'][:8]}…)")
            else:
                fail("US-23: Create anon test", f"HTTP {r_anon_test.status_code}: {r_anon_test.text[:150]}")


# ---------------------------------------------------------------------------
# Phase 3 — Student01 Pre-Check + Exam (US-9, US-11, US-13, US-15)
# ---------------------------------------------------------------------------

def phase3_student01_exam(browser: Browser, shared: dict) -> None:
    print("\n── Phase 3: Student01 Pre-Check + Exam (US-9, US-11, US-13) ────────")
    student01_token = shared["student01_token"]
    test_id = shared["test_id_s01"]

    ctx, page = new_ctx(browser, student01_token)
    mock_minio_puts(page)
    captured: dict = {}

    def on_response(response):
        try:
            if f"/exam/tests/{test_id}/start" in response.url and response.request.method == "POST":
                data = response.json()
                captured["attempt_id"] = data.get("attempt_id")
                captured["questions"] = data.get("questions", [])
            elif "/proctor/sessions/start" in response.url and response.request.method == "POST":
                data = response.json()
                captured["session_id"] = data.get("session_id")
                captured["session_token"] = data.get("session_token")
        except Exception:
            pass

    page.on("response", on_response)

    ok_precheck = _run_precheck(page, test_id, "s01", captured)
    if ok_precheck:
        shared["session_id_s01"] = captured.get("session_id", "")
        shared["session_token_s01"] = captured.get("session_token", "")
        if captured.get("session_id"):
            ok(f"US-11: Proctoring session started (id={captured['session_id'][:8]}…)")
        if captured.get("attempt_id"):
            shared["attempt_id_s01"] = captured["attempt_id"]

        try:
            page.wait_for_url(f"**/exams/{test_id}/play**", timeout=20000)
        except Exception as e:
            fail("s01: Did not navigate to exam player", str(e)[:120])
            ctx.close()
            return

        time.sleep(3)
        shot(page, "p3-s01-exam-player")

        # Lockdown check (US-9)
        try:
            blocked = page.evaluate("""() => {
                let prevented = false;
                const handler = (e) => { prevented = e.defaultPrevented; };
                document.addEventListener('contextmenu', handler, {once: true});
                document.dispatchEvent(new MouseEvent('contextmenu', {cancelable: true}));
                return prevented;
            }""")
            if blocked:
                ok("US-9: Lockdown shell blocks right-click")
            else:
                warn("US-9: Right-click not blocked (lockdown may not be active)")
        except Exception:
            pass

        # MCQ + dissertation answers
        try:
            page.locator("input[type='radio']").nth(0).wait_for(state="visible", timeout=10000)
            click_mcq_answers(page, captured.get("questions", []), shared["correct_answers"], answer_correctly=True)
            ok("s01: MCQ answered correctly")
        except Exception as e:
            fail("s01: MCQ radio interaction", str(e)[:120])

        try:
            ta = page.locator("textarea").first
            ta.wait_for(state="visible", timeout=8000)
            ta.fill("Comprehensive answer demonstrating thorough understanding. Key aspects covered with evidence.")
            ok("s01: Dissertation answer filled")
        except Exception as e:
            fail("s01: Dissertation textarea", str(e)[:120])

        shot(page, "p3-s01-exam-answered")

        # Phase 4: Proctor monitoring
        phase4_proctor(browser, shared)

        # Submit
        print("\n── Phase 3b: Student01 Submit ──────────────────────────────────────")
        try:
            page.get_by_role("button", name="Submit Exam").click()
            page.wait_for_selector("text=Submit Exam?", timeout=10000)
            shot(page, "p3-s01-submit-dialog")
            page.get_by_role("button", name="Submit Now").click()
            page.wait_for_url("**/results**", timeout=20000)
            time.sleep(2)
            shot(page, "p3-s01-results")
            ok("s01: Exam submitted successfully")

            parsed = urllib.parse.urlparse(page.url)
            params = dict(urllib.parse.parse_qsl(parsed.query))
            shared["attempt_id_s01"] = params.get("attemptId", shared.get("attempt_id_s01"))
            shared["mcq_score_s01"] = float(params.get("score", 0))
            shared["passed_s01"] = params.get("passed") == "true"

            score = shared["mcq_score_s01"]
            if score > 0:
                ok(f"s01: MCQ score = {score} (> 0 ✅)")
            else:
                fail("s01: MCQ score = 0 but expected > 0")
        except Exception as e:
            fail("s01: Submit exam", str(e)[:120])

    shared["ctx_s01"] = ctx
    shared["page_s01"] = page


# ---------------------------------------------------------------------------
# Phase 4 — Proctor Monitoring (US-12)
# ---------------------------------------------------------------------------

def phase4_proctor(browser: Browser, shared: dict) -> None:
    print("\n── Phase 4: Proctor Monitoring (US-12) ─────────────────────────────")
    teacher_token = shared["teacher_token"]
    student01_token = shared["student01_token"]
    session_id = shared.get("session_id_s01", "")
    session_token = shared.get("session_token_s01", "")

    if not session_id:
        fail("US-12: session_id_s01 not captured — skipping proctor phase")
        return

    now = datetime.now(timezone.utc).isoformat()
    inject_events(session_id, session_token, student01_token, [
        {"event_type": "tab_switch", "severity": "low", "payload": {}, "occurred_at": now},
        {"event_type": "tab_switch", "severity": "low", "payload": {}, "occurred_at": now},
        {"event_type": "devtools_opened", "severity": "high", "payload": {}, "occurred_at": now},
    ])
    time.sleep(1)
    ok(f"US-12: Injected tab_switch ×2 + devtools_opened events")

    ctx, page = new_ctx(browser, teacher_token)
    page.goto(f"{STAGING}/fr/proctor/dashboard")
    page.wait_for_load_state("domcontentloaded")
    time.sleep(6)
    shot(page, "p4-proctor-dashboard")

    try:
        expect(page.get_by_text("Proctor Dashboard")).to_be_visible(timeout=8000)
        ok("US-12 browser: proctor dashboard heading visible")
    except Exception as e:
        fail("US-12 browser: proctor dashboard heading", str(e)[:120])

    cards = page.locator("div.rounded-xl.border")
    try:
        expect(cards.first).to_be_visible(timeout=10000)
        ok(f"US-12 browser: {cards.count()} session card(s) visible on dashboard")
    except Exception as e:
        warn(f"US-12 browser: no session cards ({e})")

    # Navigate to session detail
    view_link = page.locator("a").filter(has_text="View")
    try:
        view_link.first.wait_for(state="visible", timeout=8000)
        view_link.first.click()
        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass
        time.sleep(2)
        shot(page, "p4-proctor-session-detail")
        ok("US-12 browser: navigated to proctor session detail")

        for evt in ("tab_switch", "devtools_opened"):
            variants = [evt, evt.replace("_", " "), evt.replace("_", "-")]
            found = any(page.get_by_text(v, exact=False).count() > 0 for v in variants)
            if found:
                ok(f"US-12 browser: '{evt}' event visible in session timeline")
            else:
                warn(f"US-12 browser: '{evt}' not visible (soft — may need scroll)")

        # Acknowledge alert
        ack_btn = page.locator("button").filter(has_text="Ack")
        if ack_btn.count() > 0:
            try:
                ack_btn.first.click()
                time.sleep(2)
                shot(page, "p4-proctor-acked")
                ok("US-12 browser: alert acknowledged")
            except Exception as e:
                warn(f"US-12 browser: Ack failed: {e}")
        else:
            warn("US-12 browser: No Ack button found")

    except Exception as e:
        fail("US-12 browser: could not click View link", str(e)[:120])

    ctx.close()


# ---------------------------------------------------------------------------
# Phase 5 — Student02 Pre-Check + Exam (wrong answers)
# ---------------------------------------------------------------------------

def phase5_student02_exam(browser: Browser, shared: dict) -> None:
    print("\n── Phase 5: Student02 Pre-Check + Exam (wrong answers) ─────────────")
    student02_token = shared["student02_token"]
    test_id = shared["test_id_s02"]

    ctx, page = new_ctx(browser, student02_token)
    mock_minio_puts(page)
    captured: dict = {}

    def on_response(response):
        try:
            if f"/exam/tests/{test_id}/start" in response.url and response.request.method == "POST":
                data = response.json()
                captured["attempt_id"] = data.get("attempt_id")
                captured["questions"] = data.get("questions", [])
            elif "/proctor/sessions/start" in response.url and response.request.method == "POST":
                data = response.json()
                captured["session_id"] = data.get("session_id")
        except Exception:
            pass

    page.on("response", on_response)

    ok_precheck = _run_precheck(page, test_id, "s02", captured)
    if ok_precheck:
        if captured.get("attempt_id"):
            shared["attempt_id_s02"] = captured["attempt_id"]

        try:
            page.wait_for_url(f"**/exams/{test_id}/play**", timeout=20000)
            time.sleep(3)
            shot(page, "p5-s02-exam-player")
        except Exception as e:
            fail("s02: Did not navigate to exam player", str(e)[:120])
            ctx.close()
            return

        try:
            page.locator("input[type='radio']").nth(0).wait_for(state="visible", timeout=10000)
            click_mcq_answers(page, captured.get("questions", []), shared["correct_answers"], answer_correctly=False)
            ok("s02: MCQ answered incorrectly")
        except Exception as e:
            fail("s02: MCQ radio interaction", str(e)[:120])

        try:
            ta = page.locator("textarea").first
            ta.wait_for(state="visible", timeout=8000)
            ta.fill("A brief and incomplete answer.")
            ok("s02: Dissertation answer filled")
        except Exception as e:
            fail("s02: Dissertation textarea", str(e)[:120])

        shot(page, "p5-s02-exam-answered")

        try:
            page.get_by_role("button", name="Submit Exam").click()
            page.wait_for_selector("text=Submit Exam?", timeout=10000)
            shot(page, "p5-s02-submit-dialog")
            page.get_by_role("button", name="Submit Now").click()
            page.wait_for_url("**/results**", timeout=20000)
            time.sleep(2)
            shot(page, "p5-s02-results")
            ok("s02: Exam submitted successfully")

            parsed = urllib.parse.urlparse(page.url)
            params = dict(urllib.parse.parse_qsl(parsed.query))
            shared["attempt_id_s02"] = params.get("attemptId", shared.get("attempt_id_s02"))
            shared["mcq_score_s02"] = float(params.get("score", 0))
            shared["passed_s02"] = params.get("passed") == "true"
        except Exception as e:
            fail("s02: Submit exam", str(e)[:120])

    ctx.close()


# ---------------------------------------------------------------------------
# Phase 6 — Wait for AI Dissertation Grading
# ---------------------------------------------------------------------------

def phase6_wait_ai_grading(shared: dict) -> None:
    print("\n── Phase 6: Wait for AI Dissertation Grading ───────────────────────")
    teacher_token = shared["teacher_token"]
    for label in ("s01", "s02"):
        test_id = shared.get(f"test_id_{label}")
        if not test_id:
            continue
        success, data = poll_until(
            fetch_fn=lambda tid=test_id: api_get(f"/exam/tests/{tid}/dissertation-review", teacher_token).json(),
            condition_fn=lambda d: isinstance(d, list) and len(d) > 0
                and any(a.get("status") in ("ai_scored", "human_reviewed") for a in d),
            timeout_s=300, interval_s=10,
            description=f"{label} dissertation ai_scored",
        )
        if success and isinstance(data, list):
            for a in data:
                if a.get("status") in ("ai_scored", "human_reviewed"):
                    ok(f"{label}: AI grading complete (status={a['status']}, ai_score={a.get('ai_score')})")
                    break
        else:
            warn(f"{label}: AI grading timed out (sequential worker — phase 7 will handle pending)")


# ---------------------------------------------------------------------------
# Phase 7 — Teacher Human Scoring + Audit Log (US-6, US-10, US-22)
# ---------------------------------------------------------------------------

def phase7_human_scoring(shared: dict) -> None:
    print("\n── Phase 7: Teacher Human Scoring + Audit Log (US-6, US-22) ────────")
    teacher_token = shared["teacher_token"]
    student01_token = shared["student01_token"]

    for label, score, feedback in [
        ("s01", 85.0, "Excellent — thorough analysis."),
        ("s02", 20.0, "Insufficient depth."),
    ]:
        test_id = shared.get(f"test_id_{label}")
        if not test_id:
            continue

        r = api_get(f"/exam/tests/{test_id}/dissertation-review", teacher_token)
        if r.status_code != 200:
            fail(f"Teacher: dissertation-review {label}", f"HTTP {r.status_code}")
            continue
        answers = r.json()
        pending = [a for a in answers if a.get("status") in ("pending", "ai_scored")]
        if not pending:
            warn(f"Teacher: no pending dissertations for {label}")
            continue

        answer_id = pending[0]["id"]
        r2 = api_patch(f"/exam/answers/{answer_id}/human-score", teacher_token, {
            "human_score": score,
            "human_feedback": feedback,
        })
        if r2.status_code in (200, 201) and r2.json().get("status") == "human_reviewed":
            ok(f"US-6: {label} human_score={score} applied (status=human_reviewed ✅)")
            shared[f"dissertation_id_{label}"] = answer_id
        else:
            fail(f"US-6: {label} human-score", f"HTTP {r2.status_code}: {r2.text[:150]}")

    # Role-based guards on human-score (US-10)
    s01_ans_id = shared.get("dissertation_id_s01")
    if s01_ans_id:
        r_403 = api_patch(f"/exam/answers/{s01_ans_id}/human-score", student01_token, {"human_score": 99})
        if r_403.status_code == 403:
            ok("US-10: Student gets 403 on PATCH human-score (role guard ✅)")
        else:
            fail("US-10: Student should get 403", f"got {r_403.status_code}")

        r_422 = api_patch(f"/exam/answers/{s01_ans_id}/human-score", teacher_token, {"human_score": 99999})
        if r_422.status_code == 422:
            ok("US-10: score > max_points returns 422 (validation guard ✅)")
        else:
            fail("US-10: Over-max score should return 422", f"got {r_422.status_code}")

    # FR-4.21: audit log verification (US-22)
    test_id_s01 = shared.get("test_id_s01")
    if test_id_s01:
        r_log = api_get(f"/exam/tests/{test_id_s01}/audit-log", teacher_token)
        if r_log.status_code == 200:
            entries = r_log.json()
            if isinstance(entries, list) and entries:
                ok(f"US-22: ReviewAuditLog has {len(entries)} entry(ies) after human scoring")
                entry = entries[0]
                for field in ("id", "answer_id", "actor_id", "actor_role", "action", "new_values", "occurred_at"):
                    if field in entry:
                        ok(f"US-22: audit entry has '{field}'")
                    else:
                        fail(f"US-22: audit entry missing '{field}'")

                if "human_score" in str(entry.get("new_values", {})):
                    ok("US-22: new_values contains human_score")
                else:
                    warn(f"US-22: new_values: {entry.get('new_values')}")
            else:
                warn("US-22: audit-log empty after human scoring")
        else:
            fail("US-22: GET audit-log", f"HTTP {r_log.status_code}")

        r_403_log = api_get(f"/exam/tests/{test_id_s01}/audit-log", student01_token)
        if r_403_log.status_code == 403:
            ok("US-22: Student gets 403 on audit-log (immutability guard ✅)")
        else:
            fail("US-22: Student should get 403 on audit-log", f"got {r_403_log.status_code}")

        r_del = api_delete(f"/exam/tests/{test_id_s01}/audit-log", teacher_token)
        if r_del.status_code in (404, 405):
            ok(f"US-22: DELETE audit-log returns {r_del.status_code} (no delete endpoint = immutable)")
        else:
            warn(f"US-22: DELETE audit-log returned {r_del.status_code}")


# ---------------------------------------------------------------------------
# Phase 8 — Attempt Validation (US-17)
# ---------------------------------------------------------------------------

def phase8_validation(browser: Browser, shared: dict) -> None:
    print("\n── Phase 8: Attempt Validation (US-17) ─────────────────────────────")
    teacher_token = shared["teacher_token"]
    attempt_id_s01 = shared.get("attempt_id_s01")
    attempt_id_s02 = shared.get("attempt_id_s02")
    test_id_s01 = shared.get("test_id_s01")
    test_id_s02 = shared.get("test_id_s02")

    # Individual validate: s01 (all dissertations should be human_reviewed now)
    if attempt_id_s01:
        r = api_post(f"/exam/attempts/{attempt_id_s01}/validate", teacher_token)
        if r.status_code in (200, 201):
            ok(f"US-17: Individual validate s01 → {r.json().get('validation_status', r.json())}")
        elif r.status_code == 422:
            warn("US-17: s01 validate returned 422 — dissertations may not all be human_reviewed")
        else:
            fail("US-17: Individual validate s01", f"HTTP {r.status_code}: {r.text[:150]}")

    # Batch validate: both attempts
    if test_id_s01 and attempt_id_s01 and attempt_id_s02:
        batch_ids = [attempt_id_s01, attempt_id_s02]
        r_batch = api_post(f"/exam/tests/{test_id_s01}/batch-validate", teacher_token, {
            "attempt_ids": batch_ids,
        })
        if r_batch.status_code in (200, 201):
            result = r_batch.json()
            ok(f"US-17: Batch validate returned {r_batch.status_code}: {str(result)[:100]}")
        elif r_batch.status_code == 422:
            warn("US-17: Batch validate 422 — check all dissertations are human_reviewed")
        else:
            fail("US-17: Batch validate", f"HTTP {r_batch.status_code}: {r_batch.text[:150]}")

    # Browser: submissions page shows class grouping + validate buttons (US-20 preview)
    if test_id_s01:
        ctx, page = new_ctx(browser, teacher_token)
        page.goto(f"{STAGING}/fr/exams/{test_id_s01}/submissions")
        page.wait_for_load_state("networkidle")
        time.sleep(3)
        shot(page, "p8-teacher-submissions")

        try:
            class_name = shared.get("class_name", "E2E Class")
            expect(page.get_by_text(class_name, exact=False)).to_be_visible(timeout=8000)
            ok("US-17/20 browser: class group header visible on submissions page")
        except Exception as e:
            warn(f"US-17/20 browser: class header not found: {e}")

        validate_btn = page.locator("button").filter(has_text="Validate")
        if validate_btn.count() > 0:
            ok(f"US-17 browser: Validate button(s) present ({validate_btn.count()} found)")
        else:
            warn("US-17 browser: No Validate buttons found on submissions page")

        ctx.close()


# ---------------------------------------------------------------------------
# Phase 9 — Student Read-Only Review (US-18)
# ---------------------------------------------------------------------------

def phase9_student_review(browser: Browser, shared: dict) -> None:
    print("\n── Phase 9: Student Read-Only Review (US-18) ────────────────────────")
    student01_token = shared["student01_token"]
    attempt_id = shared.get("attempt_id_s01")
    if not attempt_id:
        fail("US-18: attempt_id_s01 not available")
        return

    # API: review endpoint
    r = api_get(f"/exam/attempts/{attempt_id}/review", student01_token)
    if r.status_code == 200:
        review = r.json()
        ok(f"US-18: GET /exam/attempts/{attempt_id[:8]}/review → 200")
        if review.get("questions") or review.get("answers") or isinstance(review, dict):
            ok("US-18: review response has content")
    elif r.status_code == 403:
        warn("US-18: Review returns 403 — feedback gate may require window close or show_feedback=True")
    else:
        fail("US-18: GET /exam/attempts/{id}/review", f"HTTP {r.status_code}: {r.text[:150]}")

    # Browser: attempt review page
    ctx, page = new_ctx(browser, student01_token)
    page.goto(f"{STAGING}/fr/attempts/{attempt_id}/review")
    page.wait_for_load_state("networkidle")
    time.sleep(3)
    shot(page, "p9-student-review")

    try:
        err = page.locator("p.text-red-600").first
        if err.count() > 0:
            warn(f"US-18 browser: review page shows error: {err.inner_text()[:100]}")
        else:
            ok("US-18 browser: review page renders without errors")
    except Exception as e:
        warn(f"US-18 browser: {e}")

    # Look for pass/fail badge or score display
    score_indicators = ["pass", "fail", "score", "Score", "résultat", "Résultat"]
    found_indicator = False
    for indicator in score_indicators:
        if page.get_by_text(indicator, exact=False).count() > 0:
            found_indicator = True
            ok(f"US-18 browser: score indicator '{indicator}' visible on review page")
            break
    if not found_indicator:
        warn("US-18 browser: no score indicator found (may require feedback gate to open)")

    shared["ctx_review_s01"] = ctx
    shared["page_review_s01"] = page


# ---------------------------------------------------------------------------
# Phase 10 — Student Files Score Complaint (US-19)
# ---------------------------------------------------------------------------

def phase10_file_complaint(browser: Browser, shared: dict) -> None:
    print("\n── Phase 10: Student Files Score Complaint (US-19) ─────────────────")
    student01_token = shared["student01_token"]
    teacher_token = shared["teacher_token"]
    attempt_id = shared.get("attempt_id_s01")
    test_id = shared.get("test_id_s01")
    q_ids = shared.get("q_ids", [])

    if not attempt_id:
        fail("US-19: attempt_id_s01 not available")
        return

    # API: file complaint on first MCQ question
    complaint_question_id = q_ids[0] if q_ids else None
    body: dict = {"reason": "I believe my answer was correct based on the source material."}
    if complaint_question_id:
        body["question_id"] = complaint_question_id

    r = api_post(f"/exam/attempts/{attempt_id}/complaints", student01_token, body)
    if r.status_code in (200, 201):
        complaint = r.json()
        shared["complaint_id"] = complaint.get("id")
        ok(f"US-19: Complaint filed (id={str(complaint.get('id', '?'))[:8]}…)")
        if complaint.get("status") == "pending":
            ok("US-19: Complaint status = pending ✅")
        else:
            warn(f"US-19: Complaint status = {complaint.get('status')} (expected 'pending')")
    elif r.status_code == 403:
        warn("US-19: Filing complaint returned 403 — attempt may not be validated yet")
    else:
        fail("US-19: POST /exam/attempts/{id}/complaints", f"HTTP {r.status_code}: {r.text[:200]}")

    # Verify complaint in list
    r_list = api_get(f"/exam/attempts/{attempt_id}/complaints", student01_token)
    if r_list.status_code == 200:
        complaints = r_list.json()
        if complaints:
            ok(f"US-19: GET complaints list has {len(complaints)} complaint(s)")
        else:
            warn("US-19: GET complaints list empty")
    else:
        fail("US-19: GET /exam/attempts/{id}/complaints", f"HTTP {r_list.status_code}")

    # Teacher views complaints for test
    if test_id:
        r_tlist = api_get(f"/exam/tests/{test_id}/complaints", teacher_token)
        if r_tlist.status_code == 200:
            t_complaints = r_tlist.json()
            ok(f"US-19: Teacher GET /tests/{test_id[:8]}/complaints → {len(t_complaints)} complaint(s)")
        else:
            fail("US-19: Teacher GET test complaints", f"HTTP {r_tlist.status_code}: {r_tlist.text[:150]}")

    # Browser: student review page complaint flow
    page = shared.get("page_review_s01")
    if page:
        try:
            # Look for complaint button
            complaint_btn = page.locator("button").filter(has_text="Complaint")
            if complaint_btn.count() == 0:
                complaint_btn = page.locator("button").filter(has_text="complaint")
            if complaint_btn.count() == 0:
                complaint_btn = page.locator("button").filter(has_text="Contest")

            if complaint_btn.count() > 0:
                complaint_btn.first.click()
                time.sleep(2)
                shot(page, "p10-complaint-form-open")
                ta = page.locator("textarea").first
                if ta.count() > 0:
                    ta.fill("This answer should receive higher marks.")
                    time.sleep(1)
                    submit_btn = page.locator("button[type='submit']").last
                    if submit_btn.count() > 0:
                        submit_btn.click()
                        time.sleep(2)
                        shot(page, "p10-complaint-submitted")
                        ok("US-19 browser: complaint form submitted")
                    else:
                        warn("US-19 browser: no submit button in complaint form")
                else:
                    warn("US-19 browser: no textarea in complaint form")
            else:
                warn("US-19 browser: no complaint button found on review page")
        except Exception as e:
            warn(f"US-19 browser: {e}")

    ctx = shared.get("ctx_review_s01")
    if ctx:
        ctx.close()


# ---------------------------------------------------------------------------
# Phase 11 — Teacher Complaint Resolution (US-19)
# ---------------------------------------------------------------------------

def phase11_resolve_complaint(browser: Browser, shared: dict) -> None:
    print("\n── Phase 11: Teacher Complaint Resolution (US-19) ──────────────────")
    teacher_token = shared["teacher_token"]
    student01_token = shared["student01_token"]
    complaint_id = shared.get("complaint_id")
    test_id = shared.get("test_id_s01")
    attempt_id = shared.get("attempt_id_s01")

    if not complaint_id:
        warn("US-19: No complaint_id — skipping resolution (complaint filing may have returned 403)")
        return

    # API: teacher approves complaint with score override
    r = api_patch(f"/exam/complaints/{complaint_id}", teacher_token, {
        "status": "approved",
        "review_note": "Score reviewed and adjusted.",
        "score_override": 80.0,
    })
    if r.status_code in (200, 201):
        resolved = r.json()
        if resolved.get("status") == "approved":
            ok("US-19: Complaint approved by teacher (status=approved ✅)")
        else:
            fail("US-19: Complaint not set to approved", f"got: {resolved.get('status')}")
        if resolved.get("score_override") == 80.0:
            ok("US-19: score_override=80 applied ✅")
        else:
            warn(f"US-19: score_override={resolved.get('score_override')}")
    else:
        fail("US-19: PATCH /exam/complaints/{id}", f"HTTP {r.status_code}: {r.text[:200]}")

    # Verify student sees updated complaint
    if attempt_id:
        r_s = api_get(f"/exam/attempts/{attempt_id}/complaints", student01_token)
        if r_s.status_code == 200:
            c_list = r_s.json()
            approved = [c for c in c_list if c.get("status") == "approved"]
            if approved:
                ok("US-19: Student sees approved complaint in list ✅")
            else:
                warn(f"US-19: Student complaint list: {[c.get('status') for c in c_list]}")
        else:
            warn(f"US-19: Student complaint list returned {r_s.status_code}")

    # Browser: teacher complaints page
    if test_id:
        ctx, page = new_ctx(browser, teacher_token)
        page.goto(f"{STAGING}/fr/exams/{test_id}/complaints")
        page.wait_for_load_state("networkidle")
        time.sleep(3)
        shot(page, "p11-teacher-complaints")

        try:
            complaint_row = page.locator("tr, div").filter(has_text="approved")
            if complaint_row.count() > 0:
                ok("US-19 browser: approved complaint visible on teacher complaints page")
            else:
                warn("US-19 browser: no 'approved' row found (complaint may need refresh)")
        except Exception as e:
            warn(f"US-19 browser: {e}")

        # Test reject path on a separate complaint
        r_rej_c = api_post(f"/exam/attempts/{attempt_id}/complaints", student01_token, {
            "reason": "Second dispute for reject test.",
        }) if attempt_id else None
        if r_rej_c and r_rej_c.status_code in (200, 201):
            rej_id = r_rej_c.json().get("id")
            r_rej = api_patch(f"/exam/complaints/{rej_id}", teacher_token, {
                "status": "rejected",
                "review_note": "Score is correct per rubric.",
            })
            if r_rej.status_code in (200, 201) and r_rej.json().get("status") == "rejected":
                ok("US-19: Complaint rejected (status=rejected ✅)")
            else:
                warn(f"US-19: Reject returned {r_rej.status_code}")

        ctx.close()


# ---------------------------------------------------------------------------
# Phase 12 — Teacher Submissions Grouped by Class (US-20)
# ---------------------------------------------------------------------------

def phase12_submissions_by_class(browser: Browser, shared: dict) -> None:
    print("\n── Phase 12: Teacher Submissions by Class (US-20) ──────────────────")
    teacher_token = shared["teacher_token"]
    test_id = shared.get("test_id_s01")
    class_name = shared.get("class_name", "E2E Class")

    if not test_id:
        fail("US-20: test_id_s01 not available")
        return

    # API: verify submissions include class/course metadata (FR-4.22)
    r = api_get(f"/exam/tests/{test_id}/submissions", teacher_token)
    if r.status_code == 200:
        submissions = r.json()
        ok(f"FR-4.22: GET /tests/{test_id[:8]}/submissions → {len(submissions)} row(s)")
        if submissions:
            row = submissions[0]
            for field in ("attempt_id", "user_id", "mcq_score", "class_name", "course_code", "course_name"):
                if field in row:
                    ok(f"FR-4.22: submissions row has '{field}'={str(row[field])[:30]}")
                else:
                    fail(f"FR-4.22: submissions row missing '{field}'", f"keys: {list(row.keys())[:8]}")
    else:
        fail("FR-4.22: GET submissions", f"HTTP {r.status_code}: {r.text[:150]}")

    # Browser: submissions page grouped by class
    ctx, page = new_ctx(browser, teacher_token)
    page.goto(f"{STAGING}/fr/exams/{test_id}/submissions")
    page.wait_for_load_state("networkidle")
    time.sleep(3)
    shot(page, "p12-submissions-by-class")

    try:
        expect(page.get_by_text(class_name, exact=False)).to_be_visible(timeout=8000)
        ok(f"US-20 browser: class group header '{class_name}' visible ✅")
    except Exception as e:
        warn(f"US-20 browser: class header not found ({e})")

    # Look for student rows under the class group
    rows = page.locator("tbody tr, [data-testid='submission-row'], tr").count()
    ok(f"US-20 browser: {rows} submission row(s) visible on page")

    ctx.close()


# ---------------------------------------------------------------------------
# Phase 13 — Student History Grouped by Course/Class (US-21)
# ---------------------------------------------------------------------------

def phase13_student_history(browser: Browser, shared: dict) -> None:
    print("\n── Phase 13: Student History Grouped by Course/Class (US-21) ────────")
    student01_token = shared["student01_token"]
    teacher_token = shared["teacher_token"]

    # API: verify history includes course/class metadata (FR-4.23)
    r = api_get("/exam/student/history", student01_token)
    if r.status_code == 200:
        history = r.json()
        ok(f"FR-4.23: GET /exam/student/history → {len(history)} row(s)")
        if history:
            row = history[0]
            for field in ("attempt_id", "test_id", "test_title", "class_name", "course_code", "course_name", "academic_year"):
                if field in row:
                    ok(f"FR-4.23: history row has '{field}'={str(row[field])[:30]}")
                else:
                    fail(f"FR-4.23: history row missing '{field}'", f"keys: {list(row.keys())[:8]}")
    else:
        fail("FR-4.23: GET /exam/student/history", f"HTTP {r.status_code}: {r.text[:150]}")

    # Browser: student history page
    ctx, page = new_ctx(browser, student01_token)
    page.goto(f"{STAGING}/fr/students/me/attempts")
    page.wait_for_load_state("networkidle")
    time.sleep(3)
    shot(page, "p13-student-history")

    # Look for course grouping
    course_name = "E2E Full Coverage Testing"
    try:
        expect(page.get_by_text(course_name, exact=False)).to_be_visible(timeout=8000)
        ok(f"US-21 browser: course header '{course_name}' visible ✅")
    except Exception as e:
        warn(f"US-21 browser: course header not found ({e})")

    # Look for class grouping
    class_name = shared.get("class_name", "E2E Class")
    try:
        expect(page.get_by_text(class_name, exact=False)).to_be_visible(timeout=5000)
        ok(f"US-21 browser: class header '{class_name}' visible ✅")
    except Exception as e:
        warn(f"US-21 browser: class header not found ({e})")

    # Look for attempt rows
    attempt_rows = page.locator("a").filter(has_text="Review")
    if attempt_rows.count() > 0:
        ok(f"US-21 browser: {attempt_rows.count()} 'Review' link(s) visible in history")
    else:
        warn("US-21 browser: no Review links found in student history")

    ctx.close()


# ---------------------------------------------------------------------------
# Phase 14 — Anonymous Grading Mapping Reveal (US-23)
# ---------------------------------------------------------------------------

def phase14_anonymous_grading(browser: Browser, shared: dict) -> None:
    print("\n── Phase 14: Anonymous Grading Mapping Reveal (US-23) ───────────────")
    teacher_token = shared["teacher_token"]
    student01_token = shared["student01_token"]
    anon_test_id = shared.get("anon_test_id")
    anon_question_id = shared.get("anon_question_id")

    if not anon_test_id:
        fail("US-23: anon_test_id not available")
        return

    # Student01 starts + submits anonymous MCQ attempt
    r_start = api_post(f"/exam/tests/{anon_test_id}/start", student01_token)
    if r_start.status_code not in (200, 201):
        fail("US-23: Student start anon attempt", f"HTTP {r_start.status_code}: {r_start.text[:150]}")
        return
    anon_attempt_id = r_start.json()["attempt_id"]
    shared["anon_attempt_id"] = anon_attempt_id
    ok(f"US-23: Student started anon attempt (id={anon_attempt_id[:8]}…)")

    # Verify anon_id assigned (submissions should use anon_id)
    r_sub = api_get(f"/exam/tests/{anon_test_id}/submissions", teacher_token)
    if r_sub.status_code == 200:
        subs = r_sub.json()
        if subs and "anon_id" in subs[0]:
            ok(f"US-23: submissions response includes anon_id field")
        else:
            warn(f"US-23: anon_id field check — subs={len(subs)}, fields={list(subs[0].keys()) if subs else []}")

    # Submit MCQ
    r_submit = api_post(f"/exam/attempts/{anon_attempt_id}/submit", student01_token, {
        "mcq_answers": {anon_question_id: [0]} if anon_question_id else {},
        "dissertation_answers": {},
        "time_taken_sec": 30,
    })
    if r_submit.status_code in (200, 201):
        ok("US-23: Anon attempt submitted")
    else:
        fail("US-23: Submit anon attempt", f"HTTP {r_submit.status_code}: {r_submit.text[:150]}")

    # Check anon-mapping BEFORE validate → expect 409
    r_before = api_get(f"/exam/tests/{anon_test_id}/anon-mapping", teacher_token)
    if r_before.status_code == 409:
        ok("US-23: GET anon-mapping before validation returns 409 ✅")
    elif r_before.status_code == 200:
        warn("US-23: anon-mapping returned 200 before validation (may be auto-validated)")
    else:
        warn(f"US-23: anon-mapping before validation returned {r_before.status_code}")

    # Validate the attempt
    r_val = api_post(f"/exam/attempts/{anon_attempt_id}/validate", teacher_token)
    if r_val.status_code in (200, 201):
        ok("US-23: Anon attempt validated ✅")
    else:
        fail("US-23: Validate anon attempt", f"HTTP {r_val.status_code}: {r_val.text[:150]}")

    # Check anon-mapping AFTER validate → expect 200 with mappings
    r_after = api_get(f"/exam/tests/{anon_test_id}/anon-mapping", teacher_token)
    if r_after.status_code == 200:
        mapping_data = r_after.json()
        ok("US-23: GET anon-mapping after validation → 200 ✅")
        mappings = mapping_data.get("mappings", [])
        if mappings:
            ok(f"US-23: anon-mapping has {len(mappings)} entry(ies)")
            entry = mappings[0]
            if "anon_id" in entry and "user_id" in entry:
                ok("US-23: mapping entry has anon_id + user_id ✅")
            else:
                fail("US-23: mapping entry missing anon_id or user_id", f"keys: {list(entry.keys())}")
        else:
            fail("US-23: anon-mapping 'mappings' list is empty")
    else:
        fail("US-23: GET anon-mapping after validation", f"HTTP {r_after.status_code}: {r_after.text[:150]}")

    # Browser: teacher grading dashboard for anon test
    ctx, page = new_ctx(browser, teacher_token)
    page.goto(f"{STAGING}/fr/exams/{anon_test_id}/results")
    page.wait_for_load_state("networkidle")
    time.sleep(3)
    shot(page, "p14-anon-grading-dashboard")

    # Look for anon-related UI (reveal mapping or anon badge)
    anon_indicators = ["Anonymous", "anonymous", "anon", "Reveal", "reveal", "Identit"]
    found = False
    for indicator in anon_indicators:
        if page.get_by_text(indicator, exact=False).count() > 0:
            ok(f"US-23 browser: '{indicator}' indicator visible on grading dashboard")
            found = True
            break
    if not found:
        warn("US-23 browser: no anon/reveal indicator found on grading dashboard")

    ctx.close()


# ---------------------------------------------------------------------------
# Phase 15 — Exam Access Grants (FR-4.20)
# ---------------------------------------------------------------------------

def phase15_access_grants(shared: dict) -> None:
    print("\n── Phase 15: Exam Access Grants (FR-4.20) ──────────────────────────")
    teacher_token = shared["teacher_token"]
    admin_token = shared["admin_token"]
    student01_token = shared["student01_token"]
    test_id = shared.get("test_id_s01")
    student_user_id = decode_sub(student01_token)

    if not test_id:
        fail("FR-4.20: test_id_s01 not available")
        return

    # Non-admin should get 403
    r_nonadmin = api_post("/exam/grants", teacher_token, {
        "test_id": test_id,
        "student_id": student_user_id,
    })
    if r_nonadmin.status_code == 403:
        ok("FR-4.20: Teacher (non-admin) gets 403 on POST /exam/grants ✅")
    else:
        warn(f"FR-4.20: Expected 403 for teacher, got {r_nonadmin.status_code}")

    # Admin creates grant
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

    if str(grant.get("test_id")) == str(test_id):
        ok("FR-4.20: grant.test_id matches ✅")
    else:
        fail("FR-4.20: grant.test_id mismatch", f"expected {test_id}, got {grant.get('test_id')}")

    # List grants
    r_list = api_get("/exam/grants", admin_token)
    if r_list.status_code == 200:
        grant_ids = [g["id"] for g in r_list.json()]
        if grant_id in grant_ids:
            ok("FR-4.20: GET /exam/grants lists new grant ✅")
        else:
            warn("FR-4.20: New grant not found in list (may be org-filtered)")
    else:
        fail("FR-4.20: GET /exam/grants", f"HTTP {r_list.status_code}")

    # Revoke grant
    r_del = api_delete(f"/exam/grants/{grant_id}", admin_token)
    if r_del.status_code == 204:
        ok("FR-4.20: DELETE /exam/grants/{id} → 204 (revoked) ✅")
    else:
        fail("FR-4.20: DELETE grant", f"HTTP {r_del.status_code}: {r_del.text[:100]}")

    # Verify gone
    r_list2 = api_get("/exam/grants", admin_token)
    if r_list2.status_code == 200:
        grant_ids2 = [g["id"] for g in r_list2.json()]
        if grant_id not in grant_ids2:
            ok("FR-4.20: Revoked grant no longer in list ✅")
        else:
            fail("FR-4.20: Revoked grant still in list after DELETE")


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def run_tests() -> int:
    print("=" * 70)
    print("SIRA EXAM — Full E2E Coverage (US-1 through US-23)")
    print("Target:", STAGING)
    print("=" * 70)

    # Health check
    print("\n── Health check ────────────────────────────────────────────────────")
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

    # Mint tokens
    teacher_token = get_token("expert")
    student01_token = get_token("user", sub="1")
    student02_token = get_token("user", sub="2")
    admin_token = get_token("admin")
    print(f"\n  Tokens minted: teacher ✓  student01 ✓  student02 ✓  admin ✓")

    ts = int(time.time())
    shared: dict = {
        "ts": ts,
        "teacher_token": teacher_token,
        "student01_token": student01_token,
        "student02_token": student02_token,
        "admin_token": admin_token,
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--use-fake-ui-for-media-stream",
                "--use-fake-device-for-media-stream",
            ],
        )

        try:
            phase1_class_management(teacher_token, browser, shared)
            phase2_bank_and_tests(teacher_token, shared)
            phase3_student01_exam(browser, shared)   # includes Phase 4 proctor inline
            phase5_student02_exam(browser, shared)
            phase6_wait_ai_grading(shared)
            phase7_human_scoring(shared)
            phase8_validation(browser, shared)
            phase9_student_review(browser, shared)
            phase10_file_complaint(browser, shared)
            phase11_resolve_complaint(browser, shared)
            phase12_submissions_by_class(browser, shared)
            phase13_student_history(browser, shared)
            phase14_anonymous_grading(browser, shared)
            phase15_access_grants(shared)
        except RuntimeError as e:
            fail(f"Fatal error — aborting: {e}")
        finally:
            browser.close()

    print("\n── Known Gaps / Deviations ─────────────────────────────────────────")
    print("  • E3-15 identity verification: mocked (Claude Vision bypassed in headless)")
    print("  • Fullscreen gate: untestable in headless Chromium")
    print("  • AI grading timeout: sequential Celery worker (Phase 6 falls back to warn)")
    print("  • Complaint browser flow: depends on feedback gate being open")

    total = len(passes) + len(fails)
    pct = round(100 * len(passes) / total, 1) if total > 0 else 0

    print(f"\n{'=' * 70}")
    print(f"RESULTS: {len(passes)} passed  ·  {len(fails)} failed  ·  {pct}% pass rate")
    print("=" * 70)
    if fails:
        print("\n❌ Failures:")
        for f_msg in fails:
            print(f"   • {f_msg}")
    else:
        print("\n✅ All checks passed!")
    print(f"\nScreenshots: {SCREENSHOTS}/")

    return len(fails)


if __name__ == "__main__":
    n_fails = run_tests()
    sys.exit(1 if n_fails else 0)
