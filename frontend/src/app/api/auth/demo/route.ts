import { NextResponse } from "next/server";

export async function POST() {
    const demoUsername = process.env.DEMO_USERNAME || "investigator";
    const demoPassword = process.env.DEMO_PASSWORD || process.env.NEXT_PUBLIC_DEMO_PASSWORD;
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

    if (!demoPassword) {
        return NextResponse.json(
            { error: "Demo credentials not configured on server (DEMO_PASSWORD)." },
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
    } catch (error) {
        return NextResponse.json(
            { error: "Failed to connect to backend auth service" },
            { status: 500 }
        );
    }
}
