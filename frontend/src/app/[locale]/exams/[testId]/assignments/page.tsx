"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  listAssignments,
  createAssignment,
  updateAssignment,
  deleteAssignment,
  listClasses,
} from "@/lib/api";
import type { TestAssignment, SchoolClass, Quarter } from "@/types/exam";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { LoadingSpinner } from "@/components/ui/loading-spinner";
import Link from "next/link";
import { Trash2, Pencil, Plus, X, Check } from "lucide-react";

const QUARTERS: { value: Quarter; label: string }[] = [
  { value: "q1", label: "Q1" },
  { value: "q2", label: "Q2" },
  { value: "q3", label: "Q3" },
  { value: "q4", label: "Q4" },
];

function toLocalInput(iso: string) {
  return new Date(iso).toISOString().slice(0, 16);
}

function toDisplayRange(released: string, closes: string) {
  const fmt = (d: string) =>
    new Date(d).toLocaleString(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
    });
  return `${fmt(released)} → ${fmt(closes)}`;
}

// ---------------------------------------------------------------------------
// Inline create form
// ---------------------------------------------------------------------------

function CreateForm({
  testId,
  classes,
  onClose,
}: {
  testId: string;
  classes: SchoolClass[];
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [classId, setClassId] = useState(classes[0]?.id ?? "");
  const [releasedAt, setReleasedAt] = useState("");
  const [closesAt, setClosesAt] = useState("");
  const [quarter, setQuarter] = useState<Quarter>("q1");
  const [err, setErr] = useState<string | null>(null);

  const { mutate, isPending } = useMutation({
    mutationFn: () =>
      createAssignment(testId, {
        class_id: classId,
        released_at: new Date(releasedAt).toISOString(),
        closes_at: new Date(closesAt).toISOString(),
        quarter,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["assignments", testId] });
      onClose();
    },
    onError: (e: unknown) => {
      const msg =
        e instanceof Error ? e.message : "Échec de la création de l'affectation";
      setErr(msg);
    },
  });

  function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    if (!classId || !releasedAt || !closesAt) {
      setErr("Tous les champs sont obligatoires.");
      return;
    }
    if (new Date(closesAt) <= new Date(releasedAt)) {
      setErr("L'heure de clôture doit être postérieure à l'heure d'ouverture.");
      return;
    }
    mutate();
  }

  return (
    <Card className="border-primary/30 bg-primary/5">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base">Affecter à une classe</CardTitle>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <X className="h-4 w-4" />
          </button>
        </div>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="space-y-3">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {/* Class */}
            <div className="sm:col-span-2">
              <label className="text-xs font-medium text-muted-foreground mb-1 block">Classe</label>
              <select
                value={classId}
                onChange={(e) => setClassId(e.target.value)}
                disabled={isPending}
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              >
                {classes.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name} ({c.academic_year})
                  </option>
                ))}
              </select>
            </div>

            {/* Open */}
            <div>
              <label className="text-xs font-medium text-muted-foreground mb-1 block">Ouverture le</label>
              <input
                type="datetime-local"
                value={releasedAt}
                onChange={(e) => setReleasedAt(e.target.value)}
                disabled={isPending}
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              />
            </div>

            {/* Close */}
            <div>
              <label className="text-xs font-medium text-muted-foreground mb-1 block">Clôture le</label>
              <input
                type="datetime-local"
                value={closesAt}
                onChange={(e) => setClosesAt(e.target.value)}
                disabled={isPending}
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              />
            </div>

            {/* Quarter */}
            <div>
              <label className="text-xs font-medium text-muted-foreground mb-1 block">Trimestre</label>
              <select
                value={quarter}
                onChange={(e) => setQuarter(e.target.value as Quarter)}
                disabled={isPending}
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              >
                {QUARTERS.map((q) => (
                  <option key={q.value} value={q.value}>{q.label}</option>
                ))}
              </select>
            </div>
          </div>

          {err && (
            <Alert variant="destructive">
              <AlertDescription>{err}</AlertDescription>
            </Alert>
          )}

          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" size="sm" onClick={onClose} disabled={isPending}>
              Annuler
            </Button>
            <Button type="submit" size="sm" disabled={isPending}>
              {isPending ? <LoadingSpinner size="sm" className="mr-1" /> : <Check className="h-3.5 w-3.5 mr-1" />}
              Affecter
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Inline edit row
// ---------------------------------------------------------------------------

function EditRow({
  assignment,
  testId,
  onClose,
}: {
  assignment: TestAssignment;
  testId: string;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [releasedAt, setReleasedAt] = useState(toLocalInput(assignment.released_at));
  const [closesAt, setClosesAt] = useState(toLocalInput(assignment.closes_at));
  const [quarter, setQuarter] = useState<Quarter>(assignment.quarter);
  const [err, setErr] = useState<string | null>(null);

  const { mutate, isPending } = useMutation({
    mutationFn: () =>
      updateAssignment(testId, assignment.id, {
        released_at: new Date(releasedAt).toISOString(),
        closes_at: new Date(closesAt).toISOString(),
        quarter,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["assignments", testId] });
      onClose();
    },
    onError: (e: unknown) => {
      setErr(e instanceof Error ? e.message : "Échec de la mise à jour de l'affectation");
    },
  });

  function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    if (new Date(closesAt) <= new Date(releasedAt)) {
      setErr("L'heure de clôture doit être postérieure à l'heure d'ouverture.");
      return;
    }
    mutate();
  }

  return (
    <form onSubmit={submit} className="space-y-2 p-3 bg-muted/40 rounded-lg">
      <div className="grid grid-cols-2 gap-2">
        <div>
          <label className="text-xs text-muted-foreground">Ouverture le</label>
          <input
            type="datetime-local"
            value={releasedAt}
            onChange={(e) => setReleasedAt(e.target.value)}
            disabled={isPending}
            className="w-full rounded border border-input bg-background px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-ring"
          />
        </div>
        <div>
          <label className="text-xs text-muted-foreground">Clôture le</label>
          <input
            type="datetime-local"
            value={closesAt}
            onChange={(e) => setClosesAt(e.target.value)}
            disabled={isPending}
            className="w-full rounded border border-input bg-background px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-ring"
          />
        </div>
        <div>
          <label className="text-xs text-muted-foreground">Trimestre</label>
          <select
            value={quarter}
            onChange={(e) => setQuarter(e.target.value as Quarter)}
            disabled={isPending}
            className="w-full rounded border border-input bg-background px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-ring"
          >
            {QUARTERS.map((q) => (
              <option key={q.value} value={q.value}>{q.label}</option>
            ))}
          </select>
        </div>
      </div>
      {err && <p className="text-xs text-destructive">{err}</p>}
      <div className="flex gap-2 justify-end">
        <Button type="button" variant="ghost" size="sm" onClick={onClose} disabled={isPending}>
          Annuler
        </Button>
        <Button type="submit" size="sm" disabled={isPending}>
          {isPending ? <LoadingSpinner size="sm" /> : "Enregistrer"}
        </Button>
      </div>
    </form>
  );
}

// ---------------------------------------------------------------------------
// Assignment row
// ---------------------------------------------------------------------------

function AssignmentRow({
  assignment,
  testId,
  classes,
}: {
  assignment: TestAssignment;
  testId: string;
  classes: SchoolClass[];
}) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [deleteErr, setDeleteErr] = useState<string | null>(null);

  const className =
    classes.find((c) => c.id === assignment.class_id)?.name ?? assignment.class_id;

  const { mutate: remove, isPending: deleting } = useMutation({
    mutationFn: () => deleteAssignment(testId, assignment.id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["assignments", testId] }),
    onError: (e: unknown) => {
      setDeleteErr(e instanceof Error ? e.message : "Échec de la suppression");
      setTimeout(() => setDeleteErr(null), 4000);
    },
  });

  if (editing) {
    return (
      <li className="rounded-xl border border-border bg-card p-3">
        <p className="text-sm font-medium mb-2">{className}</p>
        <EditRow assignment={assignment} testId={testId} onClose={() => setEditing(false)} />
      </li>
    );
  }

  return (
    <li className="flex flex-col sm:flex-row sm:items-center gap-2 rounded-xl border border-border bg-card px-4 py-3">
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium">{className}</p>
        <p className="text-xs text-muted-foreground mt-0.5">
          {toDisplayRange(assignment.released_at, assignment.closes_at)}
        </p>
      </div>
      <Badge variant="outline" className="w-fit">{assignment.quarter.toUpperCase()}</Badge>
      <div className="flex items-center gap-1.5">
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7"
          onClick={() => setEditing(true)}
        >
          <Pencil className="h-3.5 w-3.5" />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7 text-destructive hover:text-destructive"
          onClick={() => remove()}
          disabled={deleting}
        >
          {deleting ? <LoadingSpinner size="sm" /> : <Trash2 className="h-3.5 w-3.5" />}
        </Button>
      </div>
      {deleteErr && <p className="text-xs text-destructive w-full">{deleteErr}</p>}
    </li>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function AssignmentsPage() {
  const { testId, locale } = useParams<{ testId: string; locale: string }>();
  const [showCreate, setShowCreate] = useState(false);

  const { data: assignments, isLoading: loadingA, error: errorA } = useQuery({
    queryKey: ["assignments", testId],
    queryFn: () => listAssignments(testId),
  });

  const { data: classes, isLoading: loadingC } = useQuery({
    queryKey: ["classes"],
    queryFn: listClasses,
  });

  const isLoading = loadingA || loadingC;

  return (
    <div className="mx-auto max-w-2xl px-4 py-8 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <nav className="text-xs text-muted-foreground mb-1">
            <Link href={`/${locale}/`} className="hover:underline">Accueil</Link>
            {" / "}
            <Link href={`/${locale}/exams/${testId}/submissions`} className="hover:underline">Test</Link>
            {" / "}
            <span>Affectations</span>
          </nav>
          <h1 className="text-2xl font-bold">Affectations par classe</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Planifiez ce test pour une ou plusieurs classes avec une fenêtre d&apos;ouverture/clôture.
          </p>
        </div>
        <Button
          size="sm"
          onClick={() => setShowCreate(true)}
          disabled={showCreate || !classes?.length}
        >
          <Plus className="h-3.5 w-3.5 mr-1" />
          Affecter
        </Button>
      </div>

      {/* Create form */}
      {showCreate && classes && classes.length > 0 && (
        <CreateForm
          testId={testId}
          classes={classes}
          onClose={() => setShowCreate(false)}
        />
      )}

      {/* No classes warning */}
      {!loadingC && (!classes || classes.length === 0) && (
        <Alert>
          <AlertDescription>
            Aucune classe trouvée. Créez une classe avant de planifier un test.
          </AlertDescription>
        </Alert>
      )}

      {/* Loading */}
      {isLoading && (
        <div className="space-y-2">
          {[1, 2].map((i) => (
            <div key={i} className="h-16 animate-pulse rounded-xl bg-muted" />
          ))}
        </div>
      )}

      {/* Error */}
      {errorA && (
        <Alert variant="destructive">
          <AlertDescription>{String(errorA)}</AlertDescription>
        </Alert>
      )}

      {/* List */}
      {!isLoading && assignments && assignments.length === 0 && (
        <p className="text-sm text-muted-foreground text-center py-8">
          Aucune planification pour le moment. Cliquez sur Affecter pour planifier ce test pour une classe.
        </p>
      )}

      {assignments && assignments.length > 0 && classes && (
        <ul className="space-y-2">
          {assignments.map((a) => (
            <AssignmentRow key={a.id} assignment={a} testId={testId} classes={classes} />
          ))}
        </ul>
      )}
    </div>
  );
}
