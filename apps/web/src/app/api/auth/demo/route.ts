import { NextResponse } from "next/server";

async function responseJson(response: Response): Promise<Record<string, unknown>> {
  try {
    return await response.json();
  } catch {
    return {};
  }
}

async function fetchWithRetry(
  url: string,
  options: RequestInit,
  maxRetries = 3,
): Promise<Response> {
  const isRetryable = (err: Error) => {
    const msg = err.message ?? "";
    return (
      msg.includes("ECONNREFUSED") ||
      msg.includes("EAI_AGAIN") ||
      msg.includes("ENOTFOUND") ||
      msg.includes("fetch failed")
    );
  };

  let lastError: Error | null = null;
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    if (attempt > 0) {
      const delay = Math.min(200 * 2 ** (attempt - 1) + Math.random() * 100, 2000);
      console.log(`[AUTH-DEMO] retry ${attempt}/${maxRetries} after ${Math.round(delay)}ms`);
      await new Promise((r) => setTimeout(r, delay));
    }
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 10000);
    try {
      const response = await fetch(url, { ...options, signal: controller.signal });
      clearTimeout(timeout);
      return response;
    } catch (err) {
      clearTimeout(timeout);
      lastError = err instanceof Error ? err : new Error(String(err));
      if (!isRetryable(lastError)) break;
    }
  }
  throw lastError ?? new Error("Request failed after retries");
}

export async function POST() {
  const fallbackTarget = process.env.RUNNING_IN_DOCKER === "1"
    ? "http://backend:8000"
    : "http://localhost:8000";
  const target = (process.env.INTERNAL_API_URL || fallbackTarget).replace(/\/+$/, "");
  const password = process.env.BOOTSTRAP_INVESTIGATOR_PASSWORD ?? process.env.DEMO_PASSWORD;
  if (process.env.DEBUG_PROXY === "1") {
    console.log(`[AUTH-DEMO] target=${target}, hasPassword=${!!password}`);
  }
  if (!password) return NextResponse.json({ detail: "demo disabled" }, { status: 503 });

  const body = new URLSearchParams();
  body.set("username", "investigator");
  body.set("password", password);

  let response: Response;
  try {
    response = await fetchWithRetry(`${target}/api/v1/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body,
    });
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    console.error(`[AUTH-DEMO] backend unreachable after retries: ${msg}`);
    return NextResponse.json(
      { error: "Authentication service unavailable. Please try again." },
      { status: 503 },
    );
  }
  const data = await responseJson(response);
  if (!response.ok) {
    return NextResponse.json(
      { error: String(data.detail ?? data.error ?? "Authentication failed") },
      { status: response.status },
    );
  }

  const { access_token: _at, csrf_token: _ct, token_type: _tt, ...safeData } = data;
  const nextResponse = NextResponse.json(safeData, { status: response.status });

  const getSetCookie = response.headers?.getSetCookie?.bind(response.headers);
  const setCookie = response.headers?.get("set-cookie");
  const upstreamSetCookie = getSetCookie ? getSetCookie() : setCookie ? [setCookie] : [];
  for (const cookie of upstreamSetCookie) {
    const name = cookie.split("=", 1)[0].trim().toLowerCase();
    if (name === "access_token" || name === "csrf_token") continue;
    nextResponse.headers.append("Set-Cookie", cookie);
  }

  const accessToken = typeof data.access_token === "string" ? data.access_token : "";
  const csrfToken = typeof data.csrf_token === "string" ? data.csrf_token : "";
  const maxAge = typeof data.expires_in === "number" ? data.expires_in : 3600;

  if (accessToken) {
    nextResponse.cookies.set("access_token", accessToken, {
      httpOnly: true,
      sameSite: "strict",
      secure: process.env.NODE_ENV === "production",
      path: "/",
      maxAge,
    });
  }

  if (csrfToken) {
    nextResponse.cookies.set("csrf_token", csrfToken, {
      httpOnly: false,
      sameSite: "strict",
      secure: process.env.NODE_ENV === "production",
      path: "/",
      maxAge,
    });
  }

  return nextResponse;
}
