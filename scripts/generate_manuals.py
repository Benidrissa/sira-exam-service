#!/usr/bin/env python3
"""Generate role-gated self-contained HTML user manuals for Sira Exam Service.

Usage:
    python scripts/generate_manuals.py
    python scripts/generate_manuals.py --base-url http://localhost:3001 \\
                                        --api-url  http://localhost:8001/api/v1 \\
                                        --output-dir docs/manuals
    python scripts/generate_manuals.py --skip-demo  # reuse existing data

Requires:
    pip install requests playwright
    playwright install chromium

Outputs:
    docs/manuals/teacher-manual.html  (roles: expert, admin, sub_admin)
    docs/manuals/student-manual.html  (role: user)
    docs/manuals/admin-manual.html    (roles: admin, sub_admin)
"""
from __future__ import annotations

import argparse
import base64
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).parent.parent
PDF_PATH = ROOT / "docs" / "Physics-WEB_Sab7RrQ-min.pdf"
FALLBACK_PDF = ROOT / "docs" / "DAMA DMBOK 2nd Edition.pdf"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Generate Sira Exam user manuals")
    p.add_argument("--base-url",    default="http://localhost:3001",      help="Frontend base URL")
    p.add_argument("--api-url",     default="http://localhost:8001/api/v1", help="Backend API base URL")
    p.add_argument("--output-dir",  default=str(ROOT / "frontend" / "public" / "manuals"), help="Output directory")
    p.add_argument("--skip-demo",   action="store_true", help="Skip demo data creation")
    p.add_argument("--bank-id",     default=None, help="Existing bank ID (with --skip-demo)")
    p.add_argument("--test-id",     default=None, help="Existing test ID (with --skip-demo)")
    p.add_argument("--session-id",  default=None, help="Existing session ID (with --skip-demo)")
    return p.parse_args()


# ---------------------------------------------------------------------------
# Availability check
# ---------------------------------------------------------------------------

def _api_alive(api_url: str) -> bool:
    try:
        r = requests.get(f"{api_url}/dev/tokens?role=expert", timeout=5)
        return r.status_code == 200
    except Exception:
        return False


def _frontend_alive(base_url: str) -> bool:
    try:
        r = requests.get(base_url, timeout=5)
        return r.status_code < 500
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Demo data setup
# ---------------------------------------------------------------------------

class DemoData:
    teacher_token: str = ""
    student_token: str = ""
    admin_token:   str = ""
    bank_id:       str = ""
    test_id:       str = ""
    session_id:    str = ""
    session_token: str = ""
    attempt_id:    str = ""

    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)

    @staticmethod
    def _h(token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}

    @classmethod
    def setup(cls, api_url: str) -> "DemoData":
        d = cls()
        print("\n[demo]  Setting up demo data ...")

        # Tokens
        for role, attr in [("expert", "teacher_token"), ("user", "student_token"), ("admin", "admin_token")]:
            r = requests.get(f"{api_url}/dev/tokens?role={role}", timeout=10)
            r.raise_for_status()
            setattr(d, attr, r.json()["access_token"])
            print(f"[demo]  ✓ {attr} ({role})")

        # Exam bank (direct questions — no AI generation for speed)
        ts = int(time.time())
        r = requests.post(f"{api_url}/exam/banks", json={
            "title_fr": f"Manuel de démonstration — Physique {ts}",
            "title_en": f"Demo Manual — Physics {ts}",
            "subject": "Physics",
            "language": "fr",
            "passing_score": 60.0,
        }, headers=cls._h(d.teacher_token), timeout=30)
        r.raise_for_status()
        d.bank_id = r.json()["id"]
        print(f"[demo]  ✓ bank_id={d.bank_id[:8]}…")

        # Questions (2 MCQ + 1 dissertation)
        for i, (qtype, opts) in enumerate([
            ("mcq", {"options": [
                {"label": "A", "text": "La vitesse de la lumière (3×10⁸ m/s)"},
                {"label": "B", "text": "La constante de Planck (6.626×10⁻³⁴ J·s)"},
                {"label": "C", "text": "La constante gravitationnelle (6.674×10⁻¹¹)"},
                {"label": "D", "text": "La charge de l'électron (1.6×10⁻¹⁹ C)"},
            ], "correct_answer_indices": [0]}),
            ("mcq", {"options": [
                {"label": "A", "text": "F = m × v"},
                {"label": "B", "text": "F = m × a"},
                {"label": "C", "text": "F = m × g"},
                {"label": "D", "text": "F = m × v²"},
            ], "correct_answer_indices": [1]}),
            ("dissertation", {"model_answer": "La thermodynamique est l'étude des relations entre chaleur et travail.", "rubric": [
                {"criterion": "Précision scientifique", "max_points": 60, "description": "Exactitude des concepts"},
                {"criterion": "Clarté", "max_points": 40, "description": "Organisation et langage"},
            ]}),
        ]):
            body: dict = {
                "question_type": qtype,
                "description": [
                    "Laquelle des constantes suivantes représente la vitesse de la lumière dans le vide ?",
                    "Quelle est la formule de la deuxième loi de Newton ?",
                    "Expliquez les principes fondamentaux de la thermodynamique et leur application.",
                ][i],
                "order_index": i,
                **opts,
            }
            r = requests.post(f"{api_url}/exam/banks/{d.bank_id}/question",
                              json=body, headers=cls._h(d.teacher_token), timeout=30)
            r.raise_for_status()
        print("[demo]  ✓ 3 questions created (2 MCQ + 1 dissertation)")

        # Validate-all → publishes bank
        r = requests.post(f"{api_url}/exam/banks/{d.bank_id}/validate-all",
                          headers=cls._h(d.teacher_token), timeout=30)
        r.raise_for_status()
        print(f"[demo]  ✓ bank published  status={r.json().get('bank_status')}")

        # Create test
        r = requests.post(f"{api_url}/exam/banks/{d.bank_id}/tests", json={
            "title": f"Demo Test {ts}", "time_limit_minutes": 30, "shuffle_questions": False,
        }, headers=cls._h(d.teacher_token), timeout=30)
        r.raise_for_status()
        d.test_id = r.json()["id"]
        print(f"[demo]  ✓ test_id={d.test_id[:8]}…")

        # Publish test (belt-and-suspenders)
        requests.patch(f"{api_url}/exam/tests/{d.test_id}", json={"status": "published"},
                       headers=cls._h(d.teacher_token), timeout=10)

        # Start student attempt + proctoring session (for proctor screenshots)
        r = requests.post(f"{api_url}/exam/tests/{d.test_id}/start",
                          headers=cls._h(d.student_token), timeout=15)
        if r.status_code in (200, 201):
            d.attempt_id = r.json().get("attempt_id", "")
            print(f"[demo]  ✓ attempt_id={d.attempt_id[:8] if d.attempt_id else 'n/a'}…")

        r = requests.post(f"{api_url}/proctor/sessions/start",
                          json={"attempt_id": d.attempt_id} if d.attempt_id else {},
                          headers=cls._h(d.student_token), timeout=15)
        if r.status_code in (200, 201):
            data = r.json()
            d.session_id = data.get("session_id", "")
            d.session_token = data.get("session_token", "")
            print(f"[demo]  ✓ session_id={d.session_id[:8] if d.session_id else 'n/a'}…")

        return d


# ---------------------------------------------------------------------------
# Screenshot capture
# ---------------------------------------------------------------------------

PLACEHOLDER_HTML = """
<html><body style="margin:0;background:#f4f4f5;display:flex;align-items:center;
justify-content:center;height:100vh;font-family:system-ui,sans-serif;flex-direction:column;gap:12px">
<div style="background:#fff;border:1px solid #e4e4e7;border-radius:10px;padding:32px 48px;
text-align:center;max-width:480px">
<div style="font-size:48px;margin-bottom:12px">📷</div>
<h2 style="margin:0 0 8px;font-size:18px;font-weight:600;color:#18181b">ROLE_PLACEHOLDER</h2>
<p style="margin:0 0 4px;font-size:14px;color:#71717a">PAGE_PLACEHOLDER</p>
<p style="margin:0;font-size:12px;color:#a1a1aa">Start the app to capture live screenshots</p>
</div></body></html>
"""


def _placeholder_b64(page, role: str, name: str) -> str:
    html = (PLACEHOLDER_HTML
            .replace("ROLE_PLACEHOLDER", role.title())
            .replace("PAGE_PLACEHOLDER", name.replace("_", " ").title()))
    page.set_content(html)
    page.wait_for_load_state("domcontentloaded")
    return base64.b64encode(page.screenshot(full_page=False)).decode()


def _capture(page) -> str:
    return base64.b64encode(page.screenshot(full_page=True)).decode()


def _capture_viewport(page) -> str:
    return base64.b64encode(page.screenshot(full_page=False)).decode()


def _set_cookie(context, token: str, domain: str, secure: bool = False) -> None:
    context.add_cookies([{
        "name": "access_token",
        "value": token,
        "domain": domain,
        "path": "/",
        "httpOnly": False,
        "secure": secure,
        "sameSite": "Lax",
    }])


def _mock_minio(page) -> None:
    """Mock MinIO presigned URL calls for headless camera capture."""
    FAKE_URL = "http://localhost:9999/mock-upload"

    def _handler(route, request):
        url = request.url
        if any(k in url for k in ("reference-frame-upload-url", "snapshot-upload-url", "/identity/upload-url")):
            route.fulfill(status=200, content_type="application/json",
                          body=f'{{"upload_url":"{FAKE_URL}","storage_key":"mock/key"}}')
        elif "/identity/recorded" in url and request.method == "POST":
            route.fulfill(status=200, content_type="application/json",
                          body='{"session_id":"mock","identity_verified":false,"identity_status":"pending"}')
        elif "/identity/status" in url:
            route.fulfill(status=200, content_type="application/json",
                          body='{"session_id":"mock","identity_verified":true,"identity_status":"verified","identity_verified_at":"2026-01-01T00:00:00Z"}')
        elif request.method == "PUT":
            route.fulfill(status=200)
        else:
            route.continue_()

    page.route("**/*", _handler)


def capture_teacher_shots(browser, base_url: str, demo: DemoData, is_offline: bool) -> dict[str, str]:
    from urllib.parse import urlparse
    domain = urlparse(base_url).hostname or "localhost"
    shots: dict[str, str] = {}

    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    page = ctx.new_page()
    page.set_default_timeout(20_000)
    _set_cookie(ctx, demo.teacher_token, domain)

    def go(url: str, wait: str = "networkidle") -> None:
        page.goto(url)
        try:
            page.wait_for_load_state(wait, timeout=15_000)
        except Exception:
            pass
        time.sleep(2)

    if is_offline:
        for name in ["dashboard", "create_step0", "create_step1", "create_step2", "create_step3",
                     "review_board", "proctor_dashboard", "session_detail"]:
            shots[name] = _placeholder_b64(page, "Teacher", name)
        ctx.close()
        return shots

    # Dashboard
    go(f"{base_url}/fr/")
    shots["dashboard"] = _capture(page)
    print("[shot]  teacher/dashboard")

    # Create wizard — step 0 (exam info)
    go(f"{base_url}/fr/create", "domcontentloaded")
    time.sleep(1)
    shots["create_step0"] = _capture(page)
    print("[shot]  teacher/create_step0")

    # Fill title to enable Next
    try:
        page.fill('input[name="title_fr"], input[placeholder*="médecine"], input[placeholder*="Titre"], input[type="text"]', "Physique Quantique — Démonstration", timeout=5_000)
    except Exception:
        try:
            page.fill('input', "Physique Quantique — Démonstration", timeout=3_000)
        except Exception:
            pass

    # Advance to step 1 (source upload)
    try:
        page.locator("button:has-text('Next'), button:has-text('Suivant'), button:has-text('Continuer')").first.click(timeout=5_000)
        time.sleep(2)
        shots["create_step1"] = _capture(page)
        print("[shot]  teacher/create_step1")
    except Exception:
        shots["create_step1"] = _placeholder_b64(page, "Teacher", "create_step1")

    # Advance to step 2 (scenario config)
    try:
        page.locator("button:has-text('Next'), button:has-text('Suivant'), button:has-text('Continuer')").first.click(timeout=5_000)
        time.sleep(2)
        shots["create_step2"] = _capture(page)
        print("[shot]  teacher/create_step2")
    except Exception:
        shots["create_step2"] = _placeholder_b64(page, "Teacher", "create_step2")

    # Step 3 — click "Generate" to show spinner
    try:
        page.locator("button:has-text('Générer'), button:has-text('Generate'), button:has-text('Next'), button:has-text('Suivant')").first.click(timeout=5_000)
        time.sleep(2)
        shots["create_step3"] = _capture(page)
        print("[shot]  teacher/create_step3")
    except Exception:
        shots["create_step3"] = _placeholder_b64(page, "Teacher", "create_step3")

    # Review board
    if demo.bank_id:
        go(f"{base_url}/fr/banks/{demo.bank_id}/review")
        shots["review_board"] = _capture(page)
        print("[shot]  teacher/review_board")
    else:
        shots["review_board"] = _placeholder_b64(page, "Teacher", "review_board")

    # Proctor dashboard
    go(f"{base_url}/fr/proctor/dashboard", "domcontentloaded")
    time.sleep(3)
    shots["proctor_dashboard"] = _capture(page)
    print("[shot]  teacher/proctor_dashboard")

    # Session detail
    if demo.session_id:
        go(f"{base_url}/fr/proctor/sessions/{demo.session_id}", "domcontentloaded")
        time.sleep(3)
        shots["session_detail"] = _capture(page)
        print("[shot]  teacher/session_detail")
    else:
        shots["session_detail"] = _placeholder_b64(page, "Teacher", "session_detail")

    ctx.close()
    return shots


def capture_student_shots(browser, base_url: str, demo: DemoData, is_offline: bool) -> dict[str, str]:
    from urllib.parse import urlparse
    domain = urlparse(base_url).hostname or "localhost"
    shots: dict[str, str] = {}

    ctx = browser.new_context(
        viewport={"width": 1280, "height": 900},
        permissions=["camera", "microphone"],
    )
    page = ctx.new_page()
    page.set_default_timeout(20_000)
    _set_cookie(ctx, demo.student_token, domain)
    _mock_minio(page)

    def go(url: str, wait: str = "networkidle") -> None:
        page.goto(url)
        try:
            page.wait_for_load_state(wait, timeout=15_000)
        except Exception:
            pass
        time.sleep(2)

    if is_offline:
        for name in ["student_dashboard", "precheck_step1", "precheck_step2",
                     "precheck_step3", "precheck_step4", "exam_player", "results"]:
            shots[name] = _placeholder_b64(page, "Student", name)
        ctx.close()
        return shots

    # Student dashboard
    go(f"{base_url}/fr/")
    shots["student_dashboard"] = _capture(page)
    print("[shot]  student/student_dashboard")

    if not demo.test_id:
        for name in ["precheck_step1", "precheck_step2", "precheck_step3", "precheck_step4", "exam_player", "results"]:
            shots[name] = _placeholder_b64(page, "Student", name)
        ctx.close()
        return shots

    # Pre-check step 1 (system check)
    go(f"{base_url}/fr/session/pre-check/{demo.test_id}", "domcontentloaded")
    time.sleep(6)
    shots["precheck_step1"] = _capture(page)
    print("[shot]  student/precheck_step1")

    # Advance to step 2 (camera preview)
    try:
        deadline = time.monotonic() + 75
        while time.monotonic() < deadline:
            try:
                btn = page.locator("button:has-text('Next'), button:has-text('Suivant')")
                if btn.count() > 0 and btn.first.is_enabled(timeout=1000):
                    break
            except Exception:
                pass
            time.sleep(2)
        page.locator("button:has-text('Next'), button:has-text('Suivant')").first.click(timeout=5_000)
        time.sleep(3)
        shots["precheck_step2"] = _capture(page)
        print("[shot]  student/precheck_step2")
    except Exception:
        shots["precheck_step2"] = _placeholder_b64(page, "Student", "precheck_step2")

    # Capture reference frame, then advance to step 3
    try:
        page.wait_for_selector("video", timeout=8000)
        time.sleep(2)
        cap_btn = page.get_by_role("button", name="Capture reference frame")
        if cap_btn.count() > 0:
            cap_btn.first.click(timeout=5_000)
            page.wait_for_selector("button:has-text('Use this photo'), button:has-text('Utiliser')", timeout=10_000)
            page.locator("button:has-text('Use this photo'), button:has-text('Utiliser')").first.click()
            time.sleep(1)
    except Exception:
        pass

    # Step 3 (identity verification)
    try:
        page.wait_for_selector("text=Step 3, text=Étape 3", timeout=10_000)
        time.sleep(4)
        shots["precheck_step3"] = _capture(page)
        print("[shot]  student/precheck_step3")

        # Click capture & verify
        capture_btn = page.get_by_role("button", name="Capture & Verify")
        if capture_btn.count() == 0:
            capture_btn = page.locator("button:has-text('Capturer')")
        if capture_btn.count() > 0:
            capture_btn.first.click(timeout=5_000)
        time.sleep(3)

        # Advance to step 4
        for sel in ["button:has-text('Continue →')", "button:has-text('Continue')", "button:has-text('Continuer')", "button:has-text('Next')"]:
            try:
                page.wait_for_selector(sel, timeout=4_000)
                page.locator(sel).first.click()
                break
            except Exception:
                pass
    except Exception:
        shots["precheck_step3"] = _placeholder_b64(page, "Student", "precheck_step3")

    # Step 4 (consent)
    try:
        page.wait_for_selector("text=Step 4, text=Étape 4", timeout=8_000)
        time.sleep(2)
        shots["precheck_step4"] = _capture(page)
        print("[shot]  student/precheck_step4")
    except Exception:
        shots["precheck_step4"] = _placeholder_b64(page, "Student", "precheck_step4")

    # Exam player (navigate directly — skip pre-check start)
    go(f"{base_url}/fr/exams/{demo.test_id}/play", "domcontentloaded")
    time.sleep(4)
    shots["exam_player"] = _capture(page)
    print("[shot]  student/exam_player")

    # Results page (use URL params)
    score_url = (f"{base_url}/fr/exams/{demo.test_id}/results"
                 f"?attemptId={demo.attempt_id or 'demo'}&score=2&total=3&passed=true")
    go(score_url, "domcontentloaded")
    time.sleep(2)
    shots["results"] = _capture(page)
    print("[shot]  student/results")

    ctx.close()
    return shots


def capture_admin_shots(browser, base_url: str, demo: DemoData, teacher_shots: dict[str, str]) -> dict[str, str]:
    """Admin sees the same pages as teacher — reuse shots, add admin-badge screenshot."""
    from urllib.parse import urlparse
    domain = urlparse(base_url).hostname or "localhost"
    shots = dict(teacher_shots)  # shallow copy

    if not demo.admin_token:
        return shots

    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    page = ctx.new_page()
    page.set_default_timeout(20_000)
    _set_cookie(ctx, demo.admin_token, domain)

    try:
        page.goto(f"{base_url}/fr/")
        page.wait_for_load_state("networkidle", timeout=12_000)
        time.sleep(2)
        shots["admin_dashboard"] = _capture(page)
        print("[shot]  admin/admin_dashboard")
    except Exception:
        shots["admin_dashboard"] = _placeholder_b64(page, "Admin", "admin_dashboard")

    ctx.close()
    return shots


# ---------------------------------------------------------------------------
# HTML renderer
# ---------------------------------------------------------------------------

# Shared inline CSS based on app design tokens
CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
:root {
  --bg:        #ffffff;
  --fg:        #0f0f10;
  --muted:     #f7f7f8;
  --muted-fg:  #717179;
  --border:    #e8e8ea;
  --primary:   #222224;
  --primary-fg:#f9f9fa;
  --radius:    10px;
  --success-bg:#d1fae5; --success-fg:#065f46;
  --warning-bg:#fef3c7; --warning-fg:#92400e;
  --danger-bg: #fee2e2; --danger-fg: #991b1b;
  --info-bg:   #dbeafe; --info-fg:   #1e40af;
  --purple-bg: #ede9fe; --purple-fg: #5b21b6;
  --sidebar-w: 230px;
  --content-ml: 250px;
}
body {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  background: var(--bg);
  color: var(--fg);
  line-height: 1.6;
  font-size: 15px;
}

/* ── Layout ── */
#sidebar {
  position: fixed; top: 0; left: 0; bottom: 0; width: var(--sidebar-w);
  background: #fafafa; border-right: 1px solid var(--border);
  overflow-y: auto; padding: 24px 16px; z-index: 10;
}
#sidebar .brand {
  display: flex; align-items: center; gap: 10px;
  font-weight: 700; font-size: 16px; margin-bottom: 28px; color: var(--fg);
  text-decoration: none;
}
#sidebar .brand-icon {
  width: 32px; height: 32px; background: var(--primary); border-radius: var(--radius);
  display: flex; align-items: center; justify-content: center; flex-shrink: 0;
}
#sidebar .brand-icon svg { width: 18px; height: 18px; color: var(--primary-fg); }
#sidebar nav { display: flex; flex-direction: column; gap: 2px; }
#sidebar nav a {
  display: block; padding: 7px 12px; border-radius: 7px;
  text-decoration: none; color: var(--muted-fg); font-size: 13.5px; font-weight: 500;
  transition: background .12s, color .12s;
}
#sidebar nav a:hover, #sidebar nav a.active {
  background: var(--border); color: var(--fg);
}
#sidebar .divider { height: 1px; background: var(--border); margin: 12px 0; }
#sidebar .section-label {
  font-size: 11px; font-weight: 600; text-transform: uppercase;
  letter-spacing: .08em; color: var(--muted-fg); padding: 0 12px 4px;
}

#content {
  margin-left: var(--content-ml);
  max-width: 900px;
  padding: 40px 40px 80px;
}

/* ── Header ── */
#doc-header {
  border-bottom: 1px solid var(--border); padding-bottom: 28px; margin-bottom: 40px;
}
#doc-header .top-row {
  display: flex; align-items: center; gap: 12px; margin-bottom: 10px;
}
#doc-header h1 { font-size: 26px; font-weight: 700; margin-bottom: 6px; }
#doc-header .subtitle { color: var(--muted-fg); font-size: 14px; }

/* ── Badges ── */
.badge {
  display: inline-flex; align-items: center; border-radius: 9999px;
  padding: 2px 10px; font-size: 12px; font-weight: 500; border: 1px solid transparent;
}
.badge-default  { background: var(--primary); color: var(--primary-fg); }
.badge-success  { background: var(--success-bg); color: var(--success-fg); }
.badge-warning  { background: var(--warning-bg); color: var(--warning-fg); }
.badge-danger   { background: var(--danger-bg);  color: var(--danger-fg);  }
.badge-info     { background: var(--info-bg);    color: var(--info-fg);    }
.badge-purple   { background: var(--purple-bg);  color: var(--purple-fg);  }
.badge-outline  { border-color: var(--border); color: var(--muted-fg); }
.badge-muted    { background: var(--muted); color: var(--muted-fg); }
.badge-teacher  { background: var(--muted); color: var(--fg); }
.badge-student  { background: var(--success-bg); color: var(--success-fg); }
.badge-admin    { background: var(--purple-bg); color: var(--purple-fg); }

/* ── Sections ── */
section { margin-bottom: 56px; scroll-margin-top: 24px; }
section h2 {
  font-size: 20px; font-weight: 700; margin-bottom: 6px;
  padding-bottom: 10px; border-bottom: 1px solid var(--border);
}
section h3 { font-size: 16px; font-weight: 600; margin: 24px 0 10px; }
section p { margin-bottom: 12px; color: #3c3c3e; }
section ul, section ol { padding-left: 22px; margin-bottom: 14px; }
section li { margin-bottom: 5px; color: #3c3c3e; }
section strong { color: var(--fg); font-weight: 600; }

/* ── Cards ── */
.card {
  background: var(--bg); border: 1px solid var(--border);
  border-radius: var(--radius); padding: 20px 24px; margin-bottom: 16px;
}
.card-title { font-weight: 600; font-size: 15px; margin-bottom: 6px; }
.card p { margin-bottom: 0; }

/* ── Callouts ── */
.callout {
  border-radius: var(--radius); padding: 14px 18px; margin: 16px 0;
  border-left: 4px solid;
}
.callout-info    { background: var(--info-bg);    border-color: #3b82f6; color: var(--info-fg); }
.callout-warning { background: var(--warning-bg); border-color: #f59e0b; color: var(--warning-fg); }
.callout-success { background: var(--success-bg); border-color: #10b981; color: var(--success-fg); }
.callout-danger  { background: var(--danger-bg);  border-color: #ef4444; color: var(--danger-fg); }
.callout-admin   { background: var(--purple-bg);  border-color: #8b5cf6; color: var(--purple-fg); }
.callout strong  { font-weight: 700; }

/* ── Steps ── */
.steps { counter-reset: step; list-style: none; padding: 0; }
.steps li {
  counter-increment: step; display: flex; gap: 14px; margin-bottom: 18px; align-items: flex-start;
}
.steps li::before {
  content: counter(step); flex-shrink: 0;
  width: 28px; height: 28px; background: var(--primary); color: var(--primary-fg);
  border-radius: 50%; font-size: 13px; font-weight: 700;
  display: flex; align-items: center; justify-content: center; margin-top: 1px;
}
.steps li .step-content { flex: 1; }
.steps li .step-title { font-weight: 600; margin-bottom: 3px; }
.steps li .step-desc { color: var(--muted-fg); font-size: 13.5px; }

/* ── Screenshots ── */
figure {
  margin: 20px 0 28px;
  background: var(--muted); border: 1px solid var(--border);
  border-radius: var(--radius); overflow: hidden;
}
figure img {
  display: block; width: 100%; height: auto;
}
figcaption {
  padding: 8px 14px; font-size: 12.5px; color: var(--muted-fg);
  background: var(--muted); border-top: 1px solid var(--border);
}
figure[data-placeholder] { border: 2px dashed var(--warning-bg); }
figure[data-placeholder] img { opacity: .7; }
figure[data-placeholder] figcaption { background: var(--warning-bg); color: var(--warning-fg); }

/* ── Status table ── */
.status-table { width: 100%; border-collapse: collapse; font-size: 13.5px; margin: 12px 0 20px; }
.status-table th {
  text-align: left; padding: 8px 12px; background: var(--muted);
  border-bottom: 2px solid var(--border); font-weight: 600; font-size: 12px;
  text-transform: uppercase; letter-spacing: .05em; color: var(--muted-fg);
}
.status-table td { padding: 9px 12px; border-bottom: 1px solid var(--border); }
.status-table tr:last-child td { border-bottom: none; }

/* ── Offline banner ── */
#offline-banner {
  display: none; position: fixed; top: 0; left: 0; right: 0; z-index: 100;
  background: var(--warning-bg); color: var(--warning-fg); text-align: center;
  padding: 10px 20px; font-size: 13px; font-weight: 500; border-bottom: 1px solid #f59e0b;
}
body.has-placeholders #offline-banner { display: block; }
body.has-placeholders #content { padding-top: 60px; }

/* ── Footer ── */
footer {
  color: var(--muted-fg); font-size: 12px; text-align: center;
  padding: 24px 0; border-top: 1px solid var(--border); margin-top: 40px;
}

/* ── Responsive ── */
@media (max-width: 768px) {
  #sidebar { display: none; }
  #content { margin-left: 0; padding: 20px; }
}
"""

ROLE_GATE_JS = {
    "teacher": "['expert','admin','sub_admin']",
    "student": "['user']",
    "admin":   "['admin','sub_admin']",
}

SIDEBAR_ACTIVE_JS = """
(function() {
  var sections = document.querySelectorAll('section[id]');
  var links = document.querySelectorAll('#sidebar nav a[href^="#"]');
  if (!sections.length || !links.length) return;
  var obs = new IntersectionObserver(function(entries) {
    entries.forEach(function(e) {
      var link = document.querySelector('#sidebar nav a[href="#' + e.target.id + '"]');
      if (link) link.classList.toggle('active', e.isIntersecting);
    });
  }, { threshold: 0.25 });
  sections.forEach(function(s) { obs.observe(s); });
})();
"""

GRAD_HEADER = "background: linear-gradient(135deg, #001f3f 0%, #1e3a8a 50%, #4c1d95 100%);"

BRAND_ICON_SVG = """<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
  stroke-linecap="round" stroke-linejoin="round" xmlns="http://www.w3.org/2000/svg">
  <path d="M22 10v6M2 10l10-5 10 5-10 5z"/><path d="M6 12v5c3 3 9 3 12 0v-5"/>
</svg>"""

def _figure(b64: str, caption: str, is_placeholder: bool = False) -> str:
    ph = ' data-placeholder="true"' if is_placeholder else ""
    prefix = "⚠️ Placeholder — " if is_placeholder else ""
    return (
        f'<figure{ph}>'
        f'<img src="data:image/png;base64,{b64}" alt="{caption}" loading="lazy">'
        f'<figcaption>{prefix}{caption}</figcaption>'
        f'</figure>'
    )


def _role_gate_script(role: str) -> str:
    allowed = ROLE_GATE_JS[role]
    return f"""<script>
(function(){{
  function gc(n){{var m=document.cookie.match(new RegExp('(?:^|; )'+n+'=([^;]*)'));return m?decodeURIComponent(m[1]):null;}}
  function dj(t){{try{{return JSON.parse(atob(t.split('.')[1].replace(/-/g,'+').replace(/_/g,'/')));}}catch(e){{return null;}}}}
  var t=gc('access_token');
  if(!t){{window.location.replace('/fr/login');return;}}
  var p=dj(t);
  if(!p){{window.location.replace('/fr/login');return;}}
  var ALLOWED={allowed};
  if(ALLOWED.indexOf(p.role)===-1){{window.location.replace('/fr/login?reason=role_mismatch');return;}}
  document.addEventListener('DOMContentLoaded',function(){{
    var b=document.getElementById('role-badge');
    if(b)b.textContent=p.role;
    var n=document.getElementById('user-name');
    if(n)n.textContent=p.sub||p.user_id||'';
  }});
}})();
</script>"""


def _html_doc(role: str, title: str, subtitle: str, badge_class: str,
              nav_links: list[tuple[str, str]],
              body_html: str,
              has_placeholders: bool = False) -> str:
    nav_items = "\n".join(
        f'<a href="#{sid}">{label}</a>' for sid, label in nav_links
    )
    placeholder_class = " has-placeholders" if has_placeholders else ""
    gen_date = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Sira Exam — {title}</title>
  <style>{CSS}</style>
  {_role_gate_script(role)}
</head>
<body class="{placeholder_class}">

<div id="offline-banner">
  ⚠️ Ces captures d'écran sont des maquettes — lancez l'application pour générer des captures réelles.
</div>

<aside id="sidebar">
  <a class="brand" href="#">
    <div class="brand-icon">{BRAND_ICON_SVG}</div>
    Sira Exam
  </a>
  <div class="section-label">Navigation</div>
  <nav>
    {nav_items}
  </nav>
  <div class="divider"></div>
  <div style="padding: 0 12px; font-size:12px; color: var(--muted-fg);">
    Connecté en tant que<br>
    <strong id="role-badge" style="color:var(--fg)">…</strong>
    <span id="user-name" style="display:block;margin-top:2px;font-size:11px"></span>
  </div>
</aside>

<main id="content">
  <div id="doc-header">
    <div class="top-row">
      <span class="badge {badge_class}">{role.title()}</span>
    </div>
    <h1>{title}</h1>
    <p class="subtitle">{subtitle}</p>
  </div>

  {body_html}

  <footer>
    Sira Exam Service &nbsp;·&nbsp; Manuel {title} &nbsp;·&nbsp; Généré le {gen_date}
  </footer>
</main>

<script>{SIDEBAR_ACTIVE_JS}</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Teacher manual content
# ---------------------------------------------------------------------------

def render_teacher(shots: dict[str, str]) -> str:
    ph = lambda k: "PLACEHOLDER" in shots.get(k, "")  # noqa: E731

    def fig(key: str, caption: str) -> str:
        b64 = shots.get(key, "")
        return _figure(b64, caption, is_placeholder=(not b64 or ph(key)))

    body = f"""
<section id="overview">
  <h2>Aperçu du rôle Enseignant</h2>
  <p>En tant qu'<strong>enseignant</strong> (<code>expert</code>), vous gérez l'ensemble du cycle de vie des examens :
  création de banques de questions, révision des questions générées par l'IA,
  surveillance des sessions proctorées et notation des dissertations.</p>
  <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:12px;margin:20px 0">
    <div class="card"><div class="card-title">📚 Banques d'examens</div><p>Créer et gérer des banques de questions.</p></div>
    <div class="card"><div class="card-title">🤖 Génération IA</div><p>Générer des QCM et dissertations via Claude.</p></div>
    <div class="card"><div class="card-title">✅ Validation</div><p>Réviser, modifier et publier les questions.</p></div>
    <div class="card"><div class="card-title">📊 Notation</div><p>Valider les scores IA sur les dissertations.</p></div>
    <div class="card"><div class="card-title">🎥 Surveillance</div><p>Monitorer les sessions proctorées en direct.</p></div>
  </div>
</section>

<section id="dashboard">
  <h2>1. Tableau de bord</h2>
  <p>La page d'accueil présente la liste de toutes vos <strong>banques d'examens</strong>
  avec leur statut. Cliquez sur <strong>Nouvel examen</strong> pour démarrer la création.</p>
  {fig("dashboard", "Tableau de bord enseignant — liste des banques d'examens")}
  <h3>Signification des statuts</h3>
  <table class="status-table">
    <thead><tr><th>Statut</th><th>Badge</th><th>Signification</th><th>Actions disponibles</th></tr></thead>
    <tbody>
      <tr><td><code>draft</code></td><td><span class="badge badge-outline">Brouillon</span></td>
          <td>Banque créée, configuration incomplète</td><td>Reprendre la configuration</td></tr>
      <tr><td><code>generating</code></td><td><span class="badge badge-warning">Génération…</span></td>
          <td>L'IA génère les questions (2–5 min)</td><td>Patienter</td></tr>
      <tr><td><code>review</code></td><td><span class="badge badge-warning">Révision</span></td>
          <td>Questions prêtes, en attente de validation</td><td>Ouvrir le tableau de révision</td></tr>
      <tr><td><code>published</code></td><td><span class="badge badge-success">Publié</span></td>
          <td>Banque publiée, test disponible pour les étudiants</td><td>Copier le lien, noter</td></tr>
      <tr><td><code>archived</code></td><td><span class="badge badge-outline">Archivé</span></td>
          <td>Banque désactivée</td><td>Consulter uniquement</td></tr>
    </tbody>
  </table>
</section>

<section id="create">
  <h2>2. Créer un examen</h2>
  <p>L'assistant de création guide en <strong>4 étapes</strong> la construction d'une banque d'examens.
  Cliquez sur <strong>Nouvel examen</strong> dans la barre de navigation pour démarrer.</p>

  <h3>Étape 1 — Informations générales</h3>
  <p>Renseignez le titre (en français), la matière, la langue et le score de passage.</p>
  {fig("create_step0", "Étape 1 — Informations de l'examen")}

  <h3>Étape 2 — Sources</h3>
  <p>Téléversez un ou plusieurs PDF ou documents Word. Le backend extrait automatiquement le texte
  via <strong>PyMuPDF</strong>. Attendez le badge <span class="badge badge-success">Extrait</span>
  avant de continuer.</p>
  {fig("create_step1", "Étape 2 — Téléversement des sources")}

  <h3>Étape 3 — Scénarios</h3>
  <p>Définissez les scénarios thématiques et le nombre de questions par type (QCM / dissertation).
  Chaque scénario deviendra un bloc contextuel dans l'interface étudiant.</p>
  {fig("create_step2", "Étape 3 — Configuration des scénarios")}

  <h3>Étape 4 — Génération</h3>
  <p>Cliquez sur <strong>Générer l'examen</strong>. Claude Sonnet génère les questions
  en 2 à 5 minutes. Une bannière de progression s'affiche ; vous pouvez fermer l'onglet
  et revenir plus tard.</p>
  {fig("create_step3", "Étape 4 — Génération IA en cours")}

  <div class="callout callout-info">
    <strong>ℹ️ Conseil :</strong> Plus le PDF source est structuré et pertinent, meilleures seront les questions générées.
    Privilégiez des documents de cours plutôt que des manuels entiers.
  </div>
</section>

<section id="review">
  <h2>3. Tableau de révision</h2>
  <p>Une fois la génération terminée (<code>status=review</code>), cliquez sur
  <strong>Tableau de révision</strong> depuis le tableau de bord.</p>
  {fig("review_board", "Tableau de révision — édition des questions")}
  <h3>Actions disponibles</h3>
  <ul>
    <li><strong>Modifier</strong> : cliquez sur n'importe quel champ pour l'éditer (sauvegarde automatique).</li>
    <li><strong>Valider</strong> : chaque question doit être validée avant publication.
        Utilisez <strong>Tout valider</strong> pour valider en masse.</li>
    <li><strong>Publier</strong> : disponible uniquement lorsque toutes les questions sont validées.
        La publication crée automatiquement un test assignable aux étudiants.</li>
    <li><strong>Copier le lien</strong> : partagez directement l'URL du test avec vos étudiants.</li>
  </ul>
  <div class="callout callout-warning">
    <strong>⚠️ Important :</strong> Une question ne peut pas être modifiée après que des étudiants ont commencé le test.
    Vérifiez bien avant de publier.
  </div>
</section>

<section id="proctor">
  <h2>4. Surveillance des sessions</h2>
  <p>Le <strong>Tableau de surveillance</strong> (bouton <em>Proctor</em> dans la barre de navigation)
  affiche en temps réel les sessions actives. Il se rafraîchit toutes les <strong>5 secondes</strong>.</p>
  {fig("proctor_dashboard", "Tableau de surveillance — grille des sessions actives")}
  <h3>Lecture de la grille</h3>
  <table class="status-table">
    <thead><tr><th>Élément</th><th>Signification</th></tr></thead>
    <tbody>
      <tr><td>Vignette webcam</td><td>Dernière capture reçue depuis l'appareil de l'étudiant</td></tr>
      <tr><td><span class="badge badge-danger">3</span> badge rouge</td><td>Nombre d'alertes non acquittées</td></tr>
      <tr><td>Gap: 2m</td><td>Durée depuis la dernière capture (> 2 min = problème réseau)</td></tr>
      <tr><td><span class="badge badge-success">active</span></td><td>Session en cours</td></tr>
      <tr><td><span class="badge badge-warning">disconnected</span></td><td>Perte de connexion détectée</td></tr>
      <tr><td><span class="badge badge-danger">terminated</span></td><td>Session arrêtée manuellement</td></tr>
    </tbody>
  </table>
</section>

<section id="session-detail">
  <h2>5. Détail de session</h2>
  <p>Cliquez sur <strong>Voir</strong> depuis la grille pour accéder au détail complet d'une session.</p>
  {fig("session_detail", "Détail de session — timeline des alertes et captures")}
  <h3>Panneaux disponibles</h3>
  <ul>
    <li><strong>Informations session</strong> : ID étudiant, durée, battements de cœur manqués.</li>
    <li><strong>Alertes</strong> : liste des événements détectés, classés par sévérité.
        Cliquez <strong>Acquitter</strong> pour chaque alerte confirmée.</li>
    <li><strong>Captures</strong> : grille des instantanés webcam avec badges de verdict IA
        (<em>Edge + Confirmed</em>, <em>Edge Only</em>, <em>Server</em>).</li>
    <li><strong>Timeline des événements</strong> : chronologie complète (violations, déconnexions).</li>
  </ul>
  <h3>Sévérité des alertes</h3>
  <table class="status-table">
    <thead><tr><th>Sévérité</th><th>Exemples</th><th>Action recommandée</th></tr></thead>
    <tbody>
      <tr><td><span class="badge badge-info">info</span></td><td>Mouvement, clignement</td><td>Observer</td></tr>
      <tr><td><span class="badge badge-warning">medium</span></td><td>Changement d'onglet, copier-coller</td><td>Surveiller</td></tr>
      <tr><td><span class="badge badge-danger">high</span></td><td>Ouverture des DevTools, perte caméra</td><td>Contacter l'étudiant</td></tr>
      <tr><td><span class="badge badge-danger" style="background:#7f1d1d">critical</span></td><td>Multiples visages, téléphone détecté</td><td>Terminer la session</td></tr>
    </tbody>
  </table>
  <h3>Terminer une session</h3>
  <p>Cliquez <strong>Terminer la session</strong> → saisissez la raison → confirmez.
  L'étudiant voit son accès révoqué immédiatement et ne peut pas reprendre l'examen.</p>
  <div class="callout callout-danger">
    <strong>⚠️ Action irréversible :</strong> La terminaison d'une session est définitive.
    Assurez-vous d'avoir une raison valable avant de procéder.
  </div>
</section>

<section id="grading">
  <h2>6. Notation des dissertations</h2>
  <p>Après la soumission d'un examen, l'IA note automatiquement les dissertations
  (<code>status=ai_scored</code>) en moins de 60 secondes. Vous pouvez ensuite
  réviser et remplacer ce score.</p>
  <h3>Processus de notation humaine</h3>
  <ol class="steps">
    <li><div class="step-content">
      <div class="step-title">Accéder aux réponses</div>
      <div class="step-desc">Sur la fiche de la banque, cliquez <strong>Notation</strong>.</div>
    </div></li>
    <li><div class="step-content">
      <div class="step-title">Lire la réponse + score IA</div>
      <div class="step-desc">Le texte de l'étudiant et le détail des critères IA sont affichés côte à côte.</div>
    </div></li>
    <li><div class="step-content">
      <div class="step-title">Saisir votre score et retour</div>
      <div class="step-desc">Entrez un score numérique ≤ score maximal et un commentaire facultatif.</div>
    </div></li>
    <li><div class="step-content">
      <div class="step-title">Enregistrer</div>
      <div class="step-desc">Cliquez <strong>Enregistrer</strong> — la réponse passe en <code>human_reviewed</code>
      et l'étudiant voit le score final.</div>
    </div></li>
  </ol>
</section>

<section id="appendix">
  <h2>7. Annexe — Raccourcis et référence</h2>
  <h3>URLs principales</h3>
  <table class="status-table">
    <thead><tr><th>Page</th><th>URL</th></tr></thead>
    <tbody>
      <tr><td>Tableau de bord</td><td><code>/fr/</code></td></tr>
      <tr><td>Créer un examen</td><td><code>/fr/create</code></td></tr>
      <tr><td>Tableau de révision</td><td><code>/fr/banks/[id]/review</code></td></tr>
      <tr><td>Surveillance</td><td><code>/fr/proctor/dashboard</code></td></tr>
      <tr><td>Détail de session</td><td><code>/fr/proctor/sessions/[id]</code></td></tr>
    </tbody>
  </table>
  <h3>Types de questions</h3>
  <ul>
    <li><strong>QCM</strong> (<code>mcq</code>) : choix unique ou multiple. Score immédiat à la soumission.</li>
    <li><strong>Dissertation</strong> (<code>dissertation</code>) : texte libre. Score IA sous 60 s, notation humaine optionnelle.</li>
  </ul>
</section>
"""
    has_ph = any("PLACEHOLDER" in v or (not v) for v in shots.values())
    return _html_doc(
        role="teacher",
        title="Manuel Enseignant",
        subtitle="Guide complet pour créer, gérer et surveiller les examens.",
        badge_class="badge-teacher",
        nav_links=[
            ("overview", "Aperçu"),
            ("dashboard", "1. Tableau de bord"),
            ("create", "2. Créer un examen"),
            ("review", "3. Tableau de révision"),
            ("proctor", "4. Surveillance"),
            ("session-detail", "5. Détail de session"),
            ("grading", "6. Notation"),
            ("appendix", "7. Annexe"),
        ],
        body_html=body,
        has_placeholders=has_ph,
    )


# ---------------------------------------------------------------------------
# Student manual content
# ---------------------------------------------------------------------------

def render_student(shots: dict[str, str]) -> str:
    ph = lambda k: "PLACEHOLDER" in shots.get(k, "")  # noqa: E731

    def fig(key: str, caption: str) -> str:
        b64 = shots.get(key, "")
        return _figure(b64, caption, is_placeholder=(not b64 or ph(key)))

    body = f"""
<section id="overview">
  <h2>Aperçu du rôle Étudiant</h2>
  <p>En tant qu'<strong>étudiant</strong> (<code>user</code>), vous accédez aux examens
  partagés par votre enseignant, passez la vérification préalable, répondez aux questions
  et consultez vos résultats.</p>
  <div class="callout callout-info">
    <strong>ℹ️ Ce dont vous avez besoin :</strong>
    Une webcam fonctionnelle, un navigateur récent (Chrome recommandé),
    et le lien ou l'identifiant de l'examen fourni par votre enseignant.
  </div>
</section>

<section id="getting-started">
  <h2>1. Accéder à l'examen</h2>
  <p>Votre enseignant vous communique un <strong>lien d'examen</strong> ou un
  <strong>identifiant de test</strong> (UUID). Sur la page d'accueil, collez-le dans le champ
  et cliquez <strong>Commencer →</strong>.</p>
  {fig("student_dashboard", "Page d'accueil étudiant — saisie du lien d'examen")}
  <div class="callout callout-warning">
    <strong>⚠️ Une seule tentative :</strong> Chaque test ne peut être passé qu'une seule fois.
    Assurez-vous d'être prêt(e) avant de démarrer.
  </div>
</section>

<section id="precheck">
  <h2>2. Vérification préalable (4 étapes)</h2>
  <p>Avant l'examen, un assistant en 4 étapes vérifie votre matériel et recueille votre consentement.</p>

  <h3>Étape 1 — Vérification du système</h3>
  <p>L'application vérifie votre caméra, la compatibilité plein écran et la résolution
  (minimum 720p). Les modèles d'IA de détection sont téléchargés en arrière-plan
  (jusqu'à 60 secondes). Le bouton <strong>Suivant</strong> s'active automatiquement
  lorsque tout est prêt.</p>
  {fig("precheck_step1", "Étape 1 — Vérification du système et chargement des modèles")}

  <h3>Étape 2 — Aperçu caméra</h3>
  <p>Positionnez-vous face à la caméra, assurez-vous que votre visage est bien éclairé.
  Cliquez <strong>Capturer l'image de référence</strong>, vérifiez l'aperçu,
  puis <strong>Utiliser cette photo</strong>.</p>
  {fig("precheck_step2", "Étape 2 — Aperçu caméra et capture de référence")}

  <h3>Étape 3 — Vérification d'identité</h3>
  <p>Présentez votre pièce d'identité à côté de votre visage face à la caméra.
  Cliquez <strong>Capturer &amp; Vérifier</strong>. L'IA vérifie la présence de votre visage
  et de votre document. Vous avez <strong>3 tentatives</strong>.</p>
  {fig("precheck_step3", "Étape 3 — Vérification d'identité avec pièce d'identité")}
  <table class="status-table">
    <thead><tr><th>Résultat</th><th>Signification</th><th>Action</th></tr></thead>
    <tbody>
      <tr><td><span class="badge badge-success">✅ Vérifié</span></td>
          <td>Identité confirmée</td><td>Cliquez Continuer</td></tr>
      <tr><td><span class="badge badge-danger">❌ Rejeté</span></td>
          <td>Visage ou document non détecté</td><td>Réessayez (max 3 fois)</td></tr>
      <tr><td><span class="badge badge-danger">🚫 Bloqué</span></td>
          <td>3 échecs — superviseur alerté</td><td>Contactez votre enseignant</td></tr>
    </tbody>
  </table>

  <h3>Étape 4 — Consentement</h3>
  <p>Lisez attentivement les conditions de surveillance. Cochez la case de consentement,
  puis cliquez <strong>Démarrer l'examen</strong>. L'examen commence immédiatement en mode
  plein écran.</p>
  {fig("precheck_step4", "Étape 4 — Consentement et démarrage de l'examen")}
</section>

<section id="exam-player">
  <h2>3. Passer l'examen</h2>
  <p>L'interface d'examen s'ouvre en <strong>mode plein écran verrouillé</strong>.
  Certaines actions sont bloquées pendant la session.</p>
  {fig("exam_player", "Interface d'examen — questions et chronomètre")}

  <h3>Types de questions</h3>
  <ul>
    <li><strong>QCM</strong> : sélectionnez une ou plusieurs réponses via les boutons radio.
        <em>Aucune pénalité pour les mauvaises réponses.</em></li>
    <li><strong>Dissertation</strong> : rédigez votre réponse dans la zone de texte.
        Un minimum de contenu peut être requis.</li>
  </ul>

  <h3>Comportements surveillés</h3>
  <ul>
    <li>Changement d'onglet ou sortie du plein écran → alerte envoyée au surveillant.</li>
    <li>Copier-coller, clic droit et ouverture des outils de développement → bloqués.</li>
    <li>Webcam capture une photo toutes les 30 secondes maximum.</li>
    <li>Battement de cœur envoyé toutes les 30 secondes — ne fermez pas l'onglet.</li>
  </ul>

  <div class="callout callout-warning">
    <strong>⚠️ Hors ligne :</strong> Si votre connexion est coupée, vos réponses sont sauvegardées
    localement et synchronisées dès la reconnexion. La bannière <em>Hors ligne</em> apparaît en haut.
  </div>

  <h3>Soumettre l'examen</h3>
  <ol class="steps">
    <li><div class="step-content">
      <div class="step-title">Cliquez <strong>Soumettre l'examen</strong></div>
      <div class="step-desc">Disponible à tout moment, mais irréversible.</div>
    </div></li>
    <li><div class="step-content">
      <div class="step-title">Confirmez dans la boîte de dialogue</div>
      <div class="step-desc">Un résumé du nombre de questions répondues est affiché.</div>
    </div></li>
    <li><div class="step-content">
      <div class="step-title">Redirection vers les résultats</div>
      <div class="step-desc">Le système calcule automatiquement votre score QCM.</div>
    </div></li>
  </ol>
  <div class="callout callout-info">
    <strong>⏱ Soumission automatique :</strong> Si le temps imparti expire,
    l'examen est soumis automatiquement avec les réponses en cours.
  </div>
</section>

<section id="results">
  <h2>4. Résultats</h2>
  <p>Après soumission, vous voyez immédiatement votre score aux QCM.
  Le score des dissertations est affiché une fois la correction IA terminée
  (généralement sous 60 secondes).</p>
  {fig("results", "Page de résultats — score QCM et état de la dissertation")}
  <table class="status-table">
    <thead><tr><th>Élément</th><th>Signification</th></tr></thead>
    <tbody>
      <tr><td>Score QCM</td><td>Calculé immédiatement à la soumission</td></tr>
      <tr><td><span class="badge badge-warning">En attente de révision</span></td>
          <td>Dissertation en cours de notation IA (max 60 s)</td></tr>
      <tr><td><span class="badge badge-success">Score final</span></td>
          <td>Dissertation notée — score communiqué par l'enseignant</td></tr>
    </tbody>
  </table>
  <div class="callout callout-info">
    <strong>ℹ️ Note :</strong> Le score final incluant la dissertation sera communiqué
    par votre enseignant après révision humaine.
  </div>
</section>

<section id="troubleshooting">
  <h2>5. Dépannage</h2>
  <h3>La caméra ne fonctionne pas</h3>
  <ul>
    <li>Vérifiez que vous avez autorisé l'accès à la caméra dans votre navigateur
        (icône cadenas dans la barre d'adresse).</li>
    <li>Assurez-vous qu'aucune autre application n'utilise la caméra simultanément.</li>
    <li>Rafraîchissez la page et réessayez.</li>
  </ul>
  <h3>La vérification d'identité échoue</h3>
  <ul>
    <li>Assurez-vous d'être dans un endroit bien éclairé.</li>
    <li>Tenez votre pièce d'identité à côté de votre visage, bien visible.</li>
    <li>Évitez les reflets sur les lunettes ou les documents plastifiés.</li>
  </ul>
  <h3>La session a été terminée par le surveillant</h3>
  <ul>
    <li>Votre enseignant a mis fin à la session suite à une violation détectée.</li>
    <li>Contactez votre enseignant pour obtenir des explications.</li>
  </ul>
</section>
"""
    has_ph = any("PLACEHOLDER" in v or (not v) for v in shots.values())
    return _html_doc(
        role="student",
        title="Manuel Étudiant",
        subtitle="Guide pour passer vos examens en toute sérénité.",
        badge_class="badge-student",
        nav_links=[
            ("overview", "Aperçu"),
            ("getting-started", "1. Accéder à l'examen"),
            ("precheck", "2. Vérification préalable"),
            ("exam-player", "3. Passer l'examen"),
            ("results", "4. Résultats"),
            ("troubleshooting", "5. Dépannage"),
        ],
        body_html=body,
        has_placeholders=has_ph,
    )


# ---------------------------------------------------------------------------
# Admin manual content
# ---------------------------------------------------------------------------

def render_admin(shots: dict[str, str]) -> str:
    ph = lambda k: "PLACEHOLDER" in shots.get(k, "")  # noqa: E731

    def fig(key: str, caption: str) -> str:
        b64 = shots.get(key, "")
        return _figure(b64, caption, is_placeholder=(not b64 or ph(key)))

    body = f"""
<section id="overview">
  <h2>Aperçu du rôle Administrateur</h2>
  <p>L'<strong>administrateur</strong> (<code>admin</code> / <code>sub_admin</code>) dispose de
  <strong>toutes les permissions de l'enseignant</strong>, plus des droits de gestion au niveau
  de l'organisation.</p>
  <div class="callout callout-admin">
    <strong>🔑 Permissions supplémentaires :</strong>
    Gestion des banques à l'échelle de l'organisation, substitution des scores,
    supervision de toutes les sessions (tous enseignants confondus).
  </div>
  <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:12px;margin:20px 0">
    <div class="card"><div class="card-title">📚 Toutes les banques</div><p>Accès à toutes les banques de l'organisation.</p></div>
    <div class="card"><div class="card-title">🤖 Génération IA</div><p>Créer des examens pour n'importe quel enseignant.</p></div>
    <div class="card"><div class="card-title">✅ Validation</div><p>Valider et publier sans restriction.</p></div>
    <div class="card"><div class="card-title">📊 Notation globale</div><p>Remplacer tout score IA.</p></div>
    <div class="card"><div class="card-title">🎥 Surveillance org.</div><p>Voir toutes les sessions actives.</p></div>
  </div>
</section>

<section id="dashboard">
  <h2>1. Tableau de bord administrateur</h2>
  <p>Identique au tableau de bord enseignant, mais avec un badge <span class="badge badge-admin">admin</span>
  dans la barre de navigation et l'accès à <strong>toutes les banques de l'organisation</strong>.</p>
  {fig("admin_dashboard", "Tableau de bord administrateur — badge Admin visible dans la navigation")}
</section>

<section id="teacher-features">
  <h2>2. Fonctionnalités enseignant (incluses)</h2>
  <p>L'administrateur bénéficie de l'ensemble des fonctionnalités décrites dans le
  <strong>Manuel Enseignant</strong> :</p>
  <ul>
    <li>Création d'examens via l'assistant 4 étapes</li>
    <li>Révision et validation des questions générées</li>
    <li>Surveillance des sessions proctorées</li>
    <li>Notation des dissertations (révision humaine)</li>
  </ul>
  <p>Consultez le <strong>Manuel Enseignant</strong> pour le détail complet de ces fonctionnalités.</p>
  {fig("review_board", "Tableau de révision — identique pour enseignant et administrateur")}
  {fig("proctor_dashboard", "Surveillance — l'administrateur voit toutes les sessions de l'organisation")}
</section>

<section id="org-management">
  <h2>3. Gestion de l'organisation</h2>
  <div class="callout callout-admin">
    <strong>🔑 Admin uniquement :</strong> Ces fonctionnalités ne sont pas accessibles aux enseignants.
  </div>
  <h3>Accès aux ressources d'autres enseignants</h3>
  <p>Contrairement à l'enseignant qui ne voit que ses propres banques, l'administrateur
  accède à <strong>toutes les banques</strong> créées au sein de l'organisation
  (<code>org_id</code> commun).</p>
  <h3>Substitution de scores</h3>
  <p>L'administrateur peut remplacer tout score IA sur n'importe quelle réponse de dissertation,
  y compris celles des examens créés par d'autres enseignants.</p>
  <h3>Surveillance globale</h3>
  <p>Le tableau de surveillance affiche <strong>toutes les sessions actives</strong> de l'organisation,
  pas uniquement celles liées à vos propres examens.</p>
</section>

<section id="proctor-detail">
  <h2>4. Surveillance avancée</h2>
  {fig("session_detail", "Détail de session — actions admin identiques à celles de l'enseignant")}
  <h3>Actions disponibles (même périmètre que l'enseignant)</h3>
  <ul>
    <li>Acquitter les alertes (toutes sessions de l'organisation)</li>
    <li>Terminer une session (toutes sessions)</li>
    <li>Consulter la timeline d'événements et les captures webcam</li>
  </ul>
</section>

<section id="appendix">
  <h2>5. Annexe — Référence rapide</h2>
  <h3>Rôles JWT et permissions</h3>
  <table class="status-table">
    <thead><tr><th>Rôle JWT</th><th>Label</th><th>Périmètre banques</th><th>Surveillance</th></tr></thead>
    <tbody>
      <tr><td><code>expert</code></td><td>Enseignant</td><td>Ses propres banques</td><td>Ses propres sessions</td></tr>
      <tr><td><code>admin</code></td><td>Administrateur</td><td>Toute l'organisation</td><td>Toute l'organisation</td></tr>
      <tr><td><code>sub_admin</code></td><td>Sous-admin</td><td>Toute l'organisation</td><td>Toute l'organisation</td></tr>
      <tr><td><code>user</code></td><td>Étudiant</td><td>— (lecture seule)</td><td>—</td></tr>
    </tbody>
  </table>
</section>
"""
    has_ph = any("PLACEHOLDER" in v or (not v) for v in shots.values())
    return _html_doc(
        role="admin",
        title="Manuel Administrateur",
        subtitle="Guide pour les administrateurs de l'organisation.",
        badge_class="badge-admin",
        nav_links=[
            ("overview", "Aperçu"),
            ("dashboard", "1. Tableau de bord"),
            ("teacher-features", "2. Fonctionnalités enseignant"),
            ("org-management", "3. Gestion organisation"),
            ("proctor-detail", "4. Surveillance avancée"),
            ("appendix", "5. Annexe"),
        ],
        body_html=body,
        has_placeholders=has_ph,
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print("  Sira Exam — Manual Generator")
    print(f"  Frontend : {args.base_url}")
    print(f"  API      : {args.api_url}")
    print(f"  Output   : {output_dir}")
    print(f"{'='*60}\n")

    api_ok = _api_alive(args.api_url)
    fe_ok  = _frontend_alive(args.base_url)
    print(f"[check]  API  {'✓ online' if api_ok else '✗ offline'}")
    print(f"[check]  Frontend {'✓ online' if fe_ok else '✗ offline'}")

    # Demo data
    demo = DemoData()
    if api_ok and not args.skip_demo:
        try:
            demo = DemoData.setup(args.api_url)
        except Exception as exc:
            print(f"[demo]  ⚠ Demo setup failed ({exc}); proceeding with placeholders")
    elif args.skip_demo:
        demo.bank_id    = args.bank_id    or ""
        demo.test_id    = args.test_id    or ""
        demo.session_id = args.session_id or ""
        # Still need tokens for screenshots
        if api_ok:
            for role, attr in [("expert", "teacher_token"), ("user", "student_token"), ("admin", "admin_token")]:
                try:
                    r = requests.get(f"{args.api_url}/dev/tokens?role={role}", timeout=10)
                    r.raise_for_status()
                    setattr(demo, attr, r.json()["access_token"])
                except Exception:
                    pass

    is_offline = not fe_ok

    # Screenshots
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[error]  playwright not installed — run: pip install playwright && playwright install chromium")
        sys.exit(1)

    teacher_shots: dict[str, str] = {}
    student_shots: dict[str, str] = {}
    admin_shots:   dict[str, str] = {}

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-gpu",
                "--use-fake-ui-for-media-stream",
                "--use-fake-device-for-media-stream",
            ],
        )
        print("\n[browser]  Chromium launched")

        print("\n[shots]  Capturing teacher screenshots ...")
        teacher_shots = capture_teacher_shots(browser, args.base_url, demo, is_offline or not demo.teacher_token)

        print("\n[shots]  Capturing student screenshots ...")
        student_shots = capture_student_shots(browser, args.base_url, demo, is_offline or not demo.student_token)

        print("\n[shots]  Capturing admin screenshots ...")
        admin_shots = capture_admin_shots(browser, args.base_url, demo, teacher_shots)

        browser.close()
    print("[browser]  Chromium closed")

    # Render HTML
    print("\n[render]  Building HTML manuals ...")
    teacher_html = render_teacher(teacher_shots)
    student_html = render_student(student_shots)
    admin_html   = render_admin(admin_shots)

    # Write output
    (output_dir / "teacher-manual.html").write_text(teacher_html, encoding="utf-8")
    (output_dir / "student-manual.html").write_text(student_html, encoding="utf-8")
    (output_dir / "admin-manual.html").write_text(admin_html,   encoding="utf-8")

    sizes = {
        "teacher-manual.html": (output_dir / "teacher-manual.html").stat().st_size,
        "student-manual.html": (output_dir / "student-manual.html").stat().st_size,
        "admin-manual.html":   (output_dir / "admin-manual.html").stat().st_size,
    }

    print(f"\n{'='*60}")
    print("  ✅  MANUALS GENERATED")
    print(f"{'='*60}")
    for fname, size in sizes.items():
        print(f"  {fname:<28}  {size // 1024:>6} KB  →  {output_dir / fname}")
    print()
    if is_offline:
        print("  ⚠  App was offline — screenshots are placeholders.")
        print("     Run again after `docker compose up -d` for real captures.")
    print()


if __name__ == "__main__":
    main()
