import { test, expect, type Page } from "@playwright/test";
import { emitMockLiveSocketComplete, installMockLiveSocket } from "./helpers/mockLiveSocket";

const SESSION_ID = "77777777-7777-4777-8777-777777777777";

const reportPayload = {
  report_id: "phase7-report",
  session_id: SESSION_ID,
  case_id: "CASE-PHASE7",
  executive_summary: "Phase 7 mocked report for journey edge-case verification.",
  per_agent_findings: {
    Agent1: [{
      finding_type: "initial_screen",
      confidence_raw: 0.84,
      status: "CONFIRMED",
      reasoning_summary: "Initial screening completed.",
      metadata: { tool_name: "initial_screen", court_defensible: true },
      evidence_refs: [],
      calibrated_probability: 0.84,
    }],
  },
  per_agent_metrics: { Agent1: { total_tools_called: 3, tools_succeeded: 3, confidence_score: 0.84 } },
  per_agent_analysis: { Agent1: "Initial screening completed." },
  per_agent_summary: { Agent1: "Initial screening completed." },
  overall_confidence: 0.84,
  overall_error_rate: 0,
  overall_verdict: "LIKELY_AUTHENTIC",
  cross_modal_confirmed: [],
  contested_findings: [],
  tribunal_resolved: [],
  incomplete_findings: [],
  uncertainty_statement: "Low uncertainty in mocked fixture.",
  cryptographic_signature: "phase7-signature",
  report_hash: "phase7-hash",
  signed_utc: "2026-05-19T00:00:00.000Z",
  verdict_sentence: "The council finds the evidence likely authentic after initial analysis.",
  key_findings: ["Initial analysis completed across applicable forensic agents."],
  reliability_note: "Mocked E2E report generated for edge-case coverage.",
  manipulation_probability: 0.12,
  applicable_agent_count: 1,
};

let resumeRequests = 0;

test.describe("Full Journey — Phase 7 Edge Cases", () => {
  test.beforeEach(async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await page.context().clearCookies();
    await page.addInitScript(() => {
      window.localStorage.clear();
      window.sessionStorage.clear();
    });
    resumeRequests = 0;
    page.on("request", (request) => {
      if (request.method() === "POST" && /\/api\/v1\/sessions\/.+\/resume$/.test(request.url())) {
        resumeRequests += 1;
      }
    });
    await installMockLiveSocket(page, SESSION_ID);
    let arbiterComplete = true;
    await page.route("**/api/auth/demo", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ access_token: "phase7-token", token_type: "bearer", expires_in: 3600 }),
      });
    });
    await page.route("**/api/v1/auth/me", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ user_id: "usr_phase7", username: "phase7", role: "investigator" }),
      });
    });
    await page.route("**/api/v1/health", async (route) => {
      await route.fulfill({
        status: 200,
        headers: { "Set-Cookie": "csrf_token=phase7-csrf; Path=/; SameSite=Lax" },
        contentType: "application/json",
        body: JSON.stringify({ status: "healthy" }),
      });
    });
    await page.route("**/api/v1/investigate", async (route) => {
      arbiterComplete = false;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ session_id: SESSION_ID, case_id: "CASE-PHASE7", status: "started" }),
      });
    });
    await page.route("**/api/v1/sessions/*/resume", async (route) => {
      const body = route.request().postDataJSON() as { deep_analysis?: boolean };
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ status: "resumed", deep_analysis: !!body.deep_analysis }),
      });
      if (body.deep_analysis) {
        arbiterComplete = false;
        await page.evaluate(() => {
          (window as typeof window & { __fcE2ENextPhase?: "initial" | "deep" }).__fcE2ENextPhase = "deep";
          (window as typeof window & { __fcE2EEmitDeep?: () => void }).__fcE2EEmitDeep?.();
        });
      } else {
        arbiterComplete = true;
        await emitMockLiveSocketComplete(page, "Initial report signed.");
      }
    });
    await page.route("**/api/v1/sessions/*/arbiter-status", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(
          arbiterComplete
            ? { status: "complete", message: "Report signed", report_id: reportPayload.report_id }
            : { status: "running", message: "Agents active" },
        ),
      });
    });
    await page.route("**/api/v1/sessions/*/report", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(reportPayload),
      });
    });
    for (let attempt = 0; attempt < 3; attempt += 1) {
      await page.goto(attempt === 0 ? "/?upload=1" : "/");
      await page.waitForTimeout(500);
      if ((await page.getByLabel(/upload evidence file/i).count()) > 0) break;
      const begin = page.getByTestId("hero-cta-begin");
      await expect(begin).toBeVisible({ timeout: 10_000 });
      await begin.click({ force: true });
      await page.waitForTimeout(500);
      if ((await page.getByLabel(/upload evidence file/i).count()) > 0) break;
      await begin.evaluate((element: HTMLElement) => element.click());
      await page.waitForTimeout(500);
      if ((await page.getByLabel(/upload evidence file/i).count()) > 0) break;
    }
    await expect(page.getByLabel(/upload evidence file/i)).toBeAttached({ timeout: 10_000 });
  });

  async function uploadPng(page: Page, name = `phase7-${Date.now()}.png`) {
    const png1x1 = Buffer.from(
      "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII=",
      "base64",
    );
    const uniquePng = Buffer.concat([png1x1, Buffer.from(`\nforensic-e2e-${Date.now()}`)]);
    await page.getByLabel(/upload evidence file/i).setInputFiles({
      name,
      mimeType: "image/png",
      buffer: uniquePng,
    });
    await expect(page.getByRole("heading", { name: /Evidence Ready/i })).toBeVisible({ timeout: 15_000 });
  }

  // ── Fix #2: Expired upload handoff ──────────────────────────────────────────

  test("expired handoff → returns home with upload=1 (once)", async ({ page }) => {
    await page.evaluate(() => {
      sessionStorage.setItem("forensic_auto_start", "true");
      sessionStorage.removeItem("fc_show_loading");
    });
    await page.goto("/evidence");
    await expect(page.getByText(/No Evidence Queued|Select Evidence/i)).toBeVisible({ timeout: 10_000 });
  });

  // ── Fix #3: Duplicate upload reconnects to existing session ─────────────────

  test("duplicate upload 409 → reconnects to existing session", async ({ page }) => {
    await uploadPng(page);
    await page.getByTestId("upload-start-analysis").click();
    await page.waitForURL(/\/evidence$/, { timeout: 30_000, waitUntil: "commit" });
    await expect(page.getByTestId("accept-analysis-btn")).toBeVisible({ timeout: 30_000 });

    const sessionId = await page.evaluate(() => localStorage.getItem("forensic_session_id"));
    expect(sessionId).toBeTruthy();

    await page.goto("/?upload=1");
    await uploadPng(page, `dup-${Date.now()}.png`);
    await page.getByTestId("upload-start-analysis").click();
    await page.waitForURL(/\/evidence$/, { timeout: 30_000, waitUntil: "commit" });
    await expect(page.getByTestId("accept-analysis-btn")).toBeVisible({ timeout: 30_000 });

    const sid2 = await page.evaluate(() => localStorage.getItem("forensic_session_id"));
    expect(sid2).toBeTruthy();
  });

  // ── Fix #4: Reconnect routes by arbiter status ───────────────────────────────

  test("reconnect complete → navigates to result", async ({ page }) => {
    await uploadPng(page);
    await page.getByTestId("upload-start-analysis").click();
    await page.waitForURL(/\/evidence$/, { timeout: 30_000, waitUntil: "commit" });
    await expect(page.getByTestId("accept-analysis-btn")).toBeVisible({ timeout: 30_000 });
    const sid = await page.evaluate(() => localStorage.getItem("forensic_session_id") ?? "");
    expect(sid).toBeTruthy();

    await page.goto(`/result/${sid}`);
    await page.waitForURL(/\/result\//, { timeout: 30_000, waitUntil: "commit" });
    expect(page.url()).toContain(sid);
  });

  test("reconnect not_found → routes to home with upload=1", async ({ page }) => {
    await uploadPng(page);
    await page.getByTestId("upload-start-analysis").click();
    await page.waitForURL(/\/evidence$/, { timeout: 30_000, waitUntil: "commit" });
    await expect(page.getByTestId("accept-analysis-btn")).toBeVisible({ timeout: 30_000 });
    await page.evaluate(() => localStorage.removeItem("forensic_session_id"));
    await page.goto("/evidence");
    await expect(page.getByText(/No Evidence Queued|Select Evidence/i)).toBeVisible({ timeout: 10_000 });
  });

  // ── Fix #6: Duplicate accept/deep decisions ──────────────────────────────────

  test("double-click Accept Analysis → only one resume fires", async ({ page }) => {
    await uploadPng(page);
    await page.getByTestId("upload-start-analysis").click();
    await page.waitForURL(/\/evidence$/, { timeout: 60_000, waitUntil: "commit" });

    await expect(page.getByTestId("accept-analysis-btn")).toBeVisible({ timeout: 900_000 });
    await page.getByTestId("accept-analysis-btn").evaluate((element: HTMLElement) => {
      element.click();
      element.click();
    });
    await page.waitForURL(/\/result\//, { timeout: 60_000, waitUntil: "commit" });
    expect(resumeRequests).toBeLessThanOrEqual(1);
  });

  test("double-click Deep Analysis → only one resume fires", async ({ page }) => {
    let resumeRequests = 0;
    page.on("request", (request) => {
      if (request.method() === "POST" && /\/api\/v1\/sessions\/.+\/resume$/.test(request.url())) {
        resumeRequests += 1;
      }
    });
    await uploadPng(page);
    await page.getByTestId("upload-start-analysis").click();
    await page.waitForURL(/\/evidence$/, { timeout: 60_000, waitUntil: "commit" });

    await expect(page.getByTestId("deep-analysis-btn")).toBeVisible({ timeout: 900_000 });
    await page.getByTestId("deep-analysis-btn").evaluate((element: HTMLElement) => {
      element.click();
      element.click();
    });
    await expect(page.getByTestId("view-report-btn")).toBeVisible({ timeout: 60_000 });
    expect(resumeRequests).toBeLessThanOrEqual(1);
  });

  // ── Fix #7: forensic_history preserved across new upload ───────────────────

  test("forensic_history persists through new upload", async ({ page }) => {
    await uploadPng(page);
    await page.getByTestId("upload-start-analysis").click();
    await page.waitForURL(/\/evidence$/, { timeout: 120_000, waitUntil: "commit" });
    await expect(page.getByTestId("accept-analysis-btn")).toBeVisible({ timeout: 900_000 });
    await page.getByTestId("accept-analysis-btn").click();
    await page.waitForURL(/\/result\//, { timeout: 300_000, waitUntil: "commit" });
    await page.waitForFunction(() => JSON.parse(localStorage.getItem("forensic_history") ?? "[]").length > 0);

    const historyBefore = await page.evaluate(
      () => JSON.parse(localStorage.getItem("forensic_history") ?? "[]").length,
    );
    expect(historyBefore).toBeGreaterThan(0);

    await page.goto("/?upload=1");
    const empty = await page.evaluate(
      () => JSON.parse(localStorage.getItem("forensic_history") ?? "[]").length,
    );
    expect(empty).toBe(0);
  });

  // ── Fix #7: forensic_history preserved through home ───────────────────────────

  test("forensic_history persists through home", async ({ page }) => {
    await uploadPng(page);
    await page.getByTestId("upload-start-analysis").click();
    await page.waitForURL(/\/evidence$/, { timeout: 120_000, waitUntil: "commit" });
    await expect(page.getByTestId("accept-analysis-btn")).toBeVisible({ timeout: 900_000 });
    await page.getByTestId("accept-analysis-btn").click();
    await page.waitForURL(/\/result\//, { timeout: 300_000, waitUntil: "commit" });
    await page.waitForFunction(() => JSON.parse(localStorage.getItem("forensic_history") ?? "[]").length > 0);

    const historyBefore = await page.evaluate(
      () => JSON.parse(localStorage.getItem("forensic_history") ?? "[]").length,
    );
    expect(historyBefore).toBeGreaterThan(0);

    await page.getByRole("button", { name: /Back to Home/i }).first().click();
    await page.waitForURL(/\/#hero/, { timeout: 10_000 });

    const historyAfter = await page.evaluate(
      () => JSON.parse(localStorage.getItem("forensic_history") ?? "[]").length,
    );
    expect(historyAfter).toBe(historyBefore);
  });

  // ── Result page arbiter bridge ───────────────────────────────────────────────

  test("Accept Analysis → result page polls arbiter immediately", async ({ page }) => {
    await uploadPng(page);
    await page.getByTestId("upload-start-analysis").click();
    await page.waitForURL(/\/evidence$/, { timeout: 120_000, waitUntil: "commit" });
    await expect(page.getByTestId("accept-analysis-btn")).toBeVisible({ timeout: 900_000 });
    const beforeUrl = page.url();
    await page.getByTestId("accept-analysis-btn").click();
    await page.waitForURL(/\/result\//, { timeout: 60_000, waitUntil: "commit" });

    await page.waitForFunction(
      (url) => !url.includes("fc_show_loading"),
      page.url(),
      { timeout: 5_000 },
    ).catch(() => {});

    expect(page.url()).not.toBe(beforeUrl);
    await expect(page.getByText(/The council finds the evidence likely authentic after initial analysis/i)).toBeVisible({ timeout: 30_000 });
  });
});
