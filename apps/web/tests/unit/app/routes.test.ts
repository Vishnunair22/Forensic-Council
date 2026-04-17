/** @jest-environment node */

const mockBackendUrlFor = jest.fn((path: string, base = "http://backend:8000") => `${base}${path}`);
const mockGetBackendBaseUrls = jest.fn(() => ["http://backend-a:8000", "http://backend-b:8000"]);

jest.mock("@/lib/backendTargets", () => ({
  backendUrlFor: (...args: [string, string?]) => mockBackendUrlFor(...args),
  getBackendBaseUrls: () => mockGetBackendBaseUrls(),
}));

describe("app api routes", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    process.env.BOOTSTRAP_INVESTIGATOR_PASSWORD = "investigator-pass";
    process.env.DEMO_PASSWORD = "demo-pass";
    Object.defineProperty(process.env, "NODE_ENV", { value: "test", writable: true, configurable: true });
    global.fetch = jest.fn();
  });

  it("demo auth route returns cookies on successful backend login", async () => {
    const { POST } = await import("@/app/api/auth/demo/route");

    (global.fetch as jest.Mock).mockResolvedValue({
      ok: true,
      json: async () => ({
        access_token: "jwt-token",
        expires_in: 1200,
        csrf_token: "csrf-token",
      }),
    });

    const response = await POST();
    const json = await response.json();
    const cookies = response.headers.get("set-cookie") ?? "";

    expect(response.status).toBe(200);
    expect(json.access_token).toBe("jwt-token");
    expect(cookies).toContain("access_token=jwt-token");
    expect(cookies).toContain("csrf_token=csrf-token");
  });

  it("demo auth route forwards backend auth failures", async () => {
    const { POST } = await import("@/app/api/auth/demo/route");

    (global.fetch as jest.Mock).mockResolvedValue({
      ok: false,
      status: 401,
      json: async () => ({ detail: "Authentication failed" }),
    });

    const response = await POST();
    const json = await response.json();

    expect(response.status).toBe(401);
    expect(json.error).toContain("Authentication failed");
  });

  it("proxy route retries retryable failures and returns the next backend response", async () => {
    const { NextRequest } = await import("next/server");
    const { GET } = await import("@/app/api/v1/[...path]/route");

    (global.fetch as jest.Mock)
      .mockResolvedValueOnce({
        status: 503,
        headers: new Headers({ "content-type": "application/json" }),
      })
      .mockResolvedValueOnce({
        status: 200,
        statusText: "OK",
        body: new ReadableStream({
          start(controller) {
            controller.enqueue(new TextEncoder().encode("{}"));
            controller.close();
          },
        }),
        headers: new Headers({ "content-type": "application/json", "x-upstream": "ok" }),
      });

    const request = new NextRequest("http://localhost/api/v1/sessions?limit=10", {
      method: "GET",
      headers: {
        authorization: "Bearer token",
        connection: "keep-alive",
      },
    });

    const response = await GET(request, {
      params: Promise.resolve({ path: ["sessions"] }),
    });

    expect(response.status).toBe(200);
    expect(response.headers.get("x-upstream")).toBe("ok");
    expect(global.fetch).toHaveBeenCalledTimes(2);
    expect((global.fetch as jest.Mock).mock.calls[0][1].headers.get("connection")).toBeNull();
  });

  it("proxy route returns 503 json when every backend fails", async () => {
    const { NextRequest } = await import("next/server");
    const { POST } = await import("@/app/api/v1/[...path]/route");

    (global.fetch as jest.Mock).mockRejectedValue(new Error("socket hang up"));

    const request = new NextRequest("http://localhost/api/v1/investigate", {
      method: "POST",
      body: JSON.stringify({ case_id: "CASE-1" }),
      headers: {
        "content-type": "application/json",
      },
    });

    const response = await POST(request, {
      params: Promise.resolve({ path: ["investigate"] }),
    });
    const json = await response.json();

    expect(response.status).toBe(503);
    expect(json.error).toContain("Failed to reach backend API");
  });
});
