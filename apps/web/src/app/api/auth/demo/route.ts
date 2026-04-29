import { NextResponse } from "next/server";

export async function POST() {
  const target = process.env.INTERNAL_API_URL ?? "http://localhost:8000";
  const password = process.env.BOOTSTRAP_INVESTIGATOR_PASSWORD ?? process.env.DEMO_PASSWORD;
  console.log(`[AUTH-DEMO] target=${target}, hasPassword=${!!password}`);
  if (!password) return NextResponse.json({ detail: "demo disabled" }, { status: 503 });

  const body = new URLSearchParams();
  body.set("username", "investigator");
  body.set("password", password);

  const r = await fetch(`${target}/api/v1/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });
  return new NextResponse(await r.arrayBuffer(), { status: r.status, headers: r.headers });
}
