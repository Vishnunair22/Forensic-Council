import { NextResponse } from "next/server";

// Retry settings: the backend health check can pass while bootstrap user
// creation is still in progress (async DB writes after startup). Retry a few
// times with backoff so the first page-load auth doesn't fail spuriously.
const MAX_RETRIES = 4;
const RETRY_DELAY_MS = [500, 1000, 2000, 3000]; // progressive back-off

function sleep(ms: number) {
    return new Promise((resolve) => setTimeout(resolve, ms));
}

export async function POST() {
    const demoUsername = process.env.DEMO_USERNAME || "investigator";
    const demoPassword = process.env.DEMO_PASSWORD || process.env.NEXT_PUBLIC_DEMO_PASSWORD;

    // CRITICAL: Server-side Next.js API routes run inside the frontend Docker container.
    // When deployed via Docker Compose, "localhost:8000" refers to the frontend container
    // itself — NOT the backend.  We must use the internal Docker network service name.
    //
    // INTERNAL_API_URL=http://forensic_api:8000  (set in docker-compose frontend env)
    // NEXT_PUBLIC_API_URL=http://localhost:8000  (browser-facing, baked at build time)
    const apiUrl =
        process.env.INTERNAL_API_URL ||
        process.env.NEXT_PUBLIC_API_URL ||
        "http://localhost:8000";

    if (!demoPassword) {
        return NextResponse.json(
            { error: "Demo credentials not configured on server. Set DEMO_PASSWORD or NEXT_PUBLIC_DEMO_PASSWORD in .env" },
            { status: 500 }
        );
    }

    const formData = new URLSearchParams();
    formData.append("username", demoUsername);
    formData.append("password", demoPassword);

    let lastError = "";

    for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
        if (attempt > 0) {
            await sleep(RETRY_DELAY_MS[attempt - 1] ?? 3000);
        }

        try {
            const res = await fetch(`${apiUrl}/api/v1/auth/login`, {
                method: "POST",
                headers: { "Content-Type": "application/x-www-form-urlencoded" },
                body: formData.toString(),
                signal: AbortSignal.timeout(8_000),
            });

            if (!res.ok) {
                const errorData = await res.json().catch(() => ({}));
                // Auth credential errors (4xx) are permanent — don't retry.
                if (res.status >= 400 && res.status < 500) {
                    return NextResponse.json(
                        { error: errorData.detail || "Authentication failed" },
                        { status: res.status }
                    );
                }
                // 5xx from backend — may be transient, retry
                lastError = errorData.detail || `Backend returned ${res.status}`;
                continue;
            }

            const data = await res.json();
            const nextRes = NextResponse.json(data);
            // Set the auth cookie via the Next.js cookies API — this is more reliable
            // than forwarding the raw Set-Cookie header, which can be silently stripped
            // or mangled by Next.js App Router header handling.
            // secure=false: backend uses secure=False in dev; Next.js standalone runs
            // NODE_ENV=production but the app may still be served over plain HTTP.
            // The proxy (Caddy) handles HTTPS termination — the cookie is HttpOnly so
            // it is never exposed to JavaScript regardless of the Secure flag.
            nextRes.cookies.set("access_token", data.access_token as string, {
                httpOnly: true,
                path: "/",
                sameSite: "lax",
                maxAge: (data.expires_in as number) ?? 3600,
                secure: false,
            });
            return nextRes;
        } catch (error: unknown) {
            const msg = error instanceof Error ? error.message : "Unknown error";
            const isTimeout = msg.includes("timeout") || msg.includes("abort");
            lastError = isTimeout ? "timeout" : msg;
            // Connection errors are retryable
        }
    }

    const isTimeout = lastError === "timeout";
    return NextResponse.json(
        {
            error: isTimeout
                ? "Backend is not reachable — is the API server running?"
                : "Failed to connect to backend auth service",
        },
        { status: 503 }
    );
}
