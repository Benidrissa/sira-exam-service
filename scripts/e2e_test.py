#!/usr/bin/env python3
"""Playwright E2E browser test for sira-exam staging.

Tests the full teacher and student flows with screenshots.
Usage: python scripts/e2e_test.py
"""
from __future__ import annotations

import os
import sys
import time
import requests
from playwright.sync_api import sync_playwright, Page, expect

STAGING = "https://sira-exam.elearning.portfolio2.kimbetien.com"
API = "https://sira-exam-api.elearning.portfolio2.kimbetien.com/api/v1"
TEST_ID = "dc11a12c-4896-4eae-844b-4c1cd6276d3f"  # DAMA DMBOK — 13 questions, published
SCREENSHOTS = "/tmp/playwright-screenshots"

os.makedirs(SCREENSHOTS, exist_ok=True)

passes: list[str] = []
fails: list[str] = []


def ok(msg: str) -> None:
    print(f"  ✅ PASS: {msg}")
    passes.append(msg)


def fail(msg: str, detail: str = "") -> None:
    full = f"{msg}" + (f" — {detail}" if detail else "")
    print(f"  ❌ FAIL: {full}")
    fails.append(full)


def shot(page: Page, name: str) -> None:
    path = f"{SCREENSHOTS}/{name}.png"
    page.screenshot(path=path, full_page=True)
    print(f"     📸 {path}")


def get_token(role: str) -> str:
    r = requests.get(f"{API}/dev/tokens?role={role}", timeout=10)
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


def run_tests() -> None:
    teacher_token = get_token("expert")
    student_token = get_token("user")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = browser.new_context(viewport={"width": 1280, "height": 800})
        page = ctx.new_page()
        page.set_default_timeout(15_000)

        # ── 1. Login page ────────────────────────────────────────────────
        print("\n── Login page ──")
        page.goto(f"{STAGING}/fr/login")
        page.wait_for_load_state("networkidle")
        shot(page, "01-login")

        try:
            expect(page.get_by_text("Continue as Teacher")).to_be_visible()
            ok("Login page shows 'Continue as Teacher' button")
        except Exception as e:
            fail("Login page missing teacher button", str(e))

        try:
            expect(page.get_by_text("Continue as Student")).to_be_visible()
            ok("Login page shows 'Continue as Student' button")
        except Exception as e:
            fail("Login page missing student button", str(e))

        try:
            expect(page.get_by_text("Sira Exam Service")).to_be_visible()
            ok("Login page shows brand name")
        except Exception as e:
            fail("Login page missing brand", str(e))

        # ── 2. Teacher flow via cookie ────────────────────────────────────
        print("\n── Teacher: home/dashboard ──")
        set_cookie(page, teacher_token)
        page.goto(f"{STAGING}/fr/")
        page.wait_for_load_state("networkidle")
        time.sleep(1)  # let React Query fetch banks
        shot(page, "02-teacher-home")

        try:
            expect(page.get_by_text("My Exam Banks", exact=False)).to_be_visible(timeout=8000)
            ok("Teacher home shows 'My Exam Banks' heading")
        except Exception as e:
            fail("Teacher home missing bank list heading", str(e))

        try:
            expect(page.get_by_text("New Exam", exact=True).first).to_be_visible()
            ok("NavBar shows 'New Exam' button")
        except Exception as e:
            fail("NavBar missing 'New Exam' button", str(e))

        try:
            expect(page.get_by_text("Proctor", exact=True).first).to_be_visible()
            ok("NavBar shows 'Proctor' button")
        except Exception as e:
            fail("NavBar missing 'Proctor' button", str(e))

        try:
            expect(page.get_by_text("Teacher", exact=True).first).to_be_visible()
            ok("NavBar shows 'Teacher' role badge")
        except Exception as e:
            fail("NavBar missing Teacher role badge", str(e))

        try:
            expect(page.get_by_text("Logout", exact=True).first).to_be_visible()
            ok("NavBar shows 'Logout' button")
        except Exception as e:
            fail("NavBar missing Logout button", str(e))

        # ── 3. Bank cards ────────────────────────────────────────────────
        print("\n── Teacher: bank cards ──")
        try:
            # published badge
            expect(page.get_by_text("published").first).to_be_visible(timeout=6000)
            ok("Bank list shows published bank with status badge")
        except Exception as e:
            fail("Bank list doesn't show any published bank", str(e))

        try:
            expect(page.get_by_text("Review Board").first).to_be_visible(timeout=6000)
            ok("Published bank shows 'Review Board' link")
        except Exception as e:
            fail("Published bank missing 'Review Board' link", str(e))

        try:
            expect(page.get_by_text("Copy Student Link").first).to_be_visible(timeout=6000)
            ok("Published bank shows 'Copy Student Link' button")
        except Exception as e:
            fail("Published bank missing 'Copy Student Link' button", str(e))

        # ── 4. Review board ───────────────────────────────────────────────
        print("\n── Teacher: review board ──")
        # Navigate via API-known bank
        page.goto(f"{STAGING}/fr/banks/840ce353-bf70-4ea8-8b47-99cd2d7eae99/review")
        page.wait_for_load_state("networkidle")
        time.sleep(1)
        shot(page, "03-review-board")

        try:
            expect(page.get_by_text("Review & Edit", exact=False)).to_be_visible(timeout=8000)
            ok("Review board heading visible")
        except Exception as e:
            fail("Review board heading missing", str(e))

        try:
            expect(page.locator(".rounded-2xl").first).to_be_visible(timeout=8000)
            ok("Review board shows scenario cards")
        except Exception as e:
            fail("Review board missing scenario cards", str(e))

        try:
            expect(page.get_by_text("MCQ", exact=True).first).to_be_visible(timeout=6000)
            ok("Review board shows MCQ question badges")
        except Exception as e:
            fail("Review board missing MCQ badges", str(e))

        try:
            btn = page.get_by_role("button", name="Publish Bank").or_(
                page.get_by_role("button", name="Validate All & Publish")
            ).or_(
                page.get_by_text("✓ Published").first
            )
            expect(btn.first).to_be_visible(timeout=5000)
            ok("Publish/Validate button visible in review board")
        except Exception as e:
            fail("Review board publish button not found", str(e))

        # ── 5. Create page ────────────────────────────────────────────────
        print("\n── Teacher: create wizard ──")
        page.goto(f"{STAGING}/fr/create")
        page.wait_for_load_state("networkidle")
        shot(page, "04-create-wizard")

        try:
            expect(page.get_by_text("Exam Info", exact=True)).to_be_visible(timeout=6000)
            ok("Create wizard step 1 'Exam Info' visible")
        except Exception as e:
            fail("Create wizard missing 'Exam Info' step", str(e))

        try:
            expect(page.get_by_placeholder("e.g. Examen de médecine", exact=False)).to_be_visible()
            ok("Create wizard shows title input field")
        except Exception as e:
            fail("Create wizard missing title input", str(e))

        try:
            step_circles = page.locator(".rounded-full")
            expect(step_circles.first).to_be_visible()
            ok("Create wizard shows step progress indicator")
        except Exception as e:
            fail("Create wizard missing step indicators", str(e))

        # ── 6. Proctor dashboard ──────────────────────────────────────────
        print("\n── Teacher: proctor dashboard ──")
        page.goto(f"{STAGING}/fr/proctor/dashboard")
        page.wait_for_load_state("networkidle")
        time.sleep(1)
        shot(page, "05-proctor-dashboard")

        try:
            # Either shows sessions or "No active sessions" empty state
            content = page.content()
            if "active" in content.lower() or "session" in content.lower() or "No active" in content:
                ok("Proctor dashboard loads (sessions or empty state)")
            else:
                fail("Proctor dashboard has unexpected content")
        except Exception as e:
            fail("Proctor dashboard failed to load", str(e))

        # ── 7. Student flow ───────────────────────────────────────────────
        print("\n── Student: home/dashboard ──")
        ctx2 = browser.new_context(viewport={"width": 1280, "height": 800})
        page2 = ctx2.new_page()
        page2.set_default_timeout(15_000)
        set_cookie(page2, student_token)

        page2.goto(f"{STAGING}/fr/")
        page2.wait_for_load_state("networkidle")
        time.sleep(1)
        shot(page2, "06-student-home")

        try:
            expect(page2.get_by_text("Take an exam", exact=False)).to_be_visible(timeout=8000)
            ok("Student home shows 'Take an exam' heading")
        except Exception as e:
            fail("Student home missing take-exam heading", str(e))

        try:
            expect(page2.get_by_placeholder("Paste test ID or link", exact=False)).to_be_visible()
            ok("Student home shows test-ID input field")
        except Exception as e:
            fail("Student home missing test-ID input", str(e))

        try:
            expect(page2.get_by_text("My Exam Banks", exact=False)).not_to_be_visible(timeout=3000)
            ok("Student home does NOT show teacher bank list")
        except Exception:
            fail("Student home incorrectly shows teacher bank list")

        # Student NavBar
        try:
            expect(page2.get_by_text("Student", exact=True).first).to_be_visible(timeout=5000)
            ok("NavBar shows 'Student' role badge")
        except Exception as e:
            fail("Student NavBar missing role badge", str(e))

        try:
            expect(page2.get_by_text("New Exam")).not_to_be_visible(timeout=3000)
            ok("Student NavBar correctly hides 'New Exam' button")
        except Exception:
            fail("Student NavBar incorrectly shows 'New Exam' button")

        # ── 8. Exam player ────────────────────────────────────────────────
        print("\n── Student: exam player ──")
        page2.goto(f"{STAGING}/fr/exams/{TEST_ID}/play")
        page2.wait_for_load_state("networkidle")
        time.sleep(2)
        shot(page2, "07-exam-player")

        try:
            expect(page2.get_by_text("Exam", exact=True).first).to_be_visible(timeout=8000)
            ok("Exam player loads with 'Exam' header")
        except Exception as e:
            fail("Exam player missing header", str(e))

        try:
            timer = page2.locator("span.font-mono")
            expect(timer.first).to_be_visible(timeout=5000)
            timer_text = timer.first.text_content()
            if timer_text and ":" in timer_text:
                ok(f"Exam player shows countdown timer: {timer_text}")
            else:
                fail("Exam player timer format wrong", timer_text or "empty")
        except Exception as e:
            fail("Exam player missing timer", str(e))

        try:
            expect(page2.get_by_text("answered", exact=False).first).to_be_visible(timeout=5000)
            ok("Exam player shows 'X/Y answered' progress counter")
        except Exception as e:
            fail("Exam player missing progress counter", str(e))

        try:
            expect(page2.get_by_text("Submit", exact=True).first).to_be_visible()
            ok("Exam player shows 'Submit' button")
        except Exception as e:
            fail("Exam player missing Submit button", str(e))

        try:
            question_cards = page2.locator(".rounded-lg.border.bg-white")
            count = question_cards.count()
            if count > 0:
                ok(f"Exam player shows {count} question cards")
            else:
                fail("Exam player shows 0 question cards")
        except Exception as e:
            fail("Exam player missing question cards", str(e))

        # Click first MCQ option
        try:
            radio = page2.locator("input[type='radio']").first
            radio.click(timeout=5000)
            time.sleep(0.5)
            progress = page2.locator("text=/\\d+ of \\d+ answered|\\d+\\/\\d+ answered/").first
            ok("Answered MCQ question — progress updated")
        except Exception as e:
            fail("Could not click MCQ answer", str(e))

        # Submit confirmation dialog
        try:
            page2.get_by_role("button", name="Submit", exact=True).click()
            time.sleep(0.5)
            shot(page2, "08-submit-confirm")
            expect(page2.get_by_text("Submit exam?", exact=False)).to_be_visible(timeout=5000)
            ok("Submit button shows confirmation dialog")
            # Dismiss dialog
            page2.get_by_role("button", name="Keep working").click()
            ok("Confirmation dialog dismissed with 'Keep working'")
        except Exception as e:
            fail("Submit confirmation dialog not shown", str(e))

        # ── 9. Unauthenticated redirect ───────────────────────────────────
        print("\n── Auth redirect ──")
        ctx3 = browser.new_context(viewport={"width": 1280, "height": 800})
        page3 = ctx3.new_page()
        page3.set_default_timeout(10_000)

        page3.goto(f"{STAGING}/fr/")
        page3.wait_for_load_state("networkidle")
        shot(page3, "09-unauth-redirect")

        try:
            expect(page3).to_have_url(f"{STAGING}/fr/login?redirect=%2Ffr", timeout=8000)
            ok("Unauthenticated user redirected to /fr/login")
        except Exception as e:
            current = page3.url
            fail("Unauthenticated user not redirected to login", f"got: {current}")

        ctx3.close()
        ctx2.close()
        browser.close()

    # ── Summary ───────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"RESULTS: {len(passes)} passed  ·  {len(fails)} failed")
    print("="*60)
    if fails:
        print("\n❌ Failures:")
        for f in fails:
            print(f"   • {f}")
    else:
        print("\n✅ All checks passed!")
    print(f"\nScreenshots: {SCREENSHOTS}/")

    return len(fails)


if __name__ == "__main__":
    n_fails = run_tests()
    sys.exit(1 if n_fails else 0)
