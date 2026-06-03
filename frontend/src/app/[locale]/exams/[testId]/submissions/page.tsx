"use client";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { listTestSubmissions, batchValidate, validateAttempt, getTest, listBankTests } from "@/lib/api";
import type { AttemptSubmissionSummary, ExamTest } from "@/types/exam";
import { AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { AuditLogPanel } from "@/components/AuditLogPanel";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ChevronDown, ChevronRight, Archive } from "lucide-react";
import { toast } from "sonner";
import { formatError } from "@/lib/formatError";
import { Skeleton } from "@/components/ui/skeleton";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { Select } from "@/components/ui/select";
import { usePaginatedList } from "@/hooks/usePaginatedList";
import { PaginationControls } from "@/components/PaginationControls";

// ─── Grouping helpers ─────────────────────────────────────────────────────────
type ClassGroup = {
  key: string;
  class_name: string | null;
  class_archived_at: string | null;
  course_code: string | null;
  course_name: string | null;
  attempts: AttemptSubmissionSummary[];
};

function groupByClass(submissions: AttemptSubmissionSummary[]): ClassGroup[] {
  const map = new Map<string, ClassGroup>();
  for (const s of submissions) {
    const key = s.class_name ?? "__unclassified__";
    if (!map.has(key)) {
      map.set(key, { key, class_name: s.class_name, class_archived_at: s.class_archived_at, course_code: s.course_code, course_name: s.course_name, attempts: [] });
    }
    map.get(key)!.attempts.push(s);
  }
  return [...map.values()].sort((a, b) => {
    if (a.class_archived_at && !b.class_archived_at) return 1;
    if (!a.class_archived_at && b.class_archived_at) return -1;
    return (a.class_name ?? "").localeCompare(b.class_name ?? "");
  });
}

function statusBadge(s: string) {
  return s === "validated"
    ? <Badge className="bg-green-100 text-green-700">Validated</Badge>
    : <Badge variant="outline">Pending</Badge>;
}

// ─── Course grade preview (FR-4.33) ───────────────────────────────────────────
function CourseGradePreview({
  thisTest,
  courseTests,
  submissions,
  locale,
}: {
  thisTest: ExamTest;
  courseTests: ExamTest[];
  submissions: AttemptSubmissionSummary[];
  locale: string;
}) {
  // Sum of all exam weights in the course (this bank). Advisory: weights are
  // relative coefficients, so a sum over 100% is a soft warning, not an error.
  const totalWeight = courseTests.reduce((sum, t) => sum + (t.exam_weight ?? 0), 0);
  const overweight = totalWeight > 100;

  // Live class average for THIS exam from current (non-dispensed) scores.
  const scored = submissions.filter((s) => s.total_score != null);
  const classAvg =
    scored.length > 0
      ? scored.reduce((sum, s) => sum + (s.total_score ?? 0), 0) / scored.length
      : null;
  const contribution =
    classAvg != null && totalWeight > 0 ? (classAvg * thisTest.exam_weight) / totalWeight : null;

  return (
    <Card>
      <CardContent className="space-y-3 py-4">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold">Course Grade Preview</h2>
          <Link
            href={`/${locale}/exams/${thisTest.id}/settings`}
            className="text-xs text-blue-600 hover:underline"
          >
            Edit weight
          </Link>
        </div>

        {overweight && (
          <div className="flex items-center gap-2 rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-700">
            <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
            Course exam weights sum to {totalWeight}% (over 100%). Weights are relative, so this is
            only a heads-up.
          </div>
        )}

        <table className="w-full text-sm">
          <tbody>
            {courseTests.map((t) => (
              <tr key={t.id} className={t.id === thisTest.id ? "font-medium" : ""}>
                <td className="py-1">{t.title}</td>
                <td className="py-1 text-right text-muted-foreground">{t.exam_weight}%</td>
              </tr>
            ))}
            <tr className="border-t">
              <td className="py-1 font-medium">Total weight</td>
              <td className={`py-1 text-right font-medium ${overweight ? "text-amber-700" : ""}`}>
                {totalWeight}%
              </td>
            </tr>
          </tbody>
        </table>

        <div className="flex items-center justify-between border-t pt-2 text-sm">
          <span className="text-muted-foreground">This exam — live class average</span>
          <span className="font-medium">
            {classAvg != null ? `${classAvg.toFixed(1)} (≈ ${contribution?.toFixed(1)} weighted)` : "—"}
          </span>
        </div>
      </CardContent>
    </Card>
  );
}

// ─── Class group accordion ────────────────────────────────────────────────────
const SUBMISSIONS_PAGE_SIZE = 20;

function ClassSection({
  group, locale, testId, selected, toggle, validateMutation,
}: {
  group: ClassGroup; locale: string; testId: string;
  selected: Set<string>; toggle: (id: string) => void;
  validateMutation: { mutate: (id: string) => void; isPending: boolean };
}) {
  const isArchived = !!group.class_archived_at;
  const [open, setOpen] = useState(!isArchived);
  const label = group.class_name ?? "Unclassified";
  const [sPage, setSPage] = useState(1);
  const totalPages = Math.max(1, Math.ceil(group.attempts.length / SUBMISSIONS_PAGE_SIZE));
  const pagedAttempts = group.attempts.slice((sPage - 1) * SUBMISSIONS_PAGE_SIZE, sPage * SUBMISSIONS_PAGE_SIZE);

  return (
    <div className={`border rounded-lg ${isArchived ? "opacity-60" : ""}`}>
      <button
        onClick={() => setOpen(v => !v)}
        className="flex w-full items-center justify-between px-4 py-3 text-sm font-semibold hover:bg-muted/50 transition-colors"
      >
        <span className="flex items-center gap-2">
          {open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
          {label}
          {group.course_code && (
            <span className="text-xs font-normal text-muted-foreground">
              ({group.course_code}{group.course_name ? ` — ${group.course_name}` : ""})
            </span>
          )}
          {isArchived && (
            <span className="flex items-center gap-1 text-xs font-normal text-muted-foreground">
              <Archive className="h-3 w-3" /> Archived
            </span>
          )}
          <Badge variant="outline" className="text-xs">{group.attempts.length}</Badge>
        </span>
      </button>

      {open && (
        <div className="border-t space-y-2 p-3">
          {pagedAttempts.map((s) => (
            <Card key={s.attempt_id} className={selected.has(s.attempt_id) ? "ring-2 ring-primary" : ""}>
              <CardContent className="flex items-center gap-4 py-3">
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
          {group.attempts.length > SUBMISSIONS_PAGE_SIZE && (
            <div className="pt-2">
              <PaginationControls currentPage={sPage} totalPages={totalPages}
                totalItems={group.attempts.length} pageSize={SUBMISSIONS_PAGE_SIZE} onPageChange={setSPage} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────
export default function SubmissionsPage() {
  const params = useParams();
  const testId = params.testId as string;
  const locale = params.locale as string;
  const qc = useQueryClient();
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [overrideScore, setOverrideScore] = useState("");
  const [batchMsg, setBatchMsg] = useState<string | null>(null);
  const [showBatchConfirm, setShowBatchConfirm] = useState(false);

  const { data: submissions, isLoading, error } = useQuery({
    queryKey: ["submissions", testId],
    queryFn: () => listTestSubmissions(testId),
    staleTime: 10_000,
  });

  // FR-4.33: load this test + its course siblings (same bank) for the preview.
  const { data: thisTest } = useQuery({
    queryKey: ["test", testId],
    queryFn: () => getTest(testId),
    staleTime: 30_000,
  });
  const { data: courseTests } = useQuery({
    queryKey: ["bank-tests", thisTest?.bank_id],
    queryFn: () => listBankTests(thisTest!.bank_id),
    enabled: !!thisTest?.bank_id,
    staleTime: 30_000,
  });

  const batchMutation = useMutation({
    mutationFn: () => batchValidate(testId, {
      attempt_ids: [...selected],
      ...(overrideScore ? { override_score: parseFloat(overrideScore) } : {}),
    }),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ["submissions", testId] });
      setSelected(new Set());
      const msg = `Validated ${res.validated_count} attempt(s).${res.errors.length ? ` ${res.errors.length} skipped.` : ""}`;
      setBatchMsg(msg);
      toast.success(msg);
    },
    onError: (e) => { const msg = formatError(e); setBatchMsg(msg); toast.error(msg); },
  });

  const validateMutation = useMutation({
    mutationFn: (attemptId: string) => validateAttempt(attemptId),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["submissions", testId] }); toast.success("Attempt validated"); },
    onError: (e) => toast.error(formatError(e)),
  });

  // Hook called unconditionally before any conditional returns
  const { page: filteredSubs, total: filteredTotal, filters: subFilters, setFilter: setSubFilter } =
    usePaginatedList<AttemptSubmissionSummary>(submissions ?? [], {
      pageSize: 999, // grouping handles visual chunking; pagination is per-group in ClassSection
      filterFn: (s, f) => {
        const matchSearch = !f.search || s.user_id.includes(f.search);
        const matchStatus = !f.status || s.validation_status === f.status;
        return matchSearch && matchStatus;
      },
    });

  if (isLoading) return (
    <main className="max-w-5xl mx-auto p-8 space-y-4">
      <Skeleton className="h-8 w-56" />
      {[1, 2, 3].map(i => <Skeleton key={i} className="h-24 w-full rounded-lg" />)}
    </main>
  );
  if (error) return <p className="p-8 text-destructive">{formatError(error)}</p>;

  const toggle = (id: string) => {
    const next = new Set(selected);
    next.has(id) ? next.delete(id) : next.add(id);
    setSelected(next);
  };

  const groups = groupByClass(filteredSubs);

  return (
    <main className="max-w-5xl mx-auto p-8 space-y-4">
      <h1 className="text-2xl font-bold">Student Submissions</h1>

      {thisTest && courseTests && (
        <CourseGradePreview
          thisTest={thisTest}
          courseTests={courseTests}
          submissions={submissions ?? []}
          locale={locale}
        />
      )}

      {/* Filter bar */}
      {(submissions ?? []).length > 0 && (
        <div className="flex flex-col sm:flex-row gap-3">
          <Input
            placeholder="Search by student ID…"
            value={subFilters.search}
            onChange={e => setSubFilter("search", e.target.value)}
            className="max-w-xs font-mono text-sm"
          />
          <Select
            options={[
              { value: "pending", label: "Pending" },
              { value: "validated", label: "Validated" },
            ]}
            placeholder="All statuses"
            value={subFilters.status}
            onChange={e => setSubFilter("status", e.target.value)}
            className="w-40"
          />
          {(subFilters.search || subFilters.status) && (
            <span className="self-center text-sm text-muted-foreground">{filteredTotal} result{filteredTotal !== 1 ? "s" : ""}</span>
          )}
        </div>
      )}

      {/* Batch controls */}
      {selected.size > 0 && (
        <Card>
          <CardContent className="flex items-center gap-4 py-4">
            <span className="text-sm font-medium">{selected.size} selected</span>
            <Input type="number" placeholder="Override score (optional, 0-100)" value={overrideScore}
              onChange={e => setOverrideScore(e.target.value)} className="w-56" />
            <Button onClick={() => setShowBatchConfirm(true)} disabled={batchMutation.isPending}>
              {batchMutation.isPending ? "Validating…" : "Batch Validate"}
            </Button>
            <ConfirmDialog
              open={showBatchConfirm}
              title={`Validate ${selected.size} submission${selected.size !== 1 ? "s" : ""}?`}
              description="This marks the selected attempts as validated. Scores will become visible to students."
              confirmLabel="Validate"
              onConfirm={() => { setShowBatchConfirm(false); batchMutation.mutate(); }}
              onCancel={() => setShowBatchConfirm(false)}
            />
            <Button variant="outline" onClick={() => setSelected(new Set())}>Clear</Button>
          </CardContent>
        </Card>
      )}

      {batchMsg && <p className="text-sm text-green-700">{batchMsg}</p>}

      {groups.length === 0 ? (
        <p className="text-muted-foreground">No submissions yet.</p>
      ) : (
        <div className="space-y-3">
          {groups.map((g, i) => (
            <ClassSection
              key={g.key ?? i}
              group={g}
              locale={locale}
              testId={testId}
              selected={selected}
              toggle={toggle}
              validateMutation={validateMutation}
            />
          ))}
        </div>
      )}

      <AuditLogPanel testId={testId} />
    </main>
  );
}
