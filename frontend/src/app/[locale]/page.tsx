"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
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
    const payload = JSON.parse(atob(token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")));
    return payload.role as string;
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
  return `${m}m ago`;
}

const STATUS_STYLE: Record<BankStatus, string> = {
  draft: "bg-gray-100 text-gray-600",
  generating: "bg-amber-100 text-amber-700 animate-pulse",
  review: "bg-orange-100 text-orange-700",
  published: "bg-green-100 text-green-700",
  archived: "bg-gray-100 text-gray-400",
};

const STATUS_DOT: Record<BankStatus, string> = {
  draft: "bg-gray-400",
  generating: "bg-amber-400",
  review: "bg-orange-400",
  published: "bg-green-500",
  archived: "bg-gray-300",
};

/* ── teacher view ───────────────────────────────────────────── */

function TeacherDashboard() {
  const { data: banks, isLoading, error, refetch } = useQuery({
    queryKey: ["banks"],
    queryFn: listExamBanks,
  });

  if (isLoading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-blue-600 border-t-transparent" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 p-6 text-center">
        <p className="text-red-700 font-medium">Failed to load exam banks</p>
        <button onClick={() => refetch()} className="mt-2 text-sm text-red-600 underline">Retry</button>
      </div>
    );
  }

  const active = banks?.filter(b => b.status !== "archived") ?? [];
  const archived = banks?.filter(b => b.status === "archived") ?? [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">My Exam Banks</h1>
          <p className="mt-1 text-sm text-gray-500">
            {active.length} active {active.length === 1 ? "bank" : "banks"}
          </p>
        </div>
        <Link
          href="/fr/create"
          className="flex items-center gap-2 rounded-xl bg-blue-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-blue-700 transition-colors"
        >
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
          </svg>
          New Exam
        </Link>
      </div>

      {/* Empty state */}
      {active.length === 0 && (
        <div className="rounded-2xl border-2 border-dashed border-gray-200 py-16 text-center">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-blue-50">
            <svg className="h-7 w-7 text-blue-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 6.042A8.967 8.967 0 0 0 6 3.75c-1.052 0-2.062.18-3 .512v14.25A8.987 8.987 0 0 1 6 18c2.305 0 4.408.867 6 2.292m0-14.25a8.966 8.966 0 0 1 6-2.292c1.052 0 2.062.18 3 .512v14.25A8.987 8.987 0 0 0 18 18a8.967 8.967 0 0 0-6 2.292m0-14.25v14.25" />
            </svg>
          </div>
          <h3 className="text-lg font-semibold text-gray-900">No exam banks yet</h3>
          <p className="mt-1 text-sm text-gray-500">Create your first exam bank to get started.</p>
          <Link href="/fr/create" className="mt-4 inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 transition-colors">
            Create your first exam
          </Link>
        </div>
      )}

      {/* Bank cards */}
      <div className="space-y-3">
        {active.map(bank => <BankCard key={bank.id} bank={bank} />)}
      </div>

      {/* Archived */}
      {archived.length > 0 && (
        <details className="mt-8">
          <summary className="cursor-pointer text-sm font-medium text-gray-500 hover:text-gray-700">
            {archived.length} archived bank{archived.length > 1 ? "s" : ""}
          </summary>
          <div className="mt-3 space-y-3">
            {archived.map(bank => <BankCard key={bank.id} bank={bank} />)}
          </div>
        </details>
      )}
    </div>
  );
}

function BankCard({ bank }: { bank: ExamBank }) {
  return (
    <div className="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm transition-shadow hover:shadow-md">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="font-semibold text-gray-900 truncate">{bank.title_fr}</h3>
            <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${STATUS_STYLE[bank.status]}`}>
              <span className={`h-1.5 w-1.5 rounded-full ${STATUS_DOT[bank.status]}`} />
              {bank.status}
            </span>
          </div>
          <p className="mt-1 text-sm text-gray-500">
            {bank.subject && <span>{bank.subject} · </span>}
            {timeAgo(bank.created_at)}
          </p>
        </div>
      </div>

      {/* Action buttons */}
      <div className="mt-4 flex flex-wrap gap-2">
        {(bank.status === "review" || bank.status === "published") && (
          <Link
            href={`/fr/banks/${bank.id}/review`}
            className="rounded-lg border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50 transition-colors"
          >
            Review Board
          </Link>
        )}
        {bank.status === "published" && (
          <>
            <Link
              href={`/fr/exams/${bank.id}/results`}
              className="rounded-lg border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50 transition-colors"
            >
              Grading
            </Link>
            <CopyTestLinkButton bankId={bank.id} />
          </>
        )}
        {bank.status === "generating" && (
          <span className="rounded-lg bg-amber-50 px-3 py-1.5 text-xs font-medium text-amber-700">
            Generating…
          </span>
        )}
        {bank.status === "draft" && (
          <Link
            href={`/fr/create`}
            className="rounded-lg bg-blue-50 px-3 py-1.5 text-xs font-medium text-blue-700 hover:bg-blue-100 transition-colors"
          >
            Continue setup
          </Link>
        )}
      </div>
    </div>
  );
}

function CopyTestLinkButton({ bankId }: { bankId: string }) {
  const [copied, setCopied] = useState(false);

  async function copyLink() {
    // Fetch the test ID for this bank
    try {
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_EXAM_API_URL ?? "http://localhost:8001/api/v1"}/exam/banks/${bankId}/tests`,
        { credentials: "include" }
      );
      if (res.ok) {
        const tests = await res.json();
        if (tests.length > 0) {
          const testId = tests[0].id;
          const url = `${window.location.origin}/fr/exams/${testId}/play`;
          await navigator.clipboard.writeText(url);
          setCopied(true);
          setTimeout(() => setCopied(false), 2000);
          return;
        }
      }
    } catch { /* ignore */ }
    // Fallback: copy bank URL
    await navigator.clipboard.writeText(`${window.location.origin}/fr/banks/${bankId}/review`);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <button
      onClick={copyLink}
      className="rounded-lg border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50 transition-colors"
    >
      {copied ? "✓ Copied!" : "Copy Test Link"}
    </button>
  );
}

/* ── student view ───────────────────────────────────────────── */

function StudentDashboard() {
  const router = useRouter();
  const [testInput, setTestInput] = useState("");
  const [error, setError] = useState("");

  function handleStart() {
    const input = testInput.trim();
    if (!input) { setError("Please enter a test ID or URL."); return; }

    // Accept a UUID or a full URL
    const uuidMatch = input.match(/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i);
    if (uuidMatch) {
      router.push(`/fr/exams/${uuidMatch[0]}/play`);
    } else {
      setError("Please enter a valid test ID (UUID) or exam link.");
    }
  }

  return (
    <div className="flex flex-col items-center justify-center py-16">
      <div className="w-full max-w-md text-center">
        <div className="mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-2xl bg-green-50">
          <svg className="h-8 w-8 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M4.26 10.147a60.438 60.438 0 0 0-.491 6.347A48.62 48.62 0 0 1 12 20.904a48.62 48.62 0 0 1 8.232-4.41 60.46 60.46 0 0 0-.491-6.347m-15.482 0a50.636 50.636 0 0 0-2.658-.813A59.906 59.906 0 0 1 12 3.493a59.903 59.903 0 0 1 10.399 5.84c-.896.248-1.783.52-2.658.814m-15.482 0A50.717 50.717 0 0 1 12 13.489a50.702 50.702 0 0 1 3.741-3.342M6.75 15a.75.75 0 1 0 0-1.5.75.75 0 0 0 0 1.5Zm0 0v-3.675A55.378 55.378 0 0 1 12 8.443m-7.007 11.55A5.981 5.981 0 0 0 6.75 15.75v-1.5" />
          </svg>
        </div>
        <h1 className="text-2xl font-bold text-gray-900">Ready to take your exam?</h1>
        <p className="mt-2 text-sm text-gray-500">
          Enter the test ID or paste the exam link provided by your teacher.
        </p>

        <div className="mt-6 flex gap-2">
          <input
            type="text"
            value={testInput}
            onChange={e => { setTestInput(e.target.value); setError(""); }}
            onKeyDown={e => e.key === "Enter" && handleStart()}
            placeholder="Paste test ID or exam link…"
            className="flex-1 rounded-xl border border-gray-200 px-4 py-2.5 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200"
          />
          <button
            onClick={handleStart}
            className="rounded-xl bg-green-600 px-4 py-2.5 text-sm font-medium text-white shadow-sm hover:bg-green-700 transition-colors"
          >
            Start →
          </button>
        </div>

        {error && <p className="mt-2 text-sm text-red-600">{error}</p>}

        <p className="mt-8 text-xs text-gray-400">
          Your teacher will share the exam link with you directly.
        </p>
      </div>
    </div>
  );
}

/* ── main ───────────────────────────────────────────────────── */

export default function HomePage() {
  const [role, setRole] = useState<string | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    setRole(getRole());
    setReady(true);
  }, []);

  if (!ready) {
    return (
      <div className="flex h-64 items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-blue-600 border-t-transparent" />
      </div>
    );
  }

  const isTeacher = role === "expert" || role === "admin" || role === "sub_admin";

  return (
    <main className="mx-auto max-w-4xl px-4 py-8 sm:px-6">
      {isTeacher ? <TeacherDashboard /> : <StudentDashboard />}
    </main>
  );
}
