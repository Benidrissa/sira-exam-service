"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ChevronRight, Home } from "lucide-react";
import { cn } from "@/lib/utils";

interface Crumb {
  label: string;
  href?: string;
}

function buildCrumbs(pathname: string): Crumb[] | null {
  // Match /locale/...rest
  const m = pathname.match(/^\/([a-z]{2})(\/.*)?$/);
  if (!m) return null;
  const locale = m[1];
  const rest = m[2] ?? "/";
  const base = `/${locale}`;

  const home: Crumb = { label: "Home", href: `${base}/` };

  // Exact + prefix matches — order matters (most specific first)
  if (/^\/exams\/[^/]+\/submissions\/[^/]+/.test(rest))
    return [home, { label: "Submissions", href: `${base}/exams/${rest.split("/")[2]}/submissions` }, { label: "Attempt Review" }];

  if (/^\/exams\/[^/]+\/submissions/.test(rest))
    return [home, { label: "Submissions" }];

  if (/^\/exams\/[^/]+\/results/.test(rest))
    return [home, { label: "Grading" }];

  if (/^\/exams\/[^/]+\/complaints/.test(rest))
    return [home, { label: "Complaints" }];

  if (/^\/banks\/[^/]+\/review/.test(rest))
    return [home, { label: "Review Board" }];

  if (/^\/classes\/[^/]+/.test(rest))
    return [home, { label: "Classes", href: `${base}/classes` }, { label: "Class Detail" }];

  if (rest === "/classes")
    return [home, { label: "Classes" }];

  if (rest === "/create")
    return [home, { label: "New Exam" }];

  if (/^\/proctor\/sessions\/[^/]+/.test(rest))
    return [home, { label: "Proctor", href: `${base}/proctor/dashboard` }, { label: "Session" }];

  if (rest === "/proctor/dashboard")
    return [home, { label: "Proctor" }];

  if (rest === "/students/me/attempts")
    return [home, { label: "My Exams" }];

  if (/^\/attempts\/[^/]+\/review/.test(rest))
    return [home, { label: "My Exams", href: `${base}/students/me/attempts` }, { label: "Review" }];

  if (rest === "/" || rest === "")
    return null; // home page — no breadcrumb needed

  return null;
}

const HIDDEN_PATHS = ["/login", "/session/pre-check", "/exams/"];

function shouldHide(pathname: string): boolean {
  return HIDDEN_PATHS.some((p) => {
    if (p === "/exams/") return /\/exams\/[^/]+\/play/.test(pathname);
    return pathname.includes(p);
  });
}

export function Breadcrumbs() {
  const pathname = usePathname() ?? "";

  if (shouldHide(pathname)) return null;

  const crumbs = buildCrumbs(pathname);
  if (!crumbs || crumbs.length <= 1) return null;

  return (
    <nav
      aria-label="Breadcrumb"
      className="border-b border-border bg-muted/30 px-4 sm:px-6"
    >
      <ol className="mx-auto flex max-w-5xl items-center gap-1 py-2 text-sm">
        {crumbs.map((crumb, i) => {
          const isLast = i === crumbs.length - 1;
          return (
            <li key={i} className="flex items-center gap-1">
              {i > 0 && <ChevronRight className="h-3.5 w-3.5 text-muted-foreground shrink-0" />}
              {crumb.href && !isLast ? (
                <Link
                  href={crumb.href}
                  className={cn(
                    "flex items-center gap-1 text-muted-foreground hover:text-foreground transition-colors",
                    i === 0 && "hover:text-primary",
                  )}
                >
                  {i === 0 && <Home className="h-3.5 w-3.5" />}
                  {crumb.label}
                </Link>
              ) : (
                <span className={cn(
                  "flex items-center gap-1",
                  isLast ? "text-foreground font-medium" : "text-muted-foreground",
                )}>
                  {i === 0 && <Home className="h-3.5 w-3.5" />}
                  {crumb.label}
                </span>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
