"use client";

import { useRef, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import {
  getSessionDetail,
  acknowledgeAlert,
  terminateSessionAsProctor,
} from "@/lib/api";
import type { ProctorAlert, SessionEvent, SessionSnapshot } from "@/types/exam";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function relativeTime(iso: string): string {
  const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  return `${Math.floor(diff / 3600)}h ago`;
}

const severityStyles: Record<ProctorAlert["severity"], string> = {
  info: "bg-blue-100 text-blue-700",
  low: "bg-gray-100 text-gray-600",
  medium: "bg-yellow-100 text-yellow-700",
  high: "bg-orange-100 text-orange-700",
  critical: "bg-red-100 text-red-700",
};

// ---------------------------------------------------------------------------
// Alert row
// ---------------------------------------------------------------------------
function AlertRow({
  alert,
  onAcknowledge,
  isAcknowledging,
}: {
  alert: ProctorAlert;
  onAcknowledge: (id: string) => void;
  isAcknowledging: boolean;
}) {
  return (
    <div
      className={`flex items-start gap-3 rounded-lg border p-3 transition
        ${alert.acknowledged ? "opacity-50" : "border-orange-200 bg-orange-50"}`}>
      <span
        className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-semibold ${severityStyles[alert.severity]}`}>
        {alert.severity}
      </span>
      <div className="flex-1 min-w-0">
        <p className="text-sm text-gray-800">{alert.message}</p>
        <p className="text-xs text-gray-400 mt-0.5">{relativeTime(alert.created_at)}</p>
      </div>
      {!alert.acknowledged && (
        <button
          onClick={() => onAcknowledge(alert.id)}
          disabled={isAcknowledging}
          className="shrink-0 rounded bg-gray-700 px-2.5 py-1 text-xs text-white hover:bg-gray-900 disabled:opacity-40 transition">
          Ack
        </button>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Snapshot card
// ---------------------------------------------------------------------------
function SnapshotCard({ snapshot }: { snapshot: SessionSnapshot }) {
  return (
    <div className="relative rounded-lg overflow-hidden bg-gray-100 aspect-video">
      {snapshot.download_url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={snapshot.download_url}
          alt="Snapshot"
          className="w-full h-full object-cover"
        />
      ) : (
        <div className="flex items-center justify-center h-full text-gray-400 text-xs">
          Unavailable
        </div>
      )}
      {snapshot.violation_detected && (
        <div className="absolute top-1 right-1 rounded-full bg-red-500 h-3 w-3 shadow" title="Violation detected" />
      )}
      <p className="absolute bottom-0 left-0 right-0 bg-black/50 text-white text-xs px-1.5 py-0.5">
        {relativeTime(snapshot.taken_at)}
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Event timeline entry
// ---------------------------------------------------------------------------
function EventEntry({ event }: { event: SessionEvent }) {
  const dotColor =
    event.severity === "critical" || event.severity === "high"
      ? "bg-red-500"
      : event.severity === "medium"
        ? "bg-yellow-500"
        : "bg-gray-400";

  return (
    <div className="flex gap-3">
      <div className="flex flex-col items-center">
        <div className={`mt-1.5 h-2.5 w-2.5 rounded-full shrink-0 ${dotColor}`} />
        <div className="flex-1 w-px bg-gray-200 mt-1" />
      </div>
      <div className="pb-3 min-w-0">
        <p className="text-sm text-gray-700 font-medium">{event.event_type}</p>
        <p className="text-xs text-gray-400">{relativeTime(event.occurred_at)}</p>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Terminate dialog
// ---------------------------------------------------------------------------
function TerminateDialog({
  onConfirm,
  onCancel,
  loading,
}: {
  onConfirm: (reason: string) => void;
  onCancel: () => void;
  loading: boolean;
}) {
  const [reason, setReason] = useState("");

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-sm bg-white rounded-2xl shadow-xl p-6 space-y-4">
        <h3 className="text-lg font-bold text-red-600">Terminate Session</h3>
        <p className="text-sm text-gray-600">
          This will immediately end the student&apos;s exam session. Please provide a reason.
        </p>
        <textarea
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          rows={3}
          placeholder="Reason for termination…"
          className="w-full rounded-lg border border-gray-300 p-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-red-400 resize-none"
        />
        <div className="flex gap-3">
          <button
            onClick={onCancel}
            className="flex-1 rounded-lg border py-2 text-sm hover:bg-gray-50 transition">
            Cancel
          </button>
          <button
            disabled={!reason.trim() || loading}
            onClick={() => onConfirm(reason.trim())}
            className="flex-1 rounded-lg bg-red-600 py-2 text-sm font-semibold text-white hover:bg-red-700 disabled:opacity-40 transition">
            {loading ? "Terminating…" : "Terminate"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Session detail page
// ---------------------------------------------------------------------------
export default function SessionDetailPage() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const queryClient = useQueryClient();
  const [showTerminate, setShowTerminate] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  const { data: session, isLoading, isError, error } = useQuery({
    queryKey: ["session", sessionId],
    queryFn: () => getSessionDetail(sessionId),
    refetchInterval: (query) =>
      query.state.data?.status === "active" ? 5_000 : false,
  });

  // WebSocket for live alerts while session is active
  useEffect(() => {
    if (!session || session.status !== "active") return;

    const wsBase = (process.env.NEXT_PUBLIC_EXAM_API_URL ?? "http://localhost:8001/api/v1")
      .replace(/^http/, "ws")
      .replace(/\/api\/v1$/, "");
    const ws = new WebSocket(`${wsBase}/ws/proctor/${sessionId}`);

    ws.onmessage = (e: MessageEvent<string>) => {
      try {
        const msg = JSON.parse(e.data) as { type?: string };
        if (msg.type === "violation") {
          queryClient.invalidateQueries({ queryKey: ["session", sessionId] });
        }
      } catch {
        // ignore parse errors
      }
    };

    wsRef.current = ws;
    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [session?.status, sessionId, queryClient]);

  const ackMutation = useMutation({
    mutationFn: acknowledgeAlert,
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["session", sessionId] }),
  });

  const terminateMutation = useMutation({
    mutationFn: (reason: string) => terminateSessionAsProctor(sessionId, reason),
    onSuccess: () => {
      setShowTerminate(false);
      queryClient.invalidateQueries({ queryKey: ["session", sessionId] });
    },
  });

  if (isLoading) return <p className="p-8 text-sm text-gray-400">Loading session…</p>;
  if (isError) return <p className="p-8 text-sm text-red-600">Error: {String(error)}</p>;
  if (!session) return null;

  const recentSnapshots = [...session.snapshots]
    .sort((a, b) => new Date(b.taken_at).getTime() - new Date(a.taken_at).getTime())
    .slice(0, 10);

  const sortedEvents = [...session.events].sort(
    (a, b) => new Date(b.occurred_at).getTime() - new Date(a.occurred_at).getTime(),
  );

  return (
    <>
      {showTerminate && (
        <TerminateDialog
          onConfirm={(r) => terminateMutation.mutate(r)}
          onCancel={() => setShowTerminate(false)}
          loading={terminateMutation.isPending}
        />
      )}

      <main className="max-w-7xl mx-auto p-6 space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <Link href="/proctor/dashboard" className="text-sm text-blue-600 hover:underline">
                ← Dashboard
              </Link>
            </div>
            <h1 className="text-2xl font-bold">
              Session{" "}
              <span className="font-mono text-lg text-gray-500">
                {sessionId.slice(0, 8)}…
              </span>
            </h1>
            <p className="text-sm text-gray-500 mt-0.5">
              Student: <span className="font-mono">{session.user_id}</span> ·
              Started {relativeTime(session.started_at)}
            </p>
          </div>
          {session.status === "active" && (
            <button
              onClick={() => setShowTerminate(true)}
              className="rounded-lg bg-red-600 px-4 py-2 text-sm font-semibold text-white hover:bg-red-700 transition">
              Terminate session
            </button>
          )}
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Left: session info + alerts */}
          <div className="space-y-4">
            <div className="rounded-xl border bg-white p-4 space-y-2">
              <h2 className="font-semibold text-sm text-gray-700 uppercase tracking-wide">
                Session Info
              </h2>
              <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
                <dt className="text-gray-500">Status</dt>
                <dd className="font-medium capitalize">{session.status}</dd>
                <dt className="text-gray-500">Missed heartbeats</dt>
                <dd className="font-medium">{session.consecutive_missed_heartbeats}</dd>
                <dt className="text-gray-500">Unacked alerts</dt>
                <dd className={`font-medium ${session.unacked_alert_count > 0 ? "text-red-600" : ""}`}>
                  {session.unacked_alert_count}
                </dd>
              </dl>
            </div>

            <div className="rounded-xl border bg-white p-4 space-y-3">
              <h2 className="font-semibold text-sm text-gray-700 uppercase tracking-wide">
                Alerts ({session.alerts.length})
              </h2>
              {session.alerts.length === 0 && (
                <p className="text-sm text-gray-400">No alerts.</p>
              )}
              <div className="space-y-2 max-h-80 overflow-y-auto pr-1">
                {[...session.alerts]
                  .sort(
                    (a, b) =>
                      new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
                  )
                  .map((alert) => (
                    <AlertRow
                      key={alert.id}
                      alert={alert}
                      onAcknowledge={(id) => ackMutation.mutate(id)}
                      isAcknowledging={ackMutation.isPending}
                    />
                  ))}
              </div>
            </div>
          </div>

          {/* Right: snapshot gallery */}
          <div className="rounded-xl border bg-white p-4 space-y-3">
            <h2 className="font-semibold text-sm text-gray-700 uppercase tracking-wide">
              Recent Snapshots ({recentSnapshots.length})
            </h2>
            {recentSnapshots.length === 0 && (
              <p className="text-sm text-gray-400">No snapshots yet.</p>
            )}
            <div className="grid grid-cols-2 gap-2">
              {recentSnapshots.map((s) => (
                <SnapshotCard key={s.id} snapshot={s} />
              ))}
            </div>
          </div>
        </div>

        {/* Event timeline */}
        <div className="rounded-xl border bg-white p-4 space-y-3">
          <h2 className="font-semibold text-sm text-gray-700 uppercase tracking-wide">
            Event Timeline ({session.events.length})
          </h2>
          {sortedEvents.length === 0 && (
            <p className="text-sm text-gray-400">No events recorded.</p>
          )}
          <div className="max-h-64 overflow-y-auto">
            {sortedEvents.map((ev) => (
              <EventEntry key={ev.id} event={ev} />
            ))}
          </div>
        </div>
      </main>
    </>
  );
}
