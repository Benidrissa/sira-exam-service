"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getAuditLog } from "@/lib/api";
import type { ReviewAuditLogEntry } from "@/types/exam";
import { Badge } from "@/components/ui/badge";
import { ChevronDown, ChevronRight, History } from "lucide-react";

function ActionBadge({ action }: { action: string }) {
  const colors: Record<string, string> = {
    human_score_applied: "bg-blue-100 text-blue-800",
    complaint_resolved: "bg-orange-100 text-orange-800",
  };
  return (
    <span className={`inline-flex items-center rounded px-2 py-0.5 text-xs font-medium ${colors[action] ?? "bg-gray-100 text-gray-700"}`}>
      {action.replace(/_/g, " ")}
    </span>
  );
}

function ScoreDelta({ entry }: { entry: ReviewAuditLogEntry }) {
  const oldScore = entry.old_values?.human_score as number | null | undefined;
  const newScore = entry.new_values?.human_score as number | null | undefined;
  if (newScore == null) return <span className="text-muted-foreground">—</span>;
  if (oldScore == null) return <span className="text-green-700 font-medium">{newScore}</span>;
  return (
    <span>
      <span className="line-through text-muted-foreground mr-1">{oldScore}</span>
      <span className="text-blue-700 font-medium">{newScore}</span>
    </span>
  );
}

export function AuditLogPanel({ testId }: { testId: string }) {
  const [open, setOpen] = useState(false);

  const { data: entries, isLoading } = useQuery<ReviewAuditLogEntry[]>({
    queryKey: ["audit-log", testId],
    queryFn: () => getAuditLog(testId),
    enabled: open,
    refetchInterval: open ? 30_000 : false,
    staleTime: 20_000,
  });

  return (
    <div className="border rounded-lg mt-6">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between px-4 py-3 text-sm font-medium text-left hover:bg-muted/50 transition-colors"
      >
        <span className="flex items-center gap-2">
          <History className="h-4 w-4 text-muted-foreground" />
          Review Audit Log
          {entries && entries.length > 0 && (
            <Badge variant="secondary">{entries.length}</Badge>
          )}
        </span>
        {open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
      </button>

      {open && (
        <div className="border-t">
          {isLoading ? (
            <p className="p-4 text-sm text-muted-foreground">Loading…</p>
          ) : !entries || entries.length === 0 ? (
            <p className="p-4 text-sm text-muted-foreground">No review changes recorded yet.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/30 text-xs text-muted-foreground">
                    <th className="px-4 py-2 text-left">When</th>
                    <th className="px-4 py-2 text-left">Actor</th>
                    <th className="px-4 py-2 text-left">Role</th>
                    <th className="px-4 py-2 text-left">Action</th>
                    <th className="px-4 py-2 text-left">Score (old → new)</th>
                  </tr>
                </thead>
                <tbody>
                  {entries.map((e) => (
                    <tr key={e.id} className="border-b last:border-0 hover:bg-muted/20">
                      <td className="px-4 py-2 whitespace-nowrap text-muted-foreground">
                        {new Date(e.occurred_at).toLocaleString()}
                      </td>
                      <td className="px-4 py-2 font-mono text-xs">{e.actor_id.slice(0, 8)}</td>
                      <td className="px-4 py-2">
                        <Badge variant="outline" className="text-xs">{e.actor_role}</Badge>
                      </td>
                      <td className="px-4 py-2">
                        <ActionBadge action={e.action} />
                      </td>
                      <td className="px-4 py-2">
                        <ScoreDelta entry={e} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
