"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { listExamBanks } from "@/lib/api";
import type { ExamBank, BankStatus } from "@/types/exam";

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

const STATUS_STYLE: Record<BankStatus, string> = {
  draft: "bg-gray-100 text-gray-600",
  generating: "bg-amber-100 text-amber-700",
  review: "bg-orange-100 text-orange-700",
  published: "bg-green-100 text-green-700",
  archived: "bg-gray-100 text-gray-400",
};

const STATUS_DOT: Record<BankStatus, string> = {
  draft: "bg-gray-400",
  generating: "bg-amber-400 animate-pulse",
  review: "bg-orange-400",
  published: "bg-green-500",
  archived: "bg-gray-300",
};

/* ── teacher view ───────────────────────────────────────────── */

function TeacherDashboard({ locale }: { locale: string }) {
  const { data: banks, isLoading, error, refetch } = useQuery({
    queryKey: ["banks"],
    queryFn: listExamBanks,
  });

  if (isLoading) {
    return (
      <div className="space-y-3">
        {[1, 2, 3].map(i => (
          <div key={i} className="h-24 animate-pulse rounded-2xl bg-gray-100" />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 p-6 text-center">
        <p className="text-red-700 font-medium">Failed to load exam banks</p>
        <p className="mt-1 text-sm text-red-500">{String(error)}</p>
        <button onClick={() => refetch()} className="mt-3 rounded-lg bg-red-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-red-700">
          Retry
        </button>
      </div>
    );
  }

  const active = banks?.filter(b => b.status !== "archived") ?? [];
  const archived = banks?.filter(b => b.status === "archived") ?? [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">My Exam Banks</h1>
          <p className="mt-0.5 text-sm text-gray-500">
            {active.length} active {active.length === 1 ? "bank" : "banks"}
            {banks && banks.length > active.length ? ` · ${archived.length} archived` : ""}
          </p>
        </div>
        <Link
          href={`/${locale}/create`}
          className="flex items-center gap-2 rounded-xl bg-blue-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-blue-700 transition-colors"
        >
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
          </svg>
          New Exam
        </Link>
      </div>

      {active.length === 0 && (
        <div className="rounded-2xl border-2 border-dashed border-gray-200 py-16 text-center">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-blue-50">
            <svg className="h-7 w-7 text-blue-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 6.042A8.967 8.967 0 0 0 6 3.75c-1.052 0-2.062.18-3 .512v14.25A8.987 8.987 0 0 1 6 18c2.305 0 4.408.867 6 2.292m0-14.25a8.966 8.966 0 0 1 6-2.292c1.052 0 2.062.18 3 .512v14.25A8.987 8.987 0 0 0 18 18a8.967 8.967 0 0 0-6 2.292m0-14.25v14.25" />
            </svg>
          </div>
          <h3 className="text-base font-semibold text-gray-900">No exam banks yet</h3>
          <p className="mt-1 text-sm text-gray-500">Create your first exam bank to get started</p>
          <Link href={`/${locale}/create`} className="mt-4 inline-flex items-center gap-2 rounded-xl bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 transition-colors">
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
            </svg>
            Create exam bank
          </Link>
        </div>
      )}

      <div className="space-y-3">
        {active.map(bank => <BankCard key={bank.id} bank={bank} locale={locale} />)}
      </div>

      {archived.length > 0 && (
        <details className="mt-4">
          <summary className="cursor-pointer select-none text-sm font-medium text-gray-400 hover:text-gray-600">
            Show {archived.length} archived
          </summary>
          <div className="mt-3 space-y-3">
            {archived.map(bank => <BankCard key={bank.id} bank={bank} locale={locale} />)}
          </div>
        </details>
      )}
    </div>
  );
}

function BankCard({ bank, locale }: { bank: ExamBank; locale: string }) {
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState<string | null>(null);

  async function copyTestLink() {
    setCopyError(null);
    try {
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_EXAM_API_URL ?? "http://localhost:8001/api/v1"}/exam/banks/${bank.id}/tests`,
        { credentials: "include" }
      );
      if (!res.ok) throw new Error("No tests found");
      const tests = await res.json();
      if (!tests.length) throw new Error("No tests created for this bank yet");
      const testId = tests[0].id;
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
    <div className="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm transition-shadow hover:shadow-md">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="font-semibold text-gray-900 truncate max-w-xs">{bank.title_fr}</h3>
            <span className={`inline-flex shrink-0 items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${STATUS_STYLE[bank.status]}`}>
              <span className={`h-1.5 w-1.5 rounded-full ${STATUS_DOT[bank.status]}`} />
              {bank.status}
            </span>
          </div>
          <p className="mt-1 text-xs text-gray-400">
            {bank.subject && <span>{bank.subject} · </span>}
            Updated {timeAgo(bank.updated_at)}
          </p>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        {(bank.status === "review" || bank.status === "published") && (
          <Link
            href={`/${locale}/banks/${bank.id}/review`}
            className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-100 transition-colors"
          >
            Review Board
          </Link>
        )}
        {bank.status === "published" && (
          <>
            <Link
              href={`/${locale}/exams/${bank.id}/results`}
              className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-100 transition-colors"
            >
              Grading
            </Link>
            <button
              onClick={copyTestLink}
              className={`rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors ${
                copied
                  ? "border-green-200 bg-green-50 text-green-700"
                  : copyError
                  ? "border-red-200 bg-red-50 text-red-600"
                  : "border-blue-200 bg-blue-50 text-blue-700 hover:bg-blue-100"
              }`}
            >
              {copied ? "✓ Link copied!" : copyError ? copyError : "Copy Student Link"}
            </button>
          </>
        )}
        {bank.status === "generating" && (
          <span className="flex items-center gap-1.5 rounded-lg bg-amber-50 px-3 py-1.5 text-xs font-medium text-amber-700">
            <span className="h-1.5 w-1.5 rounded-full bg-amber-400 animate-pulse" />
            Generating questions…
          </span>
        )}
        {bank.status === "draft" && (
          <Link
            href={`/${locale}/create`}
            className="rounded-lg bg-blue-50 px-3 py-1.5 text-xs font-medium text-blue-700 hover:bg-blue-100 transition-colors"
          >
            Complete setup →
          </Link>
        )}
      </div>
    </div>
  );
}

/* ── student view ───────────────────────────────────────────── */

function StudentDashboard({ locale }: { locale: string }) {
  const router = useRouter();
  const [testInput, setTestInput] = useState("");
  const [error, setError] = useState("");

  function handleStart() {
    const input = testInput.trim();
    if (!input) { setError("Please enter a test ID or exam link."); return; }
    const uuidMatch = input.match(/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i);
    if (uuidMatch) {
      router.push(`/${locale}/exams/${uuidMatch[0]}/play`);
    } else {
      setError("Could not find a valid test ID. Try pasting the full exam link.");
    }
  }

  return (
    <div className="flex flex-col items-center justify-center py-12">
      <div className="w-full max-w-sm text-center">
        <div className="mx-auto mb-5 flex h-14 w-14 items-center justify-center rounded-2xl bg-green-50">
          <svg className="h-7 w-7 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M4.26 10.147a60.438 60.438 0 0 0-.491 6.347A48.62 48.62 0 0 1 12 20.904a48.62 48.62 0 0 1 8.232-4.41 60.46 60.46 0 0 0-.491-6.347m-15.482 0a50.636 50.636 0 0 0-2.658-.813A59.906 59.906 0 0 1 12 3.493a59.903 59.903 0 0 1 10.399 5.84c-.896.248-1.783.52-2.658.814m-15.482 0A50.717 50.717 0 0 1 12 13.489a50.702 50.702 0 0 1 3.741-3.342" />
          </svg>
        </div>
        <h1 className="text-xl font-bold text-gray-900">Take an exam</h1>
        <p className="mt-1 text-sm text-gray-500">
          Enter the test link or ID provided by your teacher
        </p>
        <div className="mt-5 flex gap-2">
          <input
            type="text"
            value={testInput}
            onChange={e => { setTestInput(e.target.value); setError(""); }}
            onKeyDown={e => e.key === "Enter" && handleStart()}
            placeholder="Paste test ID or link…"
            className="flex-1 rounded-xl border border-gray-200 px-4 py-2.5 text-sm shadow-sm focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100"
          />
          <button
            onClick={handleStart}
            className="rounded-xl bg-green-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-green-700 transition-colors"
          >
            Go →
          </button>
        </div>
        {error && <p className="mt-2 text-xs text-red-600">{error}</p>}
        <p className="mt-6 text-xs text-gray-400">
          Your teacher will share the exam link with you directly.
        </p>
      </div>
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
      {isTeacher ? <TeacherDashboard locale={locale} /> : <StudentDashboard locale={locale} />}
    </main>
  );
}
