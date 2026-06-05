"use client";

import { useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { GraduationCap, Eye, EyeOff } from "lucide-react";
import { LoadingSpinner } from "@/components/ui/loading-spinner";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { cn } from "@/lib/utils";

const API_URL = process.env.NEXT_PUBLIC_EXAM_API_URL ?? "http://localhost:8001/api/v1";

export default function LoginPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const redirect = searchParams.get("redirect") ?? "/";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    if (!email.trim() || !password.trim()) {
      setError("Email and password are required.");
      return;
    }

    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email.trim().toLowerCase(), password }),
      });
      if (!res.ok) {
        const detail = await res.json().catch(() => null);
        throw new Error(
          res.status === 401
            ? "Invalid email or password."
            : (detail?.detail ?? `Sign in failed (${res.status}).`)
        );
      }
      const data = await res.json();
      document.cookie = `access_token=${data.access_token}; path=/; SameSite=Lax; max-age=86400`;
      const isLoginPage = !redirect || redirect.includes("/login") || redirect === "/" || redirect.match(/^\/[a-z]{2}\/?$/);
      router.push(isLoginPage ? "/fr/" : redirect);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
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

      {/* Login form */}
      <form onSubmit={handleSubmit} className="w-full max-w-sm space-y-4">
        <div className="space-y-3">
          <div>
            <label htmlFor="email" className="block text-sm font-medium text-blue-100 mb-1.5">
              Email
            </label>
            <input
              id="email"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              disabled={loading}
              className={cn(
                "w-full rounded-xl border border-white/20 bg-white/10 backdrop-blur-sm px-4 py-2.5",
                "text-white placeholder:text-blue-300/60 text-sm",
                "focus:outline-none focus:ring-2 focus:ring-white/30",
                "disabled:opacity-60"
              )}
            />
          </div>

          <div>
            <label htmlFor="password" className="block text-sm font-medium text-blue-100 mb-1.5">
              Password
            </label>
            <div className="relative">
              <input
                id="password"
                type={showPassword ? "text" : "password"}
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                disabled={loading}
                className={cn(
                  "w-full rounded-xl border border-white/20 bg-white/10 backdrop-blur-sm px-4 py-2.5 pr-11",
                  "text-white placeholder:text-blue-300/60 text-sm",
                  "focus:outline-none focus:ring-2 focus:ring-white/30",
                  "disabled:opacity-60"
                )}
              />
              <button
                type="button"
                onClick={() => setShowPassword((v) => !v)}
                tabIndex={-1}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-blue-300 hover:text-white transition-colors"
              >
                {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
          </div>
        </div>

        {error && (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        <button
          type="submit"
          disabled={loading}
          className={cn(
            "w-full flex items-center justify-center gap-2 rounded-xl border border-white/20 bg-white/10 backdrop-blur-sm px-4 py-2.5",
            "text-sm font-semibold text-white",
            "transition-all duration-150 hover:bg-white/20",
            "disabled:opacity-60 disabled:cursor-not-allowed"
          )}
        >
          {loading ? (
            <>
              <LoadingSpinner size="default" className="text-white" />
              Signing in…
            </>
          ) : (
            "Sign in"
          )}
        </button>
      </form>

      <a
        href="/manuals/uat-guide-fr.html"
        target="_blank"
        rel="noopener"
        className="mt-6 text-xs text-blue-200/70 hover:text-white transition-colors underline underline-offset-4"
      >
        Guide de test
      </a>
    </main>
  );
}
