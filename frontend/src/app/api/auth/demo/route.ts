import { NextResponse } from "next/server";

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
            { error: "Demo credentials not configured on server. Set NEXT_PUBLIC_DEMO_PASSWORD in .env" },
            { status: 500 }
        );
    }

    try {
        const formData = new URLSearchParams();
        formData.append("username", demoUsername);
        formData.append("password", demoPassword);

        const res = await fetch(`${apiUrl}/api/v1/auth/login`, {
            method: "POST",
            headers: { "Content-Type": "application/x-www-form-urlencoded" },
            body: formData.toString(),
            // Abort if the backend is unreachable (e.g. still starting up)
            signal: AbortSignal.timeout(10_000),
        });

        if (!res.ok) {
            const errorData = await res.json().catch(() => ({}));
            return NextResponse.json(
                { error: errorData.detail || "Authentication failed" },
                { status: res.status }
            );
        }

        const data = await res.json();
        return NextResponse.json(data);
    } catch (error: unknown) {
        const msg = error instanceof Error ? error.message : "Unknown error";
        const isTimeout = msg.includes("timeout") || msg.includes("abort");
        return NextResponse.json(
            {
                error: isTimeout
                    ? "Backend is not reachable — is the API server running?"
                    : "Failed to connect to backend auth service",
            },
            { status: 503 }
        );
    }
}
