"use client";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { listTestComplaints, resolveComplaint } from "@/lib/api";
import type { ComplaintStatus, ScoreComplaint } from "@/types/exam";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { useParams } from "next/navigation";

function ResolutionForm({ complaint, onDone }: { complaint: ScoreComplaint; onDone: () => void }) {
  const qc = useQueryClient();
  const params = useParams();
  const testId = params.testId as string;
  const [note, setNote] = useState("");
  const [score, setScore] = useState("");
  const [resolveStatus, setResolveStatus] = useState<"approved" | "rejected">("rejected");

  const mutation = useMutation({
    mutationFn: () => resolveComplaint(complaint.id, {
      status: resolveStatus,
      review_note: note || undefined,
      score_override: score ? parseFloat(score) : undefined,
    }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["test-complaints", testId] }); onDone(); },
  });

  return (
    <div className="space-y-3 pt-2 border-t mt-3">
      <div className="flex gap-2">
        <Button size="sm" variant={resolveStatus === "approved" ? "default" : "outline"} onClick={() => setResolveStatus("approved")}>Approve</Button>
        <Button size="sm" variant={resolveStatus === "rejected" ? "destructive" : "outline"} onClick={() => setResolveStatus("rejected")}>Reject</Button>
      </div>
      {resolveStatus === "approved" && (
        <Input type="number" placeholder="Score override (optional)" value={score} onChange={e => setScore(e.target.value)} className="w-48" />
      )}
      <Textarea placeholder={resolveStatus === "rejected" ? "Reason (required)" : "Note (optional)"} value={note} onChange={e => setNote(e.target.value)} rows={2} />
      <div className="flex gap-2">
        <Button size="sm" onClick={() => mutation.mutate()} disabled={(resolveStatus === "rejected" && !note) || mutation.isPending}>
          {mutation.isPending ? "Saving…" : "Confirm"}
        </Button>
        <Button size="sm" variant="outline" onClick={onDone}>Cancel</Button>
      </div>
    </div>
  );
}

export default function TestComplaintsPage() {
  const params = useParams();
  const testId = params.testId as string;
  const [resolving, setResolving] = useState<string | null>(null);

  const { data: complaints, isLoading, error } = useQuery({
    queryKey: ["test-complaints", testId],
    queryFn: () => listTestComplaints(testId),
  });

  if (isLoading) return <div className="p-8">Loading…</div>;
  if (error) return <p className="p-8 text-destructive">{String(error)}</p>;

  const badgeColor = (s: ComplaintStatus) =>
    s === "approved" ? "bg-green-100 text-green-700" : s === "rejected" ? "bg-red-100 text-red-700" : "bg-amber-100 text-amber-700";

  return (
    <main className="max-w-4xl mx-auto p-8 space-y-6">
      <h1 className="text-2xl font-bold">Score Complaints</h1>
      {complaints?.length === 0 && <p className="text-muted-foreground">No complaints filed.</p>}
      <div className="space-y-4">
        {complaints?.map((c: ScoreComplaint) => (
          <Card key={c.id}>
            <CardContent className="py-4 space-y-2">
              <div className="flex items-start justify-between gap-4">
                <div className="space-y-1 flex-1">
                  <p className="text-xs text-muted-foreground font-mono">{c.question_id ? `Question: ${c.question_id}` : "Total score dispute"}</p>
                  <p className="text-sm">{c.reason}</p>
                  <p className="text-xs text-muted-foreground">{new Date(c.created_at).toLocaleString()}</p>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <Badge className={badgeColor(c.status)}>{c.status}</Badge>
                  {c.status === "pending" && (
                    <Button size="sm" variant="outline" onClick={() => setResolving(resolving === c.id ? null : c.id)}>
                      Resolve
                    </Button>
                  )}
                </div>
              </div>
              {c.review_note && <p className="text-xs text-muted-foreground italic">&ldquo;{c.review_note}&rdquo;</p>}
              {resolving === c.id && <ResolutionForm complaint={c} onDone={() => setResolving(null)} />}
            </CardContent>
          </Card>
        ))}
      </div>
    </main>
  );
}
