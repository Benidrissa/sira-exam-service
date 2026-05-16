"use client";

import { useCallback, useEffect, useRef, useState } from "react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface LockdownEvent {
  event_type: string;
  severity: "info" | "low" | "medium" | "high" | "critical";
  occurred_at: string;
  payload?: Record<string, unknown>;
}

export interface LockdownShellState {
  fullscreenActive: boolean;
  fullscreenCountdown: number;
  violationCount: number;
}

const API_BASE =
  process.env.NEXT_PUBLIC_EXAM_API_URL ?? "http://localhost:8001/api/v1";

const FULLSCREEN_COUNTDOWN_SEC = 10;
const BATCH_FLUSH_MS = 5_000;
const FORCE_TERMINATE_THRESHOLD = 5;

// ---------------------------------------------------------------------------
// Auth helpers
// ---------------------------------------------------------------------------

function readCookieToken(): string | null {
  if (typeof document === "undefined") return null;
  const m = document.cookie.match(/(?:^|; )access_token=([^;]*)/);
  return m ? decodeURIComponent(m[1]) : null;
}

function getStudentSubFromCookie(): string {
  const token = readCookieToken();
  if (!token) return "unknown";
  try {
    const payload = token.split(".")[1];
    const decoded = JSON.parse(atob(payload.replace(/-/g, "+").replace(/_/g, "/")));
    return (decoded.sub as string) ?? "unknown";
  } catch {
    return "unknown";
  }
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useLockdownShell(
  enabled: boolean,
  sessionId: string | null,
  sessionToken: string | null,
  onForceTerminate: () => void,
): LockdownShellState {
  const [fullscreenActive, setFullscreenActive] = useState<boolean>(
    () => (typeof document !== "undefined" ? !!document.fullscreenElement : true),
  );
  const [fullscreenCountdown, setFullscreenCountdown] = useState(0);
  const [violationCount, setViolationCount] = useState(0);

  const consecutiveExits = useRef(0);
  const countdownRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const bufferRef = useRef<LockdownEvent[]>([]);
  const flushTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const blurStartRef = useRef<number | null>(null);
  const watermarkRef = useRef<HTMLDivElement | null>(null);
  const printStyleRef = useRef<HTMLStyleElement | null>(null);
  const onTerminateRef = useRef(onForceTerminate);
  useEffect(() => {
    onTerminateRef.current = onForceTerminate;
  }, [onForceTerminate]);

  // ---------------------------------------------------------------------------
  // Event flush
  // ---------------------------------------------------------------------------

  const flushEvents = useCallback(async () => {
    if (!sessionId || !sessionToken || bufferRef.current.length === 0) return;
    const batch = bufferRef.current.splice(0);
    const token = readCookieToken();
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      "X-Session-Token": sessionToken,
    };
    if (token) headers["Authorization"] = `Bearer ${token}`;
    try {
      await fetch(`${API_BASE}/proctor/sessions/${sessionId}/events/batch`, {
        method: "POST",
        headers,
        body: JSON.stringify({ events: batch }),
        keepalive: true,
        credentials: "include",
      });
    } catch {
      bufferRef.current.unshift(...batch);
    }
  }, [sessionId, sessionToken]);

  const enqueue = useCallback(
    (event: LockdownEvent, immediate = false) => {
      setViolationCount((n) => n + 1);
      bufferRef.current.push(event);
      if (immediate || event.severity === "high" || event.severity === "critical") {
        void flushEvents();
      }
    },
    [flushEvents],
  );

  // ---------------------------------------------------------------------------
  // Watermark
  // ---------------------------------------------------------------------------

  const injectWatermark = useCallback((sub: string, sid: string) => {
    if (watermarkRef.current || typeof document === "undefined") return;
    const div = document.createElement("div");
    div.id = "exam-watermark";
    div.setAttribute("aria-hidden", "true");
    div.style.cssText =
      "position:fixed;inset:0;pointer-events:none;z-index:9999;" +
      "display:flex;align-items:center;justify-content:center;" +
      "opacity:0.07;font-size:clamp(0.9rem,2vw,1.4rem);font-family:monospace;" +
      "color:#000;white-space:nowrap;transform:rotate(-30deg);user-select:none;";
    div.textContent = `${sub} · ${sid}`;
    document.body.appendChild(div);
    watermarkRef.current = div;
  }, []);

  const removeWatermark = useCallback(() => {
    watermarkRef.current?.remove();
    watermarkRef.current = null;
  }, []);

  // ---------------------------------------------------------------------------
  // Print CSS
  // ---------------------------------------------------------------------------

  const injectPrintCSS = useCallback(() => {
    if (printStyleRef.current || typeof document === "undefined") return;
    const style = document.createElement("style");
    style.id = "exam-print-block";
    style.textContent =
      "@media print { body * { display: none !important; } " +
      "body::before { content: 'Printing is not allowed during this exam.'; " +
      "display: block !important; font-size: 2rem; text-align: center; margin-top: 40vh; } }";
    document.head.appendChild(style);
    printStyleRef.current = style;
  }, []);

  const removePrintCSS = useCallback(() => {
    printStyleRef.current?.remove();
    printStyleRef.current = null;
  }, []);

  // ---------------------------------------------------------------------------
  // Countdown
  // ---------------------------------------------------------------------------

  const clearCountdown = useCallback(() => {
    if (countdownRef.current !== null) {
      clearInterval(countdownRef.current);
      countdownRef.current = null;
    }
    setFullscreenCountdown(0);
  }, []);

  const startCountdown = useCallback(() => {
    clearCountdown();
    setFullscreenCountdown(FULLSCREEN_COUNTDOWN_SEC);
    let remaining = FULLSCREEN_COUNTDOWN_SEC;
    countdownRef.current = setInterval(() => {
      remaining -= 1;
      setFullscreenCountdown(remaining);
      if (remaining <= 0) {
        if (countdownRef.current !== null) clearInterval(countdownRef.current);
        countdownRef.current = null;
        if (consecutiveExits.current >= FORCE_TERMINATE_THRESHOLD) {
          onTerminateRef.current();
        }
      }
    }, 1_000);
  }, [clearCountdown]);

  // ---------------------------------------------------------------------------
  // Main effect
  // ---------------------------------------------------------------------------

  useEffect(() => {
    if (!enabled) return;

    const sub = getStudentSubFromCookie();
    const sid = sessionId ?? "no-session";
    injectWatermark(sub, sid);
    injectPrintCSS();
    document.body.style.userSelect = "none";

    // Block context menu
    const blockCtx = (e: MouseEvent) => e.preventDefault();
    document.addEventListener("contextmenu", blockCtx);

    // Block new windows from JS
    const origOpen = window.open.bind(window);
    window.open = (..._args: Parameters<typeof window.open>) => null;

    // Block getDisplayMedia
    const origGDM = navigator.mediaDevices?.getDisplayMedia?.bind(
      navigator.mediaDevices,
    );
    if (navigator.mediaDevices?.getDisplayMedia) {
      navigator.mediaDevices.getDisplayMedia = (async () => {
        enqueue(
          {
            event_type: "screen_capture_attempt",
            severity: "critical",
            occurred_at: new Date().toISOString(),
          },
          true,
        );
        return Promise.reject(
          new DOMException("Not allowed by exam lockdown", "NotAllowedError"),
        );
      }) as typeof navigator.mediaDevices.getDisplayMedia;
    }

    // Extended display check
    const screenExt = (window.screen as Screen & { isExtended?: boolean })
      .isExtended;
    if (screenExt === true) {
      enqueue(
        {
          event_type: "extended_display_detected",
          severity: "high",
          occurred_at: new Date().toISOString(),
          payload: { isExtended: true },
        },
        true,
      );
    }

    // Keyboard intercept
    const blockKeys = (e: KeyboardEvent) => {
      const { ctrlKey: ctrl, metaKey: meta, shiftKey: shift, altKey: alt, key } = e;
      const blocked =
        key === "F12" ||
        (ctrl && shift && (key === "I" || key === "J" || key === "C")) ||
        (alt && key === "Tab") ||
        (ctrl && (key === "t" || key === "n" || key === "p")) ||
        (meta && (key === "t" || key === "n" || key === "p")) ||
        key === "PrintScreen" ||
        (shift && key === "PrintScreen") ||
        (alt && key === "PrintScreen") ||
        (!meta && alt && key === "F4");

      if (blocked) {
        e.preventDefault();
        e.stopPropagation();
        const rawKey = e.key;
        const isScreenshot =
          rawKey === "PrintScreen" ||
          (shift && rawKey === "PrintScreen") ||
          (alt && rawKey === "PrintScreen");
        const isPrint = (ctrl || meta) && rawKey === "p";
        if (isScreenshot) {
          enqueue(
            {
              event_type: "screenshot_key_pressed",
              severity: "high",
              occurred_at: new Date().toISOString(),
              payload: { key: rawKey, shift, alt },
            },
            true,
          );
        } else if (isPrint) {
          enqueue({
            event_type: "print_attempted",
            severity: "medium",
            occurred_at: new Date().toISOString(),
          });
        }
      }
    };
    document.addEventListener("keydown", blockKeys, true);

    // Fullscreen change
    const onFsChange = () => {
      if (document.fullscreenElement) {
        setFullscreenActive(true);
        clearCountdown();
        consecutiveExits.current = 0;
        enqueue({
          event_type: "fullscreen_restored",
          severity: "info",
          occurred_at: new Date().toISOString(),
        });
      } else {
        setFullscreenActive(false);
        consecutiveExits.current += 1;
        startCountdown();
        enqueue(
          {
            event_type: "fullscreen_exit",
            severity: "high",
            occurred_at: new Date().toISOString(),
            payload: { consecutive_count: consecutiveExits.current },
          },
          true,
        );
      }
    };
    document.addEventListener("fullscreenchange", onFsChange);

    // Visibility change
    const onVis = () => {
      enqueue({
        event_type: document.hidden ? "tab_hidden" : "tab_visible",
        severity: document.hidden ? "medium" : "info",
        occurred_at: new Date().toISOString(),
      });
    };
    document.addEventListener("visibilitychange", onVis);

    // Blur / focus
    const onBlur = () => {
      blurStartRef.current = Date.now();
      enqueue({
        event_type: "window_blur",
        severity: "medium",
        occurred_at: new Date().toISOString(),
      });
    };
    const onFocus = () => {
      const duration =
        blurStartRef.current !== null
          ? Math.round((Date.now() - blurStartRef.current) / 1_000)
          : null;
      blurStartRef.current = null;
      enqueue({
        event_type: "window_focus_restored",
        severity: "info",
        occurred_at: new Date().toISOString(),
        payload: duration !== null ? { away_seconds: duration } : undefined,
      });
    };
    window.addEventListener("blur", onBlur);
    window.addEventListener("focus", onFocus);

    // beforeunload — use sendBeacon for synchronous flush
    const onUnload = () => {
      if (sessionId && sessionToken && bufferRef.current.length > 0) {
        const token = readCookieToken();
        const blob = new Blob(
          [JSON.stringify({ events: bufferRef.current })],
          { type: "application/json" },
        );
        navigator.sendBeacon(
          `${API_BASE}/proctor/sessions/${sessionId}/events/batch`,
          blob,
        );
        bufferRef.current = [];
        // token is available for sendBeacon via cookie header automatically
        void token; // suppress unused var warning
      }
    };
    window.addEventListener("beforeunload", onUnload);

    // Periodic flush
    flushTimerRef.current = setInterval(() => {
      void flushEvents();
    }, BATCH_FLUSH_MS);

    return () => {
      document.removeEventListener("contextmenu", blockCtx);
      document.removeEventListener("keydown", blockKeys, true);
      document.removeEventListener("fullscreenchange", onFsChange);
      document.removeEventListener("visibilitychange", onVis);
      window.removeEventListener("blur", onBlur);
      window.removeEventListener("focus", onFocus);
      window.removeEventListener("beforeunload", onUnload);
      clearCountdown();
      if (flushTimerRef.current !== null) {
        clearInterval(flushTimerRef.current);
        flushTimerRef.current = null;
      }
      window.open = origOpen;
      if (origGDM && navigator.mediaDevices) {
        navigator.mediaDevices.getDisplayMedia = origGDM;
      }
      removeWatermark();
      removePrintCSS();
      document.body.style.userSelect = "";
      void flushEvents();
    };
  }, [
    enabled,
    sessionId,
    sessionToken,
    enqueue,
    flushEvents,
    injectWatermark,
    injectPrintCSS,
    removeWatermark,
    removePrintCSS,
    clearCountdown,
    startCountdown,
  ]);

  return { fullscreenActive, fullscreenCountdown, violationCount };
}
