import { backendUrlFor, getBackendBaseUrls } from "@/lib/backendTargets";
import { NextRequest, NextResponse } from "next/server";

const RETRYABLE_STATUSES = new Set([502, 503, 504]);
const HOP_BY_HOP_HEADERS = new Set([
  "connection",
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

function copyRequestHeaders(request: NextRequest) {
  const headers = new Headers();

  request.headers.forEach((value, key) => {
    if (!HOP_BY_HOP_HEADERS.has(key.toLowerCase())) {
      headers.set(key, value);
    }
  });

  return headers;
}

function copyResponseHeaders(response: Response) {
  const headers = new Headers();

  response.headers.forEach((value, key) => {
    if (!HOP_BY_HOP_HEADERS.has(key.toLowerCase())) {
      headers.set(key, value);
    }
  });

  return headers;
}

async function proxyRequest(
  request: NextRequest,
  path: string[],
): Promise<Response> {
  const backendBaseUrls = getBackendBaseUrls();
  const search = request.nextUrl.search || "";
  const pathname = `/api/v1/${path.join("/")}${search}`;
  const requestHeaders = copyRequestHeaders(request);
  const requestBody =
    request.method === "GET" || request.method === "HEAD"
      ? undefined
      : await request.arrayBuffer();

  let lastError = "Backend proxy request failed";
  let lastBackendUrl = backendBaseUrls[0] || "http://localhost:8000";

  for (const baseUrl of backendBaseUrls) {
    lastBackendUrl = baseUrl;

    try {
      const response = await fetch(backendUrlFor(pathname, baseUrl), {
        method: request.method,
        headers: requestHeaders,
        body: requestBody,
        redirect: "manual",
      });

      if (RETRYABLE_STATUSES.has(response.status)) {
        lastError = `Backend returned ${response.status} via ${baseUrl}`;
        continue;
      }

      return new Response(response.body, {
        status: response.status,
        statusText: response.statusText,
        headers: copyResponseHeaders(response),
      });
    } catch (error: unknown) {
      lastError = error instanceof Error ? error.message : "Unknown proxy error";
    }
  }

  return NextResponse.json(
    {
      error: `Failed to reach backend API (${lastBackendUrl})`,
      detail: lastError,
    },
    { status: 503 },
  );
}

type RouteContext = {
  params: Promise<{
    path: string[];
  }>;
};

export async function GET(request: NextRequest, context: RouteContext) {
  const { path } = await context.params;
  return proxyRequest(request, path);
}

export async function POST(request: NextRequest, context: RouteContext) {
  const { path } = await context.params;
  return proxyRequest(request, path);
}

export async function PUT(request: NextRequest, context: RouteContext) {
  const { path } = await context.params;
  return proxyRequest(request, path);
}

export async function PATCH(request: NextRequest, context: RouteContext) {
  const { path } = await context.params;
  return proxyRequest(request, path);
}

export async function DELETE(request: NextRequest, context: RouteContext) {
  const { path } = await context.params;
  return proxyRequest(request, path);
}
