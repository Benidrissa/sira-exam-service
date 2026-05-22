"use client";

import Link from "next/link";
import { useParams, usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { GraduationCap, Plus, LogOut, Shield, Users, BookOpen } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

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
    setRole(getRoleFromCookie());
  }, [pathname]);

  // Don't render on login page
  if (pathname?.includes("/login")) return null;

  function logout() {
    document.cookie = "access_token=; path=/; max-age=0; SameSite=Lax";
    router.push(`/${locale}/login`);
  }

  const isTeacher = role === "expert" || role === "admin" || role === "sub_admin";
  const isActive = (path: string) => {
    const full = `/${locale}${path}`;
    return pathname === full || pathname?.startsWith(full + "/");
  };

  return (
    <header className="sticky top-0 z-40 h-14 w-full border-b border-border bg-background/95 backdrop-blur-sm">
      <div className="mx-auto flex h-full max-w-5xl items-center justify-between px-4 sm:px-6">
        {/* Brand */}
        <Link
          href={`/${locale}/`}
          className="flex items-center gap-2 text-foreground hover:text-primary transition-colors"
        >
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary text-primary-foreground shrink-0">
            <GraduationCap className="h-4 w-4" />
          </div>
          <span className="font-semibold text-sm">Sira Exam</span>
        </Link>

        {/* Actions */}
        <nav className="flex items-center gap-2">
          {isTeacher && (
            <>
              {/* New Exam */}
              <Button variant="default" size="sm" asChild>
                <Link href={`/${locale}/create`}>
                  <Plus className="h-3.5 w-3.5" />
                  <span className="hidden sm:inline">New Exam</span>
                </Link>
              </Button>

              {/* Classes */}
              <Button
                variant="ghost"
                size="sm"
                asChild
                className={cn(
                  isActive("/classes") && "bg-accent text-accent-foreground"
                )}
              >
                <Link href={`/${locale}/classes`}>
                  <Users className="h-3.5 w-3.5" />
                  <span className="hidden sm:inline">Classes</span>
                </Link>
              </Button>

              {/* Proctor */}
              <Button
                variant="ghost"
                size="sm"
                asChild
                className={cn(
                  isActive("/proctor/dashboard") && "bg-accent text-accent-foreground"
                )}
              >
                <Link href={`/${locale}/proctor/dashboard`}>
                  <Shield className="h-3.5 w-3.5" />
                  <span className="hidden sm:inline">Proctor</span>
                </Link>
              </Button>
            </>
          )}

          {/* Student: My Exams */}
          {!isTeacher && role && (
            <Button
              variant="ghost"
              size="sm"
              asChild
              className={cn(isActive("/students/me/attempts") && "bg-accent text-accent-foreground")}
            >
              <Link href={`/${locale}/students/me/attempts`}>
                <BookOpen className="h-3.5 w-3.5" />
                <span className="hidden sm:inline">My Exams</span>
              </Link>
            </Button>
          )}

          {/* Role badge */}
          {role && (
            <Badge
              variant={isTeacher ? "secondary" : "success"}
              className="hidden sm:inline-flex"
            >
              {isTeacher ? "Teacher" : "Student"}
            </Badge>
          )}

          {/* Logout */}
          <Button
            variant="ghost"
            size="sm"
            onClick={logout}
            title="Log out"
            className="hover:text-destructive"
          >
            <LogOut className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">Logout</span>
          </Button>
        </nav>
      </div>
    </header>
  );
}
