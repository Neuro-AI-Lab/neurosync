/**
 * Auth gate for /dashboard/**.
 * Anyone without an access cookie is bounced to /login.
 */

import { NextRequest, NextResponse } from "next/server";

import { ACCESS_COOKIE } from "./lib/config";

export function middleware(req: NextRequest) {
  const access = req.cookies.get(ACCESS_COOKIE);
  if (!access || access.value.length === 0) {
    const url = req.nextUrl.clone();
    url.pathname = "/login";
    url.searchParams.set("next", req.nextUrl.pathname);
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/dashboard/:path*"],
};
