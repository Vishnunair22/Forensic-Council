import { backendUrlFor, getBackendBaseUrls } from "@/lib/backendTargets";
import { NextRequest, NextResponse } from "next/server";

const RETRYABLE_STATUSES = new Set([502, 503, 504]);
// 30 s for regular requests; long-poll / upload endpoints get more time via streaming
// const PROXY_TIMEOUT_MS = 30_000;
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
    // skip hop-by-hop and set-cookie
    if (
      !HOP_BY_HOP_HEADERS.has(key.toLowerCase()) &&
      key.toLowerCase() !== "set-cookie"
    ) {
      headers.set(key, value);
    }
  });

  // Specifically handle multiple Set-Cookie headers correctly via getSetCookie()
  // if the environment supports it (Next.js 15 / Node 20.x+)
  const responseHeaders = response.headers as unknown as {
    getSetCookie?: () => string[];
  };
  if (typeof responseHeaders.getSetCookie === "function") {
    const cookies = responseHeaders.getSetCookie();
    cookies.forEach((c: string) => headers.append("Set-Cookie", c));
  } else {
    // Fallback: headers.get('set-cookie') might return multiple cookies
    // separated by comma-space, which we try to re-split.
    const raw = response.headers.get("set-cookie");
    if (raw) {
      // Very naive split for legacy environments — most modern Node/Next environments
      // should hit the getSetCookie path above.
      headers.set("Set-Cookie", raw);
    }
  }

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
  
  // Is this an upload or a heavy forensic operation?
  const isHeavyPath =
    path.includes("upload") ||
    path.includes("deep-analysis") ||
    path.includes("video") ||
    path.includes("report") ||
    path.includes("decision") ||
    path[0] === "investigate"; // POST /api/v1/investigate is the evidence upload endpoint
  const timeoutMs = isHeavyPath ? 300_000 : 60_000; // 5 min for uploads/deep, 1 min otherwise

  // Optimization: Do not buffer the entire request in memory for large forensic uploads.
  // We stream the Request.body directly to the fetch call.
  // Note: Body is only supported for state-changing methods.
  const canHaveBody = !["GET", "HEAD"].includes(request.method);
  const streamBody = canHaveBody ? request.body : undefined;

  let lastError = "Backend proxy request failed";
  let lastBackendUrl = backendBaseUrls[0] || "http://localhost:8000";

  for (const baseUrl of backendBaseUrls) {
    lastBackendUrl = baseUrl;

    try {
      const response = await fetch(backendUrlFor(pathname, baseUrl), {
        method: request.method,
        headers: requestHeaders,
        body: streamBody,
        // @ts-expect-error: 'duplex' is required when body is a stream in some environments
        duplex: streamBody ? 'half' : undefined,
        redirect: "manual",
        signal: AbortSignal.timeout(timeoutMs),
      });

      if (RETRYABLE_STATUSES.has(response.status)) {
        lastError = `Backend returned ${response.status} via ${baseUrl}`;
        continue;
      }

      const responseHeaders = copyResponseHeaders(response);
      const contentType = responseHeaders.get("content-type");
      const isHtml = contentType?.includes("text/html");

      if (response.status >= 500 && isHtml) {
        lastError = `Backend returned HTML error page (${response.status})`;
        continue;
      }

      return new Response(response.body, {
        status: response.status,
        statusText: response.statusText,
        headers: responseHeaders,
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
