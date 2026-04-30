import { NextRequest, NextResponse } from "next/server";

import { backendUrlFor, getBackendBaseUrls } from "@/lib/backendTargets";

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
        signal: AbortSignal.timeout(30_000),
      });
      if (RETRYABLE_STATUSES.has(upstream.status)) {
        lastError = new Error(`Backend returned ${upstream.status}`);
        continue;
      }
      return new NextResponse(await upstreamBody(upstream), {
        status: upstream.status,
        headers: filteredHeaders(upstream.headers),
      });
    } catch (error) {
      lastError = error;
    }
  }

  return NextResponse.json(
    {
      error: `Failed to reach backend API: ${
        lastError instanceof Error ? lastError.message : "unknown error"
      }`,
    },
    { status: 503 },
  );
}

export async function GET(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  return forward(req, ctx);
}

export async function POST(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  return forward(req, ctx);
}

export async function PUT(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  return forward(req, ctx);
}

export async function PATCH(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  return forward(req, ctx);
}

export async function DELETE(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  return forward(req, ctx);
}
