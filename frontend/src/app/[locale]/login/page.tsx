"use client";

import { useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

const API_URL = process.env.NEXT_PUBLIC_EXAM_API_URL ?? "http://localhost:8001/api/v1";

function Spinner() {
  return (
    <svg
      className="h-5 w-5 animate-spin text-white"
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
    >
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
      />
    </svg>
  );
}

function GraduationCapIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M4.26 10.147a60.438 60.438 0 0 0-.491 6.347A48.62 48.62 0 0 1 12 20.904a48.62 48.62 0 0 1 8.232-4.41 60.46 60.46 0 0 0-.491-6.347m-15.482 0a50.636 50.636 0 0 0-2.658-.813A59.906 59.906 0 0 1 12 3.493a59.903 59.903 0 0 1 10.399 5.84c-.896.248-1.783.52-2.658.814m-15.482 0A50.717 50.717 0 0 1 12 13.489a50.702 50.702 0 0 1 3.741-3.342M6.75 15a.75.75 0 1 0 0-1.5.75.75 0 0 0 0 1.5Zm0 0v-3.675A55.378 55.378 0 0 1 12 8.443m-7.007 11.55A5.981 5.981 0 0 0 6.75 15.75v-1.5" />
    </svg>
  );
}

function BookOpenIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 6.042A8.967 8.967 0 0 0 6 3.75c-1.052 0-2.062.18-3 .512v14.25A8.987 8.987 0 0 1 6 18c2.305 0 4.408.867 6 2.292m0-14.25a8.966 8.966 0 0 1 6-2.292c1.052 0 2.062.18 3 .512v14.25A8.987 8.987 0 0 0 18 18a8.967 8.967 0 0 0-6 2.292m0-14.25v14.25" />
    </svg>
  );
}

export default function LoginPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const redirect = searchParams.get("redirect") ?? "/";

  const [loading, setLoading] = useState<"expert" | "user" | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function loginAs(role: "expert" | "user") {
    setLoading(role);
    setError(null);
    try {
      const res = await fetch(`${API_URL}/dev/tokens?role=${role}`);
      if (!res.ok) throw new Error(`Server returned ${res.status} — is the backend running with DEBUG=true?`);
      const data = await res.json();
      document.cookie = `access_token=${data.access_token}; path=/; SameSite=Lax; max-age=86400`;
      const isLoginPage = !redirect || redirect.includes("/login") || redirect === "/" || redirect.match(/^\/[a-z]{2}\/?$/);
      router.push(isLoginPage ? `/${role === "user" ? "fr" : "fr"}/` : redirect);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(null);
    }
  }

  return (
    <main className="flex min-h-screen flex-col items-center justify-center bg-gradient-to-br from-blue-950 via-blue-900 to-indigo-900 px-4">
      {/* Logo + brand */}
      <div className="mb-8 flex flex-col items-center gap-3 text-center">
        <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-white/10 backdrop-blur-sm border border-white/20">
          <GraduationCapIcon className="h-9 w-9 text-white" />
        </div>
        <div>
          <h1 className="text-3xl font-bold text-white tracking-tight">Sira Exam Service</h1>
          <p className="mt-1 text-sm text-blue-200">AI-powered proctored examinations</p>
        </div>
      </div>

      {/* Main card */}
      <div className="w-full max-w-md rounded-2xl bg-white/10 backdrop-blur-sm border border-white/20 p-6 shadow-2xl">
        <p className="mb-5 text-center text-sm font-medium text-blue-100">
          Select your role to continue
        </p>

        <div className="flex flex-col gap-3">
          {/* Teacher card */}
          <button
            onClick={() => loginAs("expert")}
            disabled={loading !== null}
            className="group flex items-center gap-4 rounded-xl border border-blue-400/30 bg-blue-500/20 p-4 text-left transition-all hover:bg-blue-500/35 hover:border-blue-400/50 hover:-translate-y-0.5 hover:shadow-lg disabled:opacity-60 disabled:cursor-not-allowed disabled:translate-y-0"
          >
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-blue-500/40 border border-blue-400/40">
              {loading === "expert" ? (
                <Spinner />
              ) : (
                <BookOpenIcon className="h-6 w-6 text-blue-100" />
              )}
            </div>
            <div>
              <p className="font-semibold text-white">
                {loading === "expert" ? "Signing in…" : "Continue as Teacher"}
              </p>
              <p className="text-xs text-blue-200 mt-0.5">
                Create exam banks, review questions, grade dissertations
              </p>
            </div>
          </button>

          {/* Student card */}
          <button
            onClick={() => loginAs("user")}
            disabled={loading !== null}
            className="group flex items-center gap-4 rounded-xl border border-emerald-400/30 bg-emerald-500/20 p-4 text-left transition-all hover:bg-emerald-500/35 hover:border-emerald-400/50 hover:-translate-y-0.5 hover:shadow-lg disabled:opacity-60 disabled:cursor-not-allowed disabled:translate-y-0"
          >
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-emerald-500/40 border border-emerald-400/40">
              {loading === "user" ? (
                <Spinner />
              ) : (
                <GraduationCapIcon className="h-6 w-6 text-emerald-100" />
              )}
            </div>
            <div>
              <p className="font-semibold text-white">
                {loading === "user" ? "Signing in…" : "Continue as Student"}
              </p>
              <p className="text-xs text-emerald-200 mt-0.5">
                Take exams, submit answers, view your results
              </p>
            </div>
          </button>
        </div>

        {error && (
          <div className="mt-4 rounded-xl border border-red-400/30 bg-red-500/20 px-4 py-3">
            <p className="text-sm text-red-200">{error}</p>
          </div>
        )}
      </div>

      {/* Staging badge */}
      <p className="mt-6 text-xs text-blue-300/70">
        ⚠️ Staging environment — test credentials only
      </p>
    </main>
  );
}
