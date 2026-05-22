"use client";

import { useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { GraduationCap, BookOpen } from "lucide-react";
import { LoadingSpinner } from "@/components/ui/loading-spinner";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { cn } from "@/lib/utils";

const API_URL = process.env.NEXT_PUBLIC_EXAM_API_URL ?? "http://localhost:8001/api/v1";

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
      {/* Brand section */}
      <div className="mb-8 flex flex-col items-center gap-3 text-center">
        <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-white/10 backdrop-blur-sm border border-white/20">
          <GraduationCap className="h-9 w-9 text-white" />
        </div>
        <div>
          <h1 className="text-3xl font-bold text-white tracking-tight">Sira Exam</h1>
          <p className="mt-1 text-sm text-blue-200">AI-powered proctored examinations</p>
        </div>
      </div>

      {/* Role selection */}
      <div className="w-full max-w-md space-y-3">
        <p className="text-center text-sm font-medium text-blue-100 mb-5">
          Select your role to continue
        </p>

        {/* Role cards side by side on sm+, stacked on mobile */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {/* Teacher card */}
          <button
            onClick={() => loginAs("expert")}
            disabled={loading !== null}
            className={cn(
              "group flex flex-col items-center gap-3 rounded-xl border border-white/20 bg-white/10 backdrop-blur-sm p-5 text-center",
              "transition-all duration-150 hover:bg-white/20 hover:-translate-y-0.5 hover:shadow-lg",
              "disabled:opacity-60 disabled:cursor-not-allowed disabled:translate-y-0",
              loading === "expert" && "opacity-60"
            )}
          >
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-white/10 border border-white/20">
              {loading === "expert" ? (
                <LoadingSpinner size="default" className="text-white" />
              ) : (
                <BookOpen className="h-6 w-6 text-white" />
              )}
            </div>
            <div>
              <p className="font-semibold text-white text-sm">
                {loading === "expert" ? "Signing in…" : "Continue as Teacher"}
              </p>
              <p className="text-xs text-blue-200 mt-1 leading-relaxed">
                Create banks, review questions, grade dissertations
              </p>
            </div>
          </button>

          {/* Student card */}
          <button
            onClick={() => loginAs("user")}
            disabled={loading !== null}
            className={cn(
              "group flex flex-col items-center gap-3 rounded-xl border border-white/20 bg-white/10 backdrop-blur-sm p-5 text-center",
              "transition-all duration-150 hover:bg-white/20 hover:-translate-y-0.5 hover:shadow-lg",
              "disabled:opacity-60 disabled:cursor-not-allowed disabled:translate-y-0",
              loading === "user" && "opacity-60"
            )}
          >
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-white/10 border border-white/20">
              {loading === "user" ? (
                <LoadingSpinner size="default" className="text-white" />
              ) : (
                <GraduationCap className="h-6 w-6 text-white" />
              )}
            </div>
            <div>
              <p className="font-semibold text-white text-sm">
                {loading === "user" ? "Signing in…" : "Continue as Student"}
              </p>
              <p className="text-xs text-blue-200 mt-1 leading-relaxed">
                Take exams, submit answers, view your results
              </p>
            </div>
          </button>
        </div>

        {/* Error */}
        {error && (
          <Alert variant="destructive" className="mt-4">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
      </div>

      {/* Staging badge — dev/staging only */}
      {process.env.NODE_ENV !== "production" && (
        <div className="mt-8">
          <span className="inline-flex items-center rounded-full border border-amber-400/30 bg-amber-400/20 px-3 py-1 text-xs text-amber-200">
            Staging environment — test credentials only
          </span>
        </div>
      )}
    </main>
  );
}
