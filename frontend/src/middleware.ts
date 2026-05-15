import createIntlMiddleware from "next-intl/middleware";
import { type NextRequest, NextResponse } from "next/server";

const DEFAULT_LOCALE = "fr";
const LOCALES = ["fr", "en"] as const;
const AUTH_FREE = ["/login", "/fr/login", "/en/login"];

const intlMiddleware = createIntlMiddleware({
  locales: LOCALES,
  defaultLocale: DEFAULT_LOCALE,
});

export function middleware(request: NextRequest): NextResponse {
  const { pathname } = request.nextUrl;

  // Skip auth for static assets and login pages
  if (
    pathname.startsWith("/api/") ||
    pathname.startsWith("/_next/") ||
    AUTH_FREE.some((p) => pathname === p || pathname.startsWith(p + "?"))
  ) {
    return intlMiddleware(request);
  }

  const token =
    request.cookies.get("access_token")?.value ||
    request.headers.get("Authorization")?.replace("Bearer ", "");

  if (!token) {
    const loginUrl = new URL(`/${DEFAULT_LOCALE}/login`, request.url);
    loginUrl.searchParams.set("redirect", pathname);
    return NextResponse.redirect(loginUrl);
  }

  return intlMiddleware(request);
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
