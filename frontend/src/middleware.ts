import { NextRequest, NextResponse } from "next/server";

const DEFAULT_LOCALE = "fr";
const PUBLIC_PATHS = ["/api/", "/_next/", "/favicon.ico", "/login", `/${DEFAULT_LOCALE}/login`];

export function middleware(request: NextRequest): NextResponse {
  const { pathname } = request.nextUrl;

  if (PUBLIC_PATHS.some((p) => pathname.startsWith(p))) {
    return NextResponse.next();
  }

  const token =
    request.cookies.get("access_token")?.value ||
    request.headers.get("Authorization")?.replace("Bearer ", "");

  if (!token) {
    const loginUrl = new URL(`/${DEFAULT_LOCALE}/login`, request.url);
    loginUrl.searchParams.set("redirect", pathname);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
