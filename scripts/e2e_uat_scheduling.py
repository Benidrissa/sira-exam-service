#!/usr/bin/env python3
"""UAT browser validation — Exam Scheduling UI + Overlap Guard (PR #173).

Validates US-16 ACs and the overlap guard in headed Chromium against staging:
  1. "Schedule" button visible on teacher dashboard published bank card
  2. Assignments page loads — Assign button visible
  3. Create assignment (class1, w1) → row appears in list
  4. Overlapping window (class1, w2) → overlap guard error shown in UI
  5. Adjacent window (class2, w3) → row appears, no error
  6. Edit assignment — close-before-open client validation fires
  7. Delete assignment → removed, OR staging-data guard error shown

Design: the pre-flight creates two fresh UAT classes so every run starts
with a clean slate, avoiding conflicts from undeletable assignments left
by previous runs (backend blocks deletes when the test has submissions).

Usage: python3.10 scripts/e2e_uat_scheduling.py
Screenshots: /tmp/playwright-screenshots/uat-scheduling/
"""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timedelta, timezone

import requests
from playwright.sync_api import Page, sync_playwright

UTC = timezone.utc

STAGING = "https://sira-exam.elearning.portfolio2.kimbetien.com"
API = "https://sira-exam-api.elearning.portfolio2.kimbetien.com/api/v1"
SHOTS = "/tmp/playwright-screenshots/uat-scheduling"
_TIMEOUT = 20_000

os.makedirs(SHOTS, exist_ok=True)

passes: list[str] = []
fails: list[str] = []


def ok(msg: str) -> None:
    print(f"  ✅ {msg}")
    passes.append(msg)


def fail(msg: str, detail: str = "") -> None:
    full = msg + (f" — {detail}" if detail else "")
    print(f"  ❌ {full}")
    fails.append(full)


def warn(msg: str) -> None:
    print(f"  ⚠️  {msg}")


def shot(page: Page, name: str) -> None:
    path = f"{SHOTS}/{name}.png"
    try:
        page.screenshot(path=path, full_page=True)
        print(f"     \U0001f4f8 {path}")
    except Exception as exc:
        warn(f"screenshot failed: {exc}")


def get_token(role: str = "expert") -> str:
    r = requests.get(f"{API}/dev/tokens?role={role}", timeout=30)
    r.raise_for_status()
    return r.json()["access_token"]


def set_cookie(page: Page, token: str) -> None:
    page.context.add_cookies(
        [
            {
                "name": "access_token",
                "value": token,
                "domain": "sira-exam.elearning.portfolio2.kimbetien.com",
                "path": "/",
                "httpOnly": False,
                "secure": True,
                "sameSite": "Lax",
            }
        ]
    )


def auth_h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def dt_local(dt_utc: datetime) -> str:
    """UTC datetime -> datetime-local input string (YYYY-MM-DDTHH:MM)."""
    return dt_utc.astimezone().strftime("%Y-%m-%dT%H:%M")


def new_page(browser, token: str) -> tuple:
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    pg = ctx.new_page()
    pg.set_default_timeout(_TIMEOUT)
    set_cookie(pg, token)
    return ctx, pg


def cancel_open_form(page: Page) -> None:
    """Dismiss any open inline form, ignoring errors."""
    try:
        cancel = page.get_by_role("button", name="Cancel").first
        if cancel.is_visible():
            cancel.click()
            time.sleep(1)
    except Exception:
        pass


def create_class(headers: dict, name: str) -> dict:
    r = requests.post(
        f"{API}/exam/classes",
        headers=headers,
        json={"name": name, "academic_year": "2026-2027"},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def run() -> int:
    print("=" * 65)
    print("UAT PR #173 — Exam Scheduling UI + Overlap Guard")
    print(f"Target: {STAGING}")
    print("=" * 65)

    # Health check
    try:
        h = requests.get(f"{API.replace('/api/v1', '')}/health", timeout=30)
        h.raise_for_status()
        print(f"\n  \U0001f7e2 API health: {h.json()}")
    except Exception as exc:
        print(f"  \U0001f534 API health FAILED: {exc}")
        return 1

    teacher_token = get_token("expert")
    headers = auth_h(teacher_token)
    print("  Token minted: teacher ✓")

    # Resolve published bank + test
    banks = requests.get(f"{API}/exam/banks", headers=headers, timeout=30).json()
    published = [b for b in banks if b.get("status") == "published"]
    if not published:
        print("  \U0001f534 No published bank on staging — cannot run UAT")
        return 1
    bank = published[0]

    tests = requests.get(
        f"{API}/exam/banks/{bank['id']}/tests",
        headers=headers,
        timeout=30,
    ).json()
    if not tests:
        print(f"  \U0001f534 Bank '{bank['title_fr']}' has no tests")
        return 1
    test_id = tests[0]["id"]
    print(f"  Bank: {bank['title_fr']}  test_id: {test_id}")

    # Create two fresh UAT classes for this run — guaranteed no prior
    # assignments, so overlap guard and unique-constraint won't fire.
    ts = int(time.time())
    cls1 = create_class(headers, f"UAT-A {ts}")
    cls2 = create_class(headers, f"UAT-B {ts}")
    class1_id, class1_name = cls1["id"], cls1["name"]
    class2_id, class2_name = cls2["id"], cls2["name"]
    print(f"  Class1 (fresh): {class1_name}  id: {class1_id}")
    print(f"  Class2 (fresh): {class2_name}  id: {class2_id}")

    # Time windows
    now = datetime.now(UTC)
    w1_open = now - timedelta(minutes=5)
    w1_close = now + timedelta(hours=2)
    w2_open = now + timedelta(hours=1)  # overlaps w1 (same class)
    w2_close = now + timedelta(hours=3)
    w3_open = w1_close  # adjacent to w1 (diff class)
    w3_close = w1_close + timedelta(hours=2)

    assignments_url = f"{STAGING}/fr/exams/{test_id}/assignments"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=500, args=["--no-sandbox"])

        # ── SC-1: "Schedule" button on teacher dashboard ───────────────
        print("\n── 1. Teacher dashboard — Schedule button ────")
        ctx, page = new_page(browser, teacher_token)
        page.goto(f"{STAGING}/fr/")
        page.wait_for_load_state("networkidle")
        time.sleep(3)
        shot(page, "01-teacher-dashboard")

        try:
            schedule_link = page.get_by_role("link", name="Schedule").first
            schedule_link.wait_for(state="visible", timeout=10_000)
            ok("Schedule button visible on published bank card")
        except Exception as exc:
            fail("Schedule button not visible", str(exc)[:120])
        ctx.close()

        # ── SC-2: Assignments page — Assign button ─────────────────────
        print("\n── 2. Assignments page — Assign button visible ──")
        ctx, page = new_page(browser, teacher_token)
        page.goto(assignments_url)
        page.wait_for_load_state("networkidle")
        time.sleep(2)
        shot(page, "02-assignments-page")

        try:
            btn = page.get_by_role("button", name="Assign").first
            btn.wait_for(state="visible", timeout=10_000)
            ok("Assignments page loaded — Assign button visible")
        except Exception as exc:
            fail("Assignments page / Assign button not found", str(exc)[:120])

        # ── SC-3: Create class1 assignment (w1, Q1) ────────────────────
        print("\n── 3. Create assignment (class1, w1, Q1) ─────")
        try:
            cancel_open_form(page)
            page.get_by_role("button", name="Assign").first.click()
            time.sleep(1)

            page.locator("select").first.select_option(value=class1_id)
            dt_inputs = page.locator("input[type='datetime-local']")
            dt_inputs.nth(0).fill(dt_local(w1_open))
            dt_inputs.nth(1).fill(dt_local(w1_close))
            page.locator("select").nth(1).select_option(value="q1")

            shot(page, "03a-create-form-filled")
            page.get_by_role("button", name="Assign").last.click()
            page.wait_for_load_state("networkidle")
            time.sleep(2)
            shot(page, "03b-after-create")

            # The class name appears as row text after form closes
            page.get_by_role("listitem").filter(has_text=class1_name).first.wait_for(
                state="visible", timeout=8_000
            )
            ok(f"Assignment created — '{class1_name}' row visible")
        except Exception as exc:
            fail("Create assignment failed", str(exc)[:200])

        # ── SC-4: Overlapping window → overlap guard error ─────────────
        print("\n── 4. Overlapping window → overlap guard error in UI ─")
        try:
            cancel_open_form(page)
            page.get_by_role("button", name="Assign").first.click()
            time.sleep(1)

            page.locator("select").first.select_option(value=class1_id)
            dt_inputs = page.locator("input[type='datetime-local']")
            dt_inputs.nth(0).fill(dt_local(w2_open))
            dt_inputs.nth(1).fill(dt_local(w2_close))
            page.locator("select").nth(1).select_option(value="q2")

            page.get_by_role("button", name="Assign").last.click()
            time.sleep(2)
            shot(page, "04-overlap-error")

            alert = page.locator("[role='alert']").first
            alert.wait_for(state="visible", timeout=8_000)
            msg = alert.inner_text()
            ok(f"Overlap guard triggered — error: '{msg[:80]}'")
        except Exception as exc:
            fail("Overlap guard error not shown in UI", str(exc)[:200])

        cancel_open_form(page)

        # ── SC-5: Adjacent window (class2) → success ───────────────────
        print("\n── 5. Adjacent window (class2, w3) → success ───")
        try:
            cancel_open_form(page)
            page.get_by_role("button", name="Assign").first.click()
            time.sleep(1)

            # class2 has no prior assignments — no overlap, no unique conflict
            page.locator("select").first.select_option(value=class2_id)
            dt_inputs = page.locator("input[type='datetime-local']")
            dt_inputs.nth(0).fill(dt_local(w3_open))
            dt_inputs.nth(1).fill(dt_local(w3_close))
            page.locator("select").nth(1).select_option(value="q2")

            page.get_by_role("button", name="Assign").last.click()
            page.wait_for_load_state("networkidle")
            time.sleep(2)
            shot(page, "05-adjacent-created")

            # Verify class2 row appeared; an error would keep the form open
            page.get_by_role("listitem").filter(has_text=class2_name).first.wait_for(
                state="visible", timeout=6_000
            )
            ok(f"Adjacent assignment (class2) accepted — '{class2_name}' row visible")
        except Exception as exc:
            # Distinguish rejection from timeout
            err_alerts = [
                a
                for a in page.locator("[role='alert']").all()
                if a.inner_text().strip()
            ]
            detail = err_alerts[0].inner_text()[:120] if err_alerts else str(exc)[:200]
            fail("Adjacent assignment unexpectedly rejected", detail)

        # ── SC-6: Edit — close-before-open client validation ───────────
        print("\n── 6. Edit assignment — close-before-open validation ──")
        try:
            cancel_open_form(page)
            # Find class1's row and click its pencil button
            row = page.get_by_role("listitem").filter(has_text=class1_name).first
            edit_btn = row.locator("button").nth(-2)
            edit_btn.click()
            time.sleep(1)
            shot(page, "06a-edit-open")

            # Set closes_at equal to opens_at -> client rejects
            opens_val = (
                page.locator("input[type='datetime-local']").nth(0).input_value()
            )
            page.locator("input[type='datetime-local']").nth(1).fill(opens_val)

            page.get_by_role("button", name="Save").click()
            time.sleep(1)
            shot(page, "06b-edit-validation-error")

            err_p = page.locator("p.text-destructive").first
            err_p.wait_for(state="visible", timeout=6_000)
            ok(f"Edit validation error shown: '{err_p.inner_text()[:80]}'")
        except Exception as exc:
            fail("Edit validation error not shown", str(exc)[:200])

        cancel_open_form(page)

        # ── SC-7: Delete assignment ────────────────────────────────────
        print("\n── 7. Delete assignment ──────────────")
        try:
            cancel_open_form(page)
            row = page.get_by_role("listitem").filter(has_text=class1_name).first
            rows_before = page.locator("ul > li").count()
            delete_btn = row.locator("button").last
            delete_btn.click()
            time.sleep(2)
            page.wait_for_load_state("networkidle")
            shot(page, "07-after-delete")

            rows_after = page.locator("ul > li").count()
            if rows_after < rows_before:
                ok(f"Assignment deleted (rows {rows_before} → {rows_after})")
            else:
                # Backend blocks delete when test has student submissions.
                # Check that a meaningful inline error appeared.
                delete_err = page.locator("p.text-destructive").first
                if delete_err.is_visible():
                    err_txt = delete_err.inner_text()
                    if "Cannot delete" in err_txt or "students" in err_txt:
                        ok(
                            "Delete correctly blocked by backend guard "
                            f"(staging data): '{err_txt[:80]}'"
                        )
                    else:
                        fail("Delete blocked with unexpected error", err_txt[:120])
                else:
                    fail(
                        "Delete did not remove row and showed no error",
                        f"before={rows_before} after={rows_after}",
                    )
        except Exception as exc:
            fail("Delete assignment failed", str(exc)[:200])

        shot(page, "08-final-state")
        ctx.close()
        browser.close()

    print(f"\n{'=' * 65}")
    print(f"RESULTS: {len(passes)} passed  ·  {len(fails)} failed")
    print("=" * 65)
    if fails:
        print("\n❌ Failures:")
        for msg in fails:
            print(f"   • {msg}")
    else:
        print("\n✅ All scheduling UAT checks passed!")
    print(f"\nScreenshots: {SHOTS}/")
    return len(fails)


if __name__ == "__main__":
    sys.exit(1 if run() else 0)
