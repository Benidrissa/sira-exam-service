"use client";

import Link from "next/link";
import { useParams, usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

interface JWTPayload {
  sub: string;
  role: string;
  org_id?: string;
  exp: number;
}

function decodeToken(token: string): JWTPayload | null {
  try {
    const payload = token.split(".")[1];
    return JSON.parse(atob(payload.replace(/-/g, "+").replace(/_/g, "/")));
  } catch {
    return null;
  }
}

function getCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

function getRoleFromCookie(): string | null {
  const token = getCookie("access_token");
  if (!token) return null;
  return decodeToken(token)?.role ?? null;
}

export function NavBar() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useParams<{ locale?: string }>();
  const locale = params?.locale ?? "fr";

  const [role, setRole] = useState<string | null>(() => {
    // Synchronous read on first render (runs in browser only)
    if (typeof window !== "undefined") return getRoleFromCookie();
    return null;
  });

  useEffect(() => {
    // Re-read after hydration in case cookie changed
    setRole(getRoleFromCookie());
  }, []);

  // Don't render on login page
  if (pathname?.includes("/login")) return null;

  function logout() {
    document.cookie = "access_token=; path=/; max-age=0; SameSite=Lax";
    router.push(`/${locale}/login`);
  }

  const isTeacher = role === "expert" || role === "admin" || role === "sub_admin";
  const isActive = (path: string) => pathname === `/${locale}${path}`;

  const linkClass = (path: string) =>
    `flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
      isActive(path)
        ? "bg-blue-50 text-blue-700"
        : "text-gray-600 hover:bg-gray-100 hover:text-gray-900"
    }`;

  return (
    <header className="sticky top-0 z-40 w-full border-b border-gray-200 bg-white shadow-sm">
      <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-2.5 sm:px-6">
        {/* Brand */}
        <Link href={`/${locale}/`} className="flex items-center gap-2 text-gray-900 hover:text-blue-700 transition-colors">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-blue-600 text-white">
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M4.26 10.147a60.438 60.438 0 0 0-.491 6.347A48.62 48.62 0 0 1 12 20.904a48.62 48.62 0 0 1 8.232-4.41 60.46 60.46 0 0 0-.491-6.347m-15.482 0a50.636 50.636 0 0 0-2.658-.813A59.906 59.906 0 0 1 12 3.493a59.903 59.903 0 0 1 10.399 5.84c-.896.248-1.783.52-2.658.814m-15.482 0A50.717 50.717 0 0 1 12 13.489a50.702 50.702 0 0 1 3.741-3.342" />
            </svg>
          </div>
          <span className="font-semibold text-sm">Sira Exam</span>
        </Link>

        {/* Actions */}
        <nav className="flex items-center gap-1">
          {isTeacher && (
            <>
              <Link href={`/${locale}/create`} className={linkClass("/create")}>
                <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
                </svg>
                <span className="hidden sm:inline">New Exam</span>
              </Link>
              <Link href={`/${locale}/proctor/dashboard`} className={linkClass("/proctor/dashboard")}>
                <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75 11.25 15 15 9.75m-3-7.036A11.959 11.959 0 0 1 3.598 6 11.99 11.99 0 0 0 3 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285Z" />
                </svg>
                <span className="hidden sm:inline">Proctor</span>
              </Link>
            </>
          )}

          {role && (
            <span className={`hidden sm:inline rounded-full px-2 py-0.5 text-xs font-medium ${
              isTeacher ? "bg-blue-50 text-blue-700" : "bg-green-50 text-green-700"
            }`}>
              {isTeacher ? "Teacher" : "Student"}
            </span>
          )}

          <button
            onClick={logout}
            className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium text-gray-600 hover:bg-red-50 hover:text-red-600 transition-colors"
            title="Log out"
          >
            <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 9V5.25A2.25 2.25 0 0 0 13.5 3h-6a2.25 2.25 0 0 0-2.25 2.25v13.5A2.25 2.25 0 0 0 7.5 21h6a2.25 2.25 0 0 0 2.25-2.25V15m3 0 3-3m0 0-3-3m3 3H9" />
            </svg>
            <span className="hidden sm:inline">Logout</span>
          </button>
        </nav>
      </div>
    </header>
  );
}
