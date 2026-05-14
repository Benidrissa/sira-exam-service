"use client";

import { useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

const API_URL = process.env.NEXT_PUBLIC_EXAM_API_URL ?? "http://localhost:8001/api/v1";
const DEV_LOGIN = process.env.NEXT_PUBLIC_DEV_LOGIN === "true";

export default function LoginPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const redirect = searchParams.get("redirect") ?? "/";

  const [loading, setLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [token, setToken] = useState<string | null>(null);

  async function loginAs(role: "expert" | "user") {
    setLoading(role);
    setError(null);
    try {
      const res = await fetch(`${API_URL}/dev/tokens?role=${role}`);
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
      const data = await res.json();
      // Set cookie readable by Next.js middleware
      document.cookie = `access_token=${data.access_token}; path=/; SameSite=Lax; max-age=86400`;
      setToken(data.access_token);
      router.push(redirect);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(null);
    }
  }

  if (!DEV_LOGIN) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-gray-50">
        <div className="rounded-xl border bg-white p-8 shadow-sm text-center max-w-sm w-full">
          <h1 className="text-xl font-semibold mb-4">Sira Exam Service</h1>
          <p className="text-gray-500 text-sm">
            Authentication is managed by the Sira platform.
            <br />
            Please log in via the Sira dashboard and return here.
          </p>
        </div>
      </main>
    );
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-gray-50">
      <div className="rounded-xl border bg-white p-8 shadow-sm max-w-sm w-full space-y-4">
        <div className="text-center">
          <h1 className="text-xl font-semibold">Staging Login</h1>
          <p className="text-xs text-amber-600 mt-1 font-medium">
            ⚠️ Dev-only — not available in production
          </p>
        </div>

        <div className="space-y-3">
          <button
            onClick={() => loginAs("expert")}
            disabled={loading !== null}
            className="w-full rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50 transition-colors"
          >
            {loading === "expert" ? "Signing in…" : "Login as Teacher (expert)"}
          </button>

          <button
            onClick={() => loginAs("user")}
            disabled={loading !== null}
            className="w-full rounded-lg bg-green-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-50 transition-colors"
          >
            {loading === "user" ? "Signing in…" : "Login as Student (user)"}
          </button>
        </div>

        {error && (
          <p className="text-sm text-red-600 bg-red-50 rounded-lg p-3">
            {error}
            <br />
            <span className="text-xs text-gray-500">
              Make sure the backend is running with DEBUG=true
            </span>
          </p>
        )}

        {token && (
          <details className="text-xs text-gray-500">
            <summary className="cursor-pointer">Show token</summary>
            <pre className="mt-2 break-all whitespace-pre-wrap bg-gray-50 p-2 rounded text-xs">
              {token}
            </pre>
          </details>
        )}

        <p className="text-center text-xs text-gray-400">
          Teacher ID: cccccccc-…0001 · Student ID: dddddddd-…0002
          <br />
          Org ID: aaaaaaaa-…0001
        </p>
      </div>
    </main>
  );
}
