import { NextResponse } from "next/server";

async function responseJson(response: Response): Promise<Record<string, unknown>> {
  try {
    return await response.json();
  } catch {
    return {};
  }
}

export async function POST() {
  const target = process.env.INTERNAL_API_URL ?? "http://localhost:8000";
  const password = process.env.BOOTSTRAP_INVESTIGATOR_PASSWORD ?? process.env.DEMO_PASSWORD;
  if (process.env.DEBUG_PROXY === "1") {
    console.log(`[AUTH-DEMO] target=${target}, hasPassword=${!!password}`);
  }
  if (!password) return NextResponse.json({ detail: "demo disabled" }, { status: 503 });

  const body = new URLSearchParams();
  body.set("username", "investigator");
  body.set("password", password);

  const response = await fetch(`${target}/api/v1/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });
  const data = await responseJson(response);
  if (!response.ok) {
    return NextResponse.json(
      { error: String(data.detail ?? data.error ?? "Authentication failed") },
      { status: response.status },
    );
  }

  const nextResponse = NextResponse.json(data, { status: response.status });

  const getSetCookie = response.headers?.getSetCookie?.bind(response.headers);
  const setCookie = response.headers?.get("set-cookie");
  const upstreamSetCookie = getSetCookie ? getSetCookie() : setCookie ? [setCookie] : [];
  for (const cookie of upstreamSetCookie) {
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
