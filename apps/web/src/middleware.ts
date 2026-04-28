import { NextRequest, NextResponse } from "next/server";

export function middleware(request: NextRequest) {
  const nonce = btoa(crypto.randomUUID()).replace(/=/g, "");

  const isProd = process.env.NODE_ENV === "production";
  const connectSrc = isProd
    ? "'self'"
    : "'self' ws://localhost wss://localhost ws://localhost:3000 wss://localhost:3000";

  const cspHeader = `
    default-src 'self';
    script-src 'self' 'nonce-${nonce}' 'strict-dynamic' ${!isProd ? "'unsafe-eval'" : ""};
    style-src 'self' 'unsafe-inline';
    img-src 'self' blob: data:;
    connect-src ${connectSrc};
    font-src 'self' data:;
    frame-ancestors 'none';
    form-action 'self';
  `.replace(/\s{2,}/g, " ").trim();

  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-nonce", nonce);
  requestHeaders.set("Content-Security-Policy", cspHeader);

  const response = NextResponse.next({
    request: {
      headers: requestHeaders,
    },
  });

  response.headers.set("Content-Security-Policy", cspHeader);
  return response;
}

export const config = {
  matcher: [
    {
      source: "/((?!api|_next/static|_next/image|favicon.ico).*)",
      missing: [
        { type: "header", key: "next-router-prefetch" },
        { type: "header", key: "purpose", value: "prefetch" },
      ],
    },
  ],
};
