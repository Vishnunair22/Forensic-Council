import { NextRequest, NextResponse } from "next/server";

import { backendUrlFor, getBackendBaseUrls } from "@/lib/backendTargets";

// DISABLE_NEXT_API_PROXY: set to "1" in production Docker to force all API
// traffic through Caddy (prevents a second auth/CSRF surface on port 3000).
// Leave unset in dev so direct localhost:3000 works for local testing.
const DISABLE_NEXT_API_PROXY = process.env.DISABLE_NEXT_API_PROXY === "1";

const HOP_BY_HOP_HEADERS = new Set([
  "connection",
  "content-encoding",
  "content-length",
  "host",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
]);
const RETRYABLE_STATUSES = new Set([502, 503, 504]);

function filteredHeaders(headers: Headers): Headers {
  const next = new Headers();
  for (const [key, value] of headers.entries()) {
    if (!HOP_BY_HOP_HEADERS.has(key.toLowerCase())) {
      next.set(key, value);
    }
  }
  return next;
}

async function upstreamBody(response: Response): Promise<BodyInit | null> {
  if (typeof response.arrayBuffer === "function") {
    return await response.arrayBuffer();
  }
  if (response.body) return response.body;
  const text = await response.text().catch(() => "");
  return text;
}

async function forward(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  const { path } = await ctx.params;
  const apiPath = `/api/v1/${path.join("/")}${req.nextUrl.search}`;
  const body = ["GET", "HEAD"].includes(req.method) ? undefined : await req.arrayBuffer();
  const headers = filteredHeaders(req.headers);
  let lastError: unknown = null;

  for (const base of getBackendBaseUrls()) {
    const url = backendUrlFor(apiPath, base);
    if (process.env.DEBUG_PROXY === "1") {
      console.log(`[PROXY] ${req.method} ${url}`);
    }
    try {
      const upstream = await fetch(url, {
        method: req.method,
        headers,
        body,
        redirect: "manual",
        signal: AbortSignal.timeout(8_000),
      });
      if (RETRYABLE_STATUSES.has(upstream.status)) {
        const isIdempotent = ["GET", "HEAD", "OPTIONS", "PUT", "DELETE"].includes(req.method);
        if (isIdempotent) {
          lastError = new Error(`Backend returned ${upstream.status}`);
          continue;
        }
        break;
      }
      return new NextResponse(await upstreamBody(upstream), {
        status: upstream.status,
        headers: filteredHeaders(upstream.headers),
      });
    } catch (error) {
      lastError = error;
    }
  }

  const errResp = NextResponse.json(
    {
      error: `Failed to reach backend API: ${
        lastError instanceof Error ? lastError.message : "unknown error"
      }`,
    },
    { status: 503 },
  );
  errResp.headers.set("Cache-Control", "no-store");
  return errResp;
}

function proxyGuard(): NextResponse | null {
  if (DISABLE_NEXT_API_PROXY) {
    return new NextResponse("Not found", { status: 404 });
  }
  return null;
}

export async function GET(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  const guard = proxyGuard();
  if (guard) return guard;

  const { path } = await ctx.params;
  const apiPath = `/api/v1/${path.join("/")}`;

  if (apiPath.endsWith("/live")) {
    const wsEnv = process.env.NEXT_PUBLIC_WS_URL;
    return new NextResponse(
      `WebSocket not supported via Next.js proxy. ${wsEnv ? "NEXT_PUBLIC_WS_URL is set." : "Use Caddy or set NEXT_PUBLIC_WS_URL."}`,
      { status: 426 },
    );
  }
  return forward(req, ctx);
}

export async function POST(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  const guard = proxyGuard();
  if (guard) return guard;
  return forward(req, ctx);
}

export async function PUT(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  const guard = proxyGuard();
  if (guard) return guard;
  return forward(req, ctx);
}

export async function PATCH(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  const guard = proxyGuard();
  if (guard) return guard;
  return forward(req, ctx);
}

export async function DELETE(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  const guard = proxyGuard();
  if (guard) return guard;
  return forward(req, ctx);
}
