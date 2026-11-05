import { NextResponse, type NextRequest } from "next/server";

/**
 * Production answers on one address only. Vercel also serves the production deployment on
 * aliases such as rbz-rates-git-main-<team>.vercel.app; requests there are redirected to the
 * canonical host (NEXTAUTH_URL) so GitHub sign-in, whose cookies and callback belong to that
 * host, works wherever someone starts, and search engines see a single site.
 */
export function proxy(request: NextRequest) {
  const canonical = process.env.VERCEL_ENV === "production" ? process.env.NEXTAUTH_URL : undefined;
  if (!canonical) return NextResponse.next();
  const target = new URL(canonical);
  const host = request.headers.get("host");
  if (!host || host === target.host) return NextResponse.next();
  const url = new URL(request.nextUrl.pathname + request.nextUrl.search, target.origin);
  return NextResponse.redirect(url, 308);
}

export const config = {
  // everything except Next's static assets
  matcher: ["/((?!_next/static|_next/image|favicon.svg).*)"],
};
