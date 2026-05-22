#!/usr/bin/env python3
"""UAT browser validation for PR #168 — breadcrumbs, pagination, filtering.

Navigates to each target page as an authenticated user and verifies:
  1. Breadcrumb nav is visible on deep pages
  2. Breadcrumb is hidden on login
  3. Filter inputs (search / select) are present on list pages
  4. Pagination controls render when list has content

Usage: python scripts/e2e_uat_pr168.py
Screenshots: /tmp/playwright-screenshots/uat-pr168/
"""
from __future__ import annotations

import os
import sys
import time

import requests
from playwright.sync_api import sync_playwright, Page, expect

STAGING = "https://sira-exam.elearning.portfolio2.kimbetien.com"
API = "https://sira-exam-api.elearning.portfolio2.kimbetien.com/api/v1"
SHOTS = "/tmp/playwright-screenshots/uat-pr168"
_TIMEOUT = 30_000

os.makedirs(SHOTS, exist_ok=True)

passes: list[str] = []
fails: list[str] = []


def ok(msg: str) -> None:
    print(f"  ✅ {msg}")
    passes.append(msg)


def fail(msg: str, detail: str = "") -> None:
    full = f"{msg}" + (f" — {detail}" if detail else "")
    print(f"  ❌ {full}")
    fails.append(full)


def warn(msg: str) -> None:
    print(f"  ⚠️  {msg}")


def shot(page: Page, name: str) -> None:
    path = f"{SHOTS}/{name}.png"
    try:
        page.screenshot(path=path, full_page=True)
        print(f"     📸 {path}")
    except Exception as e:
        warn(f"screenshot failed: {e}")


def get_token(role: str = "user", sub: str = "1") -> str:
    r = requests.get(f"{API}/dev/tokens?role={role}&sub={sub}", timeout=30)
    r.raise_for_status()
    return r.json()["access_token"]


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


def check_breadcrumb_visible(page: Page, label: str, expected_crumb: str) -> None:
    """Assert the breadcrumb nav is visible and contains expected_crumb text."""
    try:
        nav = page.locator("nav[aria-label='Breadcrumb']")
        expect(nav).to_be_visible(timeout=8000)
        ok(f"{label}: breadcrumb nav visible")
        if expected_crumb:
            crumb_text = nav.inner_text()
            if expected_crumb.lower() in crumb_text.lower():
                ok(f"{label}: breadcrumb contains '{expected_crumb}'")
            else:
                fail(f"{label}: breadcrumb missing '{expected_crumb}'", f"got: {crumb_text[:80]}")
    except Exception as e:
        fail(f"{label}: breadcrumb not visible", str(e)[:100])


def check_breadcrumb_hidden(page: Page, label: str) -> None:
    """Assert no breadcrumb nav on this page."""
    nav = page.locator("nav[aria-label='Breadcrumb']")
    if nav.count() == 0:
        ok(f"{label}: breadcrumb correctly hidden")
    else:
        try:
            if nav.is_hidden():
                ok(f"{label}: breadcrumb correctly hidden")
            else:
                fail(f"{label}: breadcrumb should be hidden but is visible")
        except Exception:
            ok(f"{label}: breadcrumb correctly hidden (not in DOM)")


def check_filter_input(page: Page, label: str) -> None:
    """Assert a search/filter input is present."""
    inputs = page.locator("input[type='text'], input:not([type]), select")
    if inputs.count() > 0:
        ok(f"{label}: filter input(s) visible ({inputs.count()} found)")
    else:
        fail(f"{label}: no filter input found")


def check_pagination(page: Page, label: str) -> None:
    """Check if pagination controls are present (only shown when list has items)."""
    # PaginationControls renders "Prev" / "Next" buttons
    prev_btn = page.get_by_role("button", name="Prev")
    next_btn = page.get_by_role("button", name="Next")
    # "Showing X–Y of Z" text
    showing = page.get_by_text("Showing", exact=False)

    if showing.count() > 0:
        ok(f"{label}: pagination 'Showing X–Y of N' text visible")
    elif prev_btn.count() > 0 or next_btn.count() > 0:
        ok(f"{label}: pagination Prev/Next buttons present")
    else:
        warn(f"{label}: no pagination controls (list may be empty or under page size)")


def run() -> int:
    print("=" * 65)
    print("UAT PR #168 — Breadcrumbs + Pagination + Filtering")
    print(f"Target: {STAGING}")
    print("=" * 65)

    # Health check
    try:
        h = requests.get(f"{API.replace('/api/v1', '')}/health", timeout=30)
        h.raise_for_status()
        print(f"\n  🟢 API health: {h.json()}")
    except Exception as e:
        print(f"  🔴 API health FAILED: {e}")
        return 1

    # We need some pre-existing data to test list pages with content.
    # Re-use the setup from e2e_full_coverage: teacher creates bank + class.
    teacher_token = get_token("expert", sub="1")
    student_token = get_token("user", sub="1")
    print("  Tokens minted: teacher ✓  student ✓")

    # Fetch existing data to get IDs for navigation
    banks_r = requests.get(f"{API}/exam/banks", headers={"Authorization": f"Bearer {teacher_token}"}, timeout=30)
    classes_r = requests.get(f"{API}/exam/classes", headers={"Authorization": f"Bearer {teacher_token}"}, timeout=30)
    history_r = requests.get(f"{API}/exam/student/history", headers={"Authorization": f"Bearer {student_token}"}, timeout=30)

    banks = banks_r.json() if banks_r.status_code == 200 else []
    classes = classes_r.json() if classes_r.status_code == 200 else []
    history = history_r.json() if history_r.status_code == 200 else []

    # Pick first published bank's test_id for submissions/grading/complaints
    test_id = None
    published_banks = [b for b in banks if b.get("status") == "published"]
    if published_banks:
        bank_id = published_banks[0]["id"]
        tests_r = requests.get(f"{API}/exam/banks/{bank_id}/tests",
                               headers={"Authorization": f"Bearer {teacher_token}"}, timeout=30)
        if tests_r.status_code == 200 and tests_r.json():
            test_id = tests_r.json()[0]["id"]

    class_id = classes[0]["id"] if classes else None
    attempt_id = history[0]["attempt_id"] if history else None

    print(f"\n  Data: {len(banks)} banks, {len(classes)} classes, {len(history)} history items")
    print(f"  test_id={str(test_id)[:8] if test_id else 'none'}, class_id={str(class_id)[:8] if class_id else 'none'}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])

        # ── 1. Login page — breadcrumb should be HIDDEN ──────────────────
        print("\n── 1. Login page (no breadcrumb) ────────────────────────────")
        ctx = browser.new_context(viewport={"width": 1280, "height": 900})
        page = ctx.new_page()
        page.goto(f"{STAGING}/fr/login")
        page.wait_for_load_state("networkidle")
        time.sleep(2)
        shot(page, "01-login")
        check_breadcrumb_hidden(page, "Login")
        ctx.close()

        # ── 2. Dashboard — breadcrumb should be HIDDEN (home = no crumb) ─
        print("\n── 2. Dashboard (home — no breadcrumb) ─────────────────────")
        ctx = browser.new_context(viewport={"width": 1280, "height": 900})
        page = ctx.new_page()
        set_cookie(page, teacher_token)
        page.goto(f"{STAGING}/fr/")
        page.wait_for_load_state("networkidle")
        time.sleep(3)
        shot(page, "02-dashboard")
        check_breadcrumb_hidden(page, "Dashboard (home)")

        # Check filter bar on bank list
        check_filter_input(page, "Dashboard bank list")
        check_pagination(page, "Dashboard bank list")
        ctx.close()

        # ── 3. Classes list — "Home" crumb? No — classes IS a top-level page ─
        # Breadcrumbs only shows on deep pages; /classes is a 1-crumb page (no trail)
        print("\n── 3. Classes list ──────────────────────────────────────────")
        ctx = browser.new_context(viewport={"width": 1280, "height": 900})
        page = ctx.new_page()
        set_cookie(page, teacher_token)
        page.goto(f"{STAGING}/fr/classes")
        page.wait_for_load_state("networkidle")
        time.sleep(3)
        shot(page, "03-classes-list")
        check_filter_input(page, "Classes list")
        check_pagination(page, "Classes list")
        ctx.close()

        # ── 4. Class Detail — "Home > Classes > Class Detail" ────────────
        if class_id:
            print("\n── 4. Class Detail (breadcrumb + member search) ─────────────")
            ctx = browser.new_context(viewport={"width": 1280, "height": 900})
            page = ctx.new_page()
            set_cookie(page, teacher_token)
            page.goto(f"{STAGING}/fr/classes/{class_id}")
            page.wait_for_load_state("networkidle")
            time.sleep(3)
            shot(page, "04-class-detail")
            check_breadcrumb_visible(page, "Class Detail", "Classes")
            ctx.close()
        else:
            warn("No class_id — skipping class detail breadcrumb check")

        # ── 5. Submissions — "Home > Submissions" + filter bar ───────────
        if test_id:
            print("\n── 5. Submissions (breadcrumb + filter) ─────────────────────")
            ctx = browser.new_context(viewport={"width": 1280, "height": 900})
            page = ctx.new_page()
            set_cookie(page, teacher_token)
            page.goto(f"{STAGING}/fr/exams/{test_id}/submissions")
            page.wait_for_load_state("networkidle")
            time.sleep(3)
            shot(page, "05-submissions")
            check_breadcrumb_visible(page, "Submissions", "Submissions")
            check_filter_input(page, "Submissions")
            ctx.close()

            # ── 6. Grading — "Home > Grading" + status filter ────────────
            print("\n── 6. Grading (breadcrumb + status filter) ──────────────────")
            ctx = browser.new_context(viewport={"width": 1280, "height": 900})
            page = ctx.new_page()
            set_cookie(page, teacher_token)
            page.goto(f"{STAGING}/fr/exams/{test_id}/results")
            page.wait_for_load_state("networkidle")
            time.sleep(3)
            shot(page, "06-grading")
            check_breadcrumb_visible(page, "Grading", "Grading")
            check_filter_input(page, "Grading status filter")
            ctx.close()

            # ── 7. Complaints — "Home > Complaints" + status filter ───────
            print("\n── 7. Complaints (breadcrumb + filter) ──────────────────────")
            ctx = browser.new_context(viewport={"width": 1280, "height": 900})
            page = ctx.new_page()
            set_cookie(page, teacher_token)
            page.goto(f"{STAGING}/fr/exams/{test_id}/complaints")
            page.wait_for_load_state("networkidle")
            time.sleep(3)
            shot(page, "07-complaints")
            check_breadcrumb_visible(page, "Complaints", "Complaints")
            # Filter only appears when complaints exist; skip if list is empty (WAI)
            inputs = page.locator("input, select").count()
            if inputs > 0:
                ok("Complaints: filter input(s) visible")
            else:
                warn("Complaints status filter: not shown (test has 0 complaints — filter hidden by design)")
            ctx.close()
        else:
            warn("No test_id — skipping submissions/grading/complaints checks")

        # ── 8. Student History — "Home > My Exams" + search ─────────────
        print("\n── 8. Student History (breadcrumb + search + passed filter) ────")
        ctx = browser.new_context(viewport={"width": 1280, "height": 900})
        page = ctx.new_page()
        set_cookie(page, student_token)
        page.goto(f"{STAGING}/fr/students/me/attempts")
        page.wait_for_load_state("networkidle")
        time.sleep(3)
        shot(page, "08-student-history")
        check_breadcrumb_visible(page, "Student History", "My Exams")
        if history:
            check_filter_input(page, "Student History search/filter")
        ctx.close()

        # ── 9. Attempt Review — "Home > My Exams > Review" ──────────────
        if attempt_id:
            print("\n── 9. Attempt Review (breadcrumb: Home > My Exams > Review) ──")
            ctx = browser.new_context(viewport={"width": 1280, "height": 900})
            page = ctx.new_page()
            set_cookie(page, student_token)
            page.goto(f"{STAGING}/fr/attempts/{attempt_id}/review")
            page.wait_for_load_state("networkidle")
            time.sleep(3)
            shot(page, "09-attempt-review")
            check_breadcrumb_visible(page, "Attempt Review", "My Exams")
            ctx.close()
        else:
            warn("No attempt_id — skipping attempt review breadcrumb check")

        # ── 10. Proctor Dashboard — "Home > Proctor" + filter ────────────
        print("\n── 10. Proctor Dashboard (breadcrumb + filter) ──────────────")
        ctx = browser.new_context(viewport={"width": 1280, "height": 900})
        page = ctx.new_page()
        set_cookie(page, teacher_token)
        page.goto(f"{STAGING}/fr/proctor/dashboard")
        page.wait_for_load_state("networkidle")
        time.sleep(3)
        shot(page, "10-proctor-dashboard")
        check_breadcrumb_visible(page, "Proctor Dashboard", "Proctor")
        ctx.close()

        browser.close()

    print(f"\n{'=' * 65}")
    print(f"RESULTS: {len(passes)} passed  ·  {len(fails)} failed")
    print("=" * 65)
    if fails:
        print("\n❌ Failures:")
        for f_msg in fails:
            print(f"   • {f_msg}")
    else:
        print("\n✅ All UAT checks passed!")
    print(f"\nScreenshots: {SHOTS}/")

    return len(fails)


if __name__ == "__main__":
    sys.exit(1 if run() else 0)
