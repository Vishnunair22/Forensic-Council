import { NextResponse } from "next/server";
import { backendUrlFor, getBackendBaseUrls } from "@/lib/backendTargets";

const MAX_RETRIES = 2;
const RETRY_DELAY_MS = [500, 1500];

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export async function POST() {
  const demoUsername = process.env.DEMO_USERNAME || "investigator";
  const demoPassword =
    process.env.BOOTSTRAP_INVESTIGATOR_PASSWORD ||
    process.env.DEMO_PASSWORD ||
    process.env.NEXT_PUBLIC_DEMO_PASSWORD ||
    "demo_dev_only_not_for_production";
  const backendBaseUrls = getBackendBaseUrls();

  const formData = new URLSearchParams();
  formData.append("username", demoUsername);
  formData.append("password", demoPassword);

  let lastError = "";
  let lastBackendUrl = backendBaseUrls[0] || "http://localhost:8000";

  for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
    if (attempt > 0) {
      await sleep(RETRY_DELAY_MS[attempt - 1] ?? 3000);
    }

    for (const baseUrl of backendBaseUrls) {
      lastBackendUrl = baseUrl;
      try {
        // High-speed reachability check (5s)
        const response = await fetch(
          backendUrlFor("/api/v1/auth/login", baseUrl),
          {
            method: "POST",
            headers: { "Content-Type": "application/x-www-form-urlencoded" },
            body: formData.toString(),
            signal: AbortSignal.timeout(5000), 
          },
        );

        if (!response.ok) {
          const errorData = await response.json().catch(() => ({}));

          if (response.status >= 400 && response.status < 500) {
            return NextResponse.json(
              { error: errorData.detail || "Authentication failed" },
              { status: response.status },
            );
          }

          lastError =
            errorData.detail ||
            `Backend returned ${response.status} via ${baseUrl}`;
          continue;
        }

        const data = await response.json();
        const nextResponse = NextResponse.json(data);
        const cookieSecure = process.env.COOKIE_SECURE
          ? process.env.COOKIE_SECURE === "true"
          : process.env.NODE_ENV === "production";

        // Set HttpOnly cookie for browser-based auth
        nextResponse.cookies.set("access_token", data.access_token as string, {
          httpOnly: true,
          path: "/",
          sameSite: "lax",
          maxAge: (data.expires_in as number) ?? 3600,
          secure: cookieSecure,
        });

        // Also set CSRF token cookie if returned by backend
        if (data.csrf_token) {
          nextResponse.cookies.set("csrf_token", data.csrf_token as string, {
            httpOnly: false,
            path: "/",
            sameSite: "lax",
            maxAge: (data.expires_in as number) ?? 3600,
            secure: cookieSecure,
          });
        }

        return nextResponse;
        } catch (error: unknown) {
          const msg = error instanceof Error ? error.message : "Unknown error";
          const isTimeout = msg.includes("timeout") || msg.includes("abort");
          
          // CRITICAL: Log diagnostic info to server console (visible in docker logs)
          console.error(`[AUTH_HANDSHAKE] Connection failed to ${baseUrl}: ${msg}`);
          
          lastError = isTimeout ? "timeout" : `${msg} via ${baseUrl}`;
        }
      }
    }

  const isTimeout = lastError === "timeout";
  return NextResponse.json(
    {
      error: isTimeout
        ? "Backend is not reachable - is the API server running?"
        : `Failed to connect to backend auth service (${lastBackendUrl})`,
    },
    { status: 503 },
  );
}
