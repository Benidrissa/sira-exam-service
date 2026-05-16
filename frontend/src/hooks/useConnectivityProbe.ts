"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export type ConnectivityState = "ONLINE" | "PROBING" | "RECONNECTING" | "DRAINING";

export interface ConnectivityProbeState {
  connectivityState: ConnectivityState;
  offlineSince: Date | null;
  offlineDurationSeconds: number;
  sessionExpired: boolean;
}

const PROBE_URL =
  (process.env.NEXT_PUBLIC_EXAM_API_URL ?? "http://localhost:8001/api/v1").replace(
    /\/api\/v1$/,
    "",
  ) + "/health";

const BACKOFF_DELAYS_MS = [5_000, 10_000, 20_000, 40_000, 60_000];

export function useConnectivityProbe(
  sessionId: string | null,
  sessionToken: string | null,
  onDrain: () => Promise<void>,
): ConnectivityProbeState {
  const [state, setState] = useState<ConnectivityState>("ONLINE");
  const [offlineSince, setOfflineSince] = useState<Date | null>(null);
  const [offlineDurationSeconds, setOfflineDurationSeconds] = useState(0);
  const [sessionExpired, setSessionExpired] = useState(false);

  const probeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const durationTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const backoffIndexRef = useRef(0);
  const stateRef = useRef<ConnectivityState>("ONLINE");
  const drainingRef = useRef(false);

  const updateState = useCallback((next: ConnectivityState) => {
    stateRef.current = next;
    setState(next);
  }, []);

  // ── Stop duration timer ──────────────────────────────────────────────────

  const stopDurationTimer = useCallback(() => {
    if (durationTimerRef.current !== null) {
      clearInterval(durationTimerRef.current);
      durationTimerRef.current = null;
    }
  }, []);

  // ── Schedule next probe with exponential backoff ─────────────────────────

  const scheduleProbe = useCallback(
    (probeFn: () => Promise<void>) => {
      if (probeTimerRef.current !== null) clearTimeout(probeTimerRef.current);
      const delay =
        BACKOFF_DELAYS_MS[Math.min(backoffIndexRef.current, BACKOFF_DELAYS_MS.length - 1)];
      backoffIndexRef.current = Math.min(
        backoffIndexRef.current + 1,
        BACKOFF_DELAYS_MS.length - 1,
      );
      probeTimerRef.current = setTimeout(() => {
        void probeFn();
      }, delay);
    },
    [],
  );

  // ── Probe health endpoint ────────────────────────────────────────────────

  const probe = useCallback(async () => {
    try {
      const resp = await fetch(PROBE_URL, { method: "HEAD", cache: "no-store" });
      if (resp.ok) {
        backoffIndexRef.current = 0;
        // Transition to RECONNECTING — call heartbeat-resume
        updateState("RECONNECTING");
        const API_BASE =
          process.env.NEXT_PUBLIC_EXAM_API_URL ?? "http://localhost:8001/api/v1";
        const cookieToken =
          typeof document !== "undefined"
            ? document.cookie.match(/(?:^|; )access_token=([^;]*)/)?.[1]
            : null;
        const headers: Record<string, string> = {
          "Content-Type": "application/json",
          "X-Session-Token": sessionToken ?? "",
        };
        if (cookieToken) headers["Authorization"] = `Bearer ${decodeURIComponent(cookieToken)}`;

        const resumeResp = await fetch(
          `${API_BASE}/proctor/sessions/${sessionId}/heartbeat-resume`,
          {
            method: "POST",
            headers,
            body: JSON.stringify({}),
            credentials: "include",
          },
        );

        if (resumeResp.status === 409) {
          setSessionExpired(true);
          updateState("ONLINE");
          return;
        }
        if (resumeResp.ok) {
          updateState("DRAINING");
          if (!drainingRef.current) {
            drainingRef.current = true;
            try {
              await onDrain();
            } catch {
              // drain failed — go back to PROBING
              drainingRef.current = false;
              updateState("PROBING");
              scheduleProbe(probe);
              return;
            }
            drainingRef.current = false;
          }
          stopDurationTimer();
          setOfflineSince(null);
          setOfflineDurationSeconds(0);
          updateState("ONLINE");
          return;
        }
      }
    } catch {
      // network still down — fall through to reschedule
    }
    // Still offline — schedule next probe with backoff
    scheduleProbe(probe);
  }, [sessionId, sessionToken, onDrain, updateState, scheduleProbe, stopDurationTimer]);

  // ── Go offline ───────────────────────────────────────────────────────────

  const goOffline = useCallback(() => {
    if (stateRef.current !== "ONLINE") return;
    setOfflineSince(new Date());
    updateState("PROBING");
    backoffIndexRef.current = 0;
    durationTimerRef.current = setInterval(() => {
      setOfflineDurationSeconds((s) => s + 1);
    }, 1_000);
    scheduleProbe(probe);
  }, [updateState, scheduleProbe, probe]);

  // ── DOM events ───────────────────────────────────────────────────────────

  useEffect(() => {
    if (!sessionId || !sessionToken) return;

    const handleOffline = () => goOffline();
    const handleOnline = () => {
      if (stateRef.current === "PROBING") {
        backoffIndexRef.current = 0;
        if (probeTimerRef.current !== null) clearTimeout(probeTimerRef.current);
        void probe();
      }
    };

    window.addEventListener("offline", handleOffline);
    window.addEventListener("online", handleOnline);

    return () => {
      window.removeEventListener("offline", handleOffline);
      window.removeEventListener("online", handleOnline);
      if (probeTimerRef.current !== null) clearTimeout(probeTimerRef.current);
      stopDurationTimer();
    };
  }, [sessionId, sessionToken, goOffline, probe, stopDurationTimer]);

  return { connectivityState: state, offlineSince, offlineDurationSeconds, sessionExpired };
}
