import { NextRequest, NextResponse } from "next/server";

export function middleware(request: NextRequest) {
  const isProd = process.env.NODE_ENV === "production";
  const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "";

  // Forward CSRF token on mutating requests to API routes
  const csrfToken = request.cookies.get("csrf_token")?.value;
  const requestHeaders = new Headers(request.headers);
  if (csrfToken && ["POST", "PUT", "DELETE", "PATCH"].includes(request.method)) {
    requestHeaders.set("X-CSRF-Token", csrfToken);
  }

  // Derive WS origin from NEXT_PUBLIC_API_URL
  let wsOrigin = "";
  let httpOrigin = "";
  if (apiUrl) {
    try {
      const u = new URL(apiUrl);
      wsOrigin = `${u.protocol === "https:" ? "wss:" : "ws:"}//${u.host}`;
      httpOrigin = `${u.protocol}//${u.host}`;
    } catch { /* ignore */ }
  }

  const sameOriginWs = "'self' wss: ws:";
  const prodConnectSrc = `'self' ${sameOriginWs} ${wsOrigin} ${httpOrigin}`.trim().replace(/\s+/g, " ");
  const devConnectSrc = `'self' ws://localhost wss://localhost ws://localhost:3000 wss://localhost:3000 ws://localhost:8000 wss://localhost:8000 http://localhost:8000 https://localhost:8000${wsOrigin ? ` ${wsOrigin}` : ""}${httpOrigin ? ` ${httpOrigin}` : ""}`;
  
  const connectSrc = isProd ? prodConnectSrc : devConnectSrc;

  const cspHeader = `
    default-src 'self';
    script-src 'self' 'unsafe-inline' ${!isProd ? "'unsafe-eval'" : ""};
    style-src 'self' 'unsafe-inline';
    img-src 'self' blob: data:;
    connect-src ${connectSrc};
    font-src 'self' data:;
    frame-ancestors 'none';
    form-action 'self';
  `.replace(/\s{2,}/g, " ").trim();

  const response = NextResponse.next({
    request: { headers: requestHeaders },
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
