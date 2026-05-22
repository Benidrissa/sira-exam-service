"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { listActiveSessions } from "@/lib/api";
import type { SessionSummary } from "@/types/exam";
import { Skeleton } from "@/components/ui/skeleton";
import { formatError } from "@/lib/formatError";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function relativeTime(iso: string): string {
  const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  return `${Math.floor(diff / 3600)}h ago`;
}

function StatusBadge({ status }: { status: SessionSummary["status"] }) {
  const styles: Record<SessionSummary["status"], string> = {
    active: "bg-green-100 text-green-700",
    disconnected: "bg-amber-100 text-amber-700",
    terminated: "bg-red-100 text-red-700",
    expired: "bg-yellow-100 text-yellow-700",
    completed: "bg-gray-100 text-gray-600",
  };
  return (
    <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${styles[status]}`}>
      {status}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Session card
// ---------------------------------------------------------------------------
function SessionCard({ session }: { session: SessionSummary }) {
  return (
    <div className="relative rounded-xl border bg-white shadow-sm p-4 space-y-3 hover:shadow-md transition">
      {/* Violation badge */}
      {session.unacked_alert_count > 0 && (
        <div className="absolute -top-2 -right-2 flex h-6 w-6 items-center justify-center rounded-full bg-red-500 text-xs font-bold text-white shadow">
          {session.unacked_alert_count}
        </div>
      )}

      {/* Snapshot preview */}
      <div className="rounded-lg overflow-hidden bg-gray-100 aspect-video">
        {session.latest_snapshot_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={session.latest_snapshot_url}
            alt="Latest snapshot"
            className="w-full h-full object-cover"
          />
        ) : (
          <div className="flex items-center justify-center h-full text-gray-400 text-xs">
            No snapshot yet
          </div>
        )}
      </div>

      {/* Session info */}
      <div className="space-y-1">
        <div className="flex items-center justify-between gap-2">
          <p className="text-sm font-medium truncate">
            Student: <span className="font-mono text-xs text-gray-500">{session.user_id}</span>
          </p>
          <StatusBadge status={session.status} />
        </div>
        <p className="text-xs text-gray-400">Started {relativeTime(session.started_at)}</p>
        {session.consecutive_missed_heartbeats > 0 && (
          <p className="text-xs text-orange-600 font-medium">
            {session.consecutive_missed_heartbeats} missed heartbeat
            {session.consecutive_missed_heartbeats > 1 ? "s" : ""}
          </p>
        )}
        {/* Offline / gap badge — E3-8 */}
        {session.status === "disconnected" && session.disconnected_at && (
          <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-700 animate-pulse">
            Offline since {new Date(session.disconnected_at).toLocaleTimeString()}
          </span>
        )}
        {session.status !== "disconnected" && (session.offline_event_count ?? 0) > 0 && (
          <span className="inline-flex items-center rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-700">
            {session.total_offline_duration_s
              ? `Gap: ${Math.round(session.total_offline_duration_s / 60)}m`
              : "Network gap"}
          </span>
        )}
      </div>

      <Link
        href={`/proctor/sessions/${session.id}`}
        className="block w-full text-center rounded-lg bg-blue-600 py-1.5 text-xs font-semibold text-white hover:bg-blue-700 transition">
        View
      </Link>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Dashboard
// ---------------------------------------------------------------------------
export default function ProctorDashboardPage() {
  const { data: sessions, isLoading, isError, error } = useQuery({
    queryKey: ["proctor-sessions"],
    queryFn: listActiveSessions,
    refetchInterval: 5_000,
  });

  return (
    <main className="max-w-7xl mx-auto p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Proctor Dashboard</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            Live sessions — refreshes every 5 seconds
          </p>
        </div>
        {sessions && (
          <div className="flex items-center gap-2">
            <span className="h-2 w-2 rounded-full bg-green-400 animate-pulse" />
            <span className="text-sm text-gray-600">{sessions.length} active</span>
          </div>
        )}
      </div>

      {/* States */}
      {isLoading && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {[1, 2, 3, 4].map(i => <Skeleton key={i} className="h-64 w-full rounded-xl" />)}
        </div>
      )}

      {isError && (
        <p className="text-sm text-red-600 py-4">{formatError(error)}</p>
      )}

      {sessions && sessions.length === 0 && (
        <div className="py-16 text-center space-y-2">
          <p className="text-gray-400 text-sm">No active sessions at the moment.</p>
          <p className="text-xs text-gray-300">Dashboard auto-refreshes every 5 seconds.</p>
        </div>
      )}

      {/* Session grid — sorted by unacked alerts descending */}
      {sessions && sessions.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {[...sessions].sort((a, b) => (b.unacked_alert_count ?? 0) - (a.unacked_alert_count ?? 0)).map((s) => (
            <SessionCard key={s.id} session={s} />
          ))}
        </div>
      )}
    </main>
  );
}
