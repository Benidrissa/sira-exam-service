"use client";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { listTestSubmissions, batchValidate, validateAttempt } from "@/lib/api";
import type { AttemptSubmissionSummary } from "@/types/exam";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import Link from "next/link";
import { useParams } from "next/navigation";

function statusBadge(s: string) {
  return s === "validated"
    ? <Badge className="bg-green-100 text-green-700">Validated</Badge>
    : <Badge variant="outline">Pending</Badge>;
}

export default function SubmissionsPage() {
  const params = useParams();
  const testId = params.testId as string;
  const locale = params.locale as string;
  const qc = useQueryClient();
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [overrideScore, setOverrideScore] = useState("");
  const [batchMsg, setBatchMsg] = useState<string | null>(null);

  const { data: submissions, isLoading, error } = useQuery({
    queryKey: ["submissions", testId],
    queryFn: () => listTestSubmissions(testId),
    staleTime: 10_000,
  });

  const batchMutation = useMutation({
    mutationFn: () => batchValidate(testId, {
      attempt_ids: [...selected],
      ...(overrideScore ? { override_score: parseFloat(overrideScore) } : {}),
    }),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ["submissions", testId] });
      setSelected(new Set());
      setBatchMsg(`Validated ${res.validated_count} attempt(s).${res.errors.length ? ` ${res.errors.length} error(s).` : ""}`);
    },
    onError: (e) => setBatchMsg(`Error: ${String(e)}`),
  });

  const validateMutation = useMutation({
    mutationFn: (attemptId: string) => validateAttempt(attemptId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["submissions", testId] }),
  });

  if (isLoading) return <div className="p-8">Loading…</div>;
  if (error) return <p className="p-8 text-destructive">{String(error)}</p>;

  const toggle = (id: string) => {
    const next = new Set(selected);
    next.has(id) ? next.delete(id) : next.add(id);
    setSelected(next);
  };

  return (
    <main className="max-w-5xl mx-auto p-8 space-y-6">
      <h1 className="text-2xl font-bold">Student Submissions</h1>

      {/* Batch controls */}
      {selected.size > 0 && (
        <Card>
          <CardContent className="flex items-center gap-4 py-4">
            <span className="text-sm font-medium">{selected.size} selected</span>
            <Input type="number" placeholder="Override score (optional, 0-100)" value={overrideScore}
              onChange={e => setOverrideScore(e.target.value)} className="w-56" />
            <Button onClick={() => batchMutation.mutate()} disabled={batchMutation.isPending}>
              {batchMutation.isPending ? "Validating…" : "Batch Validate"}
            </Button>
            <Button variant="outline" onClick={() => setSelected(new Set())}>Clear</Button>
          </CardContent>
        </Card>
      )}

      {batchMsg && <p className="text-sm text-green-700">{batchMsg}</p>}

      <div className="space-y-3">
        {submissions?.length === 0 && <p className="text-muted-foreground">No submissions yet.</p>}
        {submissions?.map((s: AttemptSubmissionSummary) => (
          <Card key={s.attempt_id} className={selected.has(s.attempt_id) ? "ring-2 ring-primary" : ""}>
            <CardContent className="flex items-center gap-4 py-4">
              <input type="checkbox" checked={selected.has(s.attempt_id)}
                onChange={() => toggle(s.attempt_id)} className="h-4 w-4" />
              <div className="flex-1 min-w-0">
                <p className="font-mono text-xs text-muted-foreground truncate">{s.user_id}</p>
                <p className="text-sm">{new Date(s.attempted_at).toLocaleString()}</p>
              </div>
              <div className="text-sm space-y-1 text-right">
                <p>MCQ: <span className="font-medium">{s.mcq_score?.toFixed(1) ?? "—"}</span></p>
                <p>Total: <span className="font-medium">{s.total_score?.toFixed(1) ?? "—"}</span></p>
              </div>
              <div className="text-xs space-y-1">
                <p className="text-amber-600">Pending: {s.pending_count}</p>
                <p className="text-blue-600">AI scored: {s.ai_scored_count}</p>
                <p className="text-green-600">Reviewed: {s.human_reviewed_count}</p>
              </div>
              {statusBadge(s.validation_status)}
              <div className="flex gap-2">
                <Link href={`/${locale}/exams/${testId}/submissions/${s.attempt_id}`}>
                  <Button size="sm" variant="outline">Review →</Button>
                </Link>
                {s.validation_status === "pending" && (
                  <Button size="sm" onClick={() => validateMutation.mutate(s.attempt_id)}
                    disabled={validateMutation.isPending}>
                    Validate
                  </Button>
                )}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </main>
  );
}
