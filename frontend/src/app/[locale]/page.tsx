"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { listExamBanks, listBankTests } from "@/lib/api";
import type { ExamBank, BankStatus } from "@/types/exam";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardHeader,
  CardTitle,
  CardContent,
  CardFooter,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Alert, AlertTitle, AlertDescription } from "@/components/ui/alert";
import { cn } from "@/lib/utils";
import {
  Plus,
  GraduationCap,
  FileText,
  AlertCircle,
  CheckCircle,
  ClipboardList,
} from "lucide-react";

/* ── helpers ────────────────────────────────────────────────── */

function getCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const m = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return m ? decodeURIComponent(m[1]) : null;
}

function getRole(): string | null {
  const token = getCookie("access_token");
  if (!token) return null;
  try {
    return JSON.parse(atob(token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")))?.role ?? null;
  } catch {
    return null;
  }
}

function timeAgo(iso: string) {
  const diff = Date.now() - new Date(iso).getTime();
  const d = Math.floor(diff / 86400000);
  const h = Math.floor(diff / 3600000);
  const m = Math.floor(diff / 60000);
  if (d > 0) return `${d}d ago`;
  if (h > 0) return `${h}h ago`;
  if (m > 0) return `${m}m ago`;
  return "just now";
}

const STATUS_BADGE_VARIANT: Record<BankStatus, "secondary" | "warning" | "success" | "outline"> = {
  draft: "secondary",
  generating: "warning",
  review: "warning",
  published: "success",
  archived: "outline",
};

/* ── teacher view ───────────────────────────────────────────── */

function TeacherDashboard({ locale }: { locale: string }) {
  const { data: banks, isLoading, error, refetch } = useQuery({
    queryKey: ["banks"],
    queryFn: listExamBanks,
  });

  if (isLoading) {
    return (
      <div className="space-y-4">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-24 animate-pulse rounded-xl bg-muted" />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <Alert variant="destructive">
        <AlertCircle className="h-4 w-4" />
        <AlertTitle>Failed to load exam banks</AlertTitle>
        <AlertDescription className="mt-2 flex flex-col gap-2">
          <span>{String(error)}</span>
          <Button
            variant="outline"
            size="sm"
            className="w-fit border-destructive/40 text-destructive hover:bg-destructive/10"
            onClick={() => refetch()}
          >
            Retry
          </Button>
        </AlertDescription>
      </Alert>
    );
  }

  const active = banks?.filter((b) => b.status !== "archived") ?? [];
  const archived = banks?.filter((b) => b.status === "archived") ?? [];

  return (
    <div className="space-y-6">
      {/* Page heading */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">My Exam Banks</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            {active.length} active {active.length === 1 ? "bank" : "banks"}
            {banks && banks.length > active.length
              ? ` · ${archived.length} archived`
              : ""}
          </p>
        </div>
        <Button asChild variant="default">
          <Link href={`/${locale}/create`}>
            <Plus />
            New Exam
          </Link>
        </Button>
      </div>

      {/* Empty state */}
      {active.length === 0 && (
        <Card className="border-2 border-dashed border-border bg-transparent shadow-none py-12">
          <CardContent className="flex flex-col items-center gap-4 text-center pt-0">
            <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-muted">
              <FileText className="h-7 w-7 text-muted-foreground" />
            </div>
            <div>
              <h3 className="text-base font-semibold">No exam banks yet</h3>
              <p className="mt-1 text-sm text-muted-foreground">
                Create your first exam bank to get started
              </p>
            </div>
            <Button asChild variant="default">
              <Link href={`/${locale}/create`}>
                <Plus />
                New Exam
              </Link>
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Active banks */}
      {active.length > 0 && (
        <div className="space-y-3">
          {active.map((bank) => (
            <BankCard key={bank.id} bank={bank} locale={locale} />
          ))}
        </div>
      )}

      {/* Archived banks */}
      {archived.length > 0 && (
        <details className="mt-4">
          <summary className="cursor-pointer select-none text-sm font-medium text-muted-foreground hover:text-foreground">
            Show {archived.length} archived
          </summary>
          <div className="mt-3 space-y-3">
            {archived.map((bank) => (
              <BankCard key={bank.id} bank={bank} locale={locale} />
            ))}
          </div>
        </details>
      )}
    </div>
  );
}

function BankCard({ bank, locale }: { bank: ExamBank; locale: string }) {
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState<string | null>(null);

  // Pre-fetch the first published test for this bank (needed for Grading link + student link)
  const { data: tests } = useQuery({
    queryKey: ["bank-tests", bank.id],
    queryFn: () => listBankTests(bank.id),
    enabled: bank.status === "published",
    staleTime: 60_000,
  });
  const testId = tests?.[0]?.id ?? null;

  async function copyTestLink() {
    setCopyError(null);
    try {
      if (!testId) throw new Error("No tests found for this bank");
      const url = `${window.location.origin}/${locale}/exams/${testId}/play`;
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
    } catch (e) {
      setCopyError(e instanceof Error ? e.message : "Could not copy link");
      setTimeout(() => setCopyError(null), 3000);
    }
  }

  return (
    <Card className="transition-shadow hover:shadow-md">
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between gap-3">
          <CardTitle className="truncate max-w-xs text-base">{bank.title_fr}</CardTitle>
          <Badge
            variant={STATUS_BADGE_VARIANT[bank.status]}
            className={cn(
              bank.status === "generating" && "animate-pulse"
            )}
          >
            {bank.status}
          </Badge>
        </div>
        <p className="text-xs text-muted-foreground">
          {bank.subject && <span>{bank.subject} · </span>}
          Updated {timeAgo(bank.updated_at)}
        </p>
      </CardHeader>

      <CardContent className="pt-1">
        {/* Generating shimmer */}
        {bank.status === "generating" && (
          <div className="flex items-center gap-2 rounded-lg bg-amber-50 px-3 py-2 text-xs font-medium text-amber-700">
            <span className="h-1.5 w-1.5 rounded-full bg-amber-400 animate-pulse" />
            Generating questions…
          </div>
        )}

        {/* Actions */}
        {bank.status !== "generating" && (
          <div className="flex flex-wrap items-center gap-2">
            {(bank.status === "review" || bank.status === "published") && (
              <Button variant="outline" size="sm" asChild>
                <Link href={`/${locale}/banks/${bank.id}/review`}>
                  Review Board
                </Link>
              </Button>
            )}
            {bank.status === "published" && (
              <>
                <Button variant="outline" size="sm" asChild disabled={!testId}>
                  <Link href={testId ? `/${locale}/exams/${testId}/submissions` : "#"}>
                    Submissions
                  </Link>
                </Button>
                <Button variant="outline" size="sm" asChild disabled={!testId}>
                  <Link href={testId ? `/${locale}/exams/${testId}/results` : "#"}>
                    Grading
                  </Link>
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={copyTestLink}
                  className={cn(
                    copied &&
                      "border-emerald-200 bg-emerald-50 text-emerald-700 hover:bg-emerald-100",
                    copyError &&
                      "border-destructive/40 bg-destructive/5 text-destructive"
                  )}
                >
                  {copied ? (
                    <>
                      <CheckCircle className="h-3.5 w-3.5" />
                      Copied
                    </>
                  ) : (
                    "Copy Student Link"
                  )}
                </Button>
                {copyError && (
                  <p className="text-xs text-destructive">{copyError}</p>
                )}
              </>
            )}
            {bank.status === "draft" && (
              <Button variant="outline" size="sm" asChild>
                <Link href={`/${locale}/create`}>Complete setup</Link>
              </Button>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

/* ── student view ───────────────────────────────────────────── */

function StudentDashboard({ locale }: { locale: string }) {
  const router = useRouter();
  const [testInput, setTestInput] = useState("");
  const [error, setError] = useState("");

  function handleStart() {
    const input = testInput.trim();
    if (!input) {
      setError("Please enter a test ID or exam link.");
      return;
    }
    const uuidMatch = input.match(
      /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i
    );
    if (uuidMatch) {
      router.push(`/${locale}/exams/${uuidMatch[0]}/play`);
    } else {
      setError("Could not find a valid test ID. Try pasting the full exam link.");
    }
  }

  return (
    <div className="flex justify-center mt-16">
      <Card className="w-full max-w-sm mx-auto">
        <CardHeader className="items-center text-center gap-2">
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-primary/10">
            <GraduationCap className="h-6 w-6 text-primary" style={{ width: 48, height: 48 }} />
          </div>
          <div>
            <h1 className="text-xl font-bold">Take an Exam</h1>
          </div>
          <p className="text-sm text-muted-foreground">
            Enter your test link or ID
          </p>
        </CardHeader>

        <CardContent className="space-y-3">
          <div className="flex gap-2">
            <Input
              type="text"
              value={testInput}
              onChange={(e) => {
                setTestInput(e.target.value);
                setError("");
              }}
              onKeyDown={(e) => e.key === "Enter" && handleStart()}
              placeholder="Paste test ID or link…"
              className={cn(error && "border-destructive focus-visible:ring-destructive/30")}
            />
            <Button onClick={handleStart}>Go →</Button>
          </div>
          {error && (
            <p className="text-xs text-destructive">{error}</p>
          )}
        </CardContent>

        <CardFooter className="flex-col gap-3">
          <Button variant="outline" size="sm" className="w-full" asChild>
            <Link href={`/${locale}/students/me/attempts`}>
              <ClipboardList className="h-3.5 w-3.5" />
              My Exam History
            </Link>
          </Button>
          <p className="text-xs text-muted-foreground text-center w-full">
            Or paste a test link above to start a new exam.
          </p>
        </CardFooter>
      </Card>
    </div>
  );
}

/* ── main ───────────────────────────────────────────────────── */

export default function HomePage() {
  const params = useParams<{ locale?: string }>();
  const locale = params?.locale ?? "fr";

  // Synchronous role detection — no spinner flash
  const role = typeof window !== "undefined" ? getRole() : null;
  const isTeacher = role === "expert" || role === "admin" || role === "sub_admin";

  return (
    <main className="mx-auto max-w-3xl px-4 py-8 sm:px-6">
      {isTeacher ? (
        <TeacherDashboard locale={locale} />
      ) : (
        <StudentDashboard locale={locale} />
      )}
    </main>
  );
}
