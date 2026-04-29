import { NextRequest, NextResponse } from "next/server";

const TARGET = process.env.INTERNAL_API_URL ?? "http://localhost:8000";

async function forward(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  const { path } = await ctx.params;
  const url = `${TARGET}/api/v1/${path.join("/")}${req.nextUrl.search}`;
  console.log(`[PROXY] ${req.method} ${url}`);
  const init: RequestInit = {
    method: req.method,
    headers: req.headers,
    body: ["GET", "HEAD"].includes(req.method) ? undefined : await req.arrayBuffer(),
    redirect: "manual",
  };
  const upstream = await fetch(url, init);
  const body = await upstream.arrayBuffer();
  return new NextResponse(body, {
    status: upstream.status,
    headers: upstream.headers,
  });
}
export { forward as GET, forward as POST, forward as PUT, forward as DELETE, forward as PATCH };
