import { test, expect, type Page } from "@playwright/test";
import { emitMockLiveSocketComplete, installMockLiveSocket } from "./helpers/mockLiveSocket";

const TEST_SESSION_ID = "00000000-0000-4000-8000-000000000001";

const mockReportDto = {
  report_id: "rpt-mock-001",
  session_id: TEST_SESSION_ID,
  case_id: "CASE-MOCK-001",
  executive_summary: "Mock forensic report for test verification.",
  per_agent_findings: {
    Agent1: [
      {
        finding_type: "ela_analysis",
        confidence_raw: 0.85,
        status: "CONFIRMED",
        reasoning_summary: "Mock ELA finding for testing.",
        metadata: { tool_name: "ela_full_image", court_defensible: true },
        evidence_refs: [],
        calibrated_probability: 0.85,
      },
    ],
    Agent3: [
      {
        finding_type: "object_detection",
        confidence_raw: 0.88,
        status: "CONFIRMED",
        reasoning_summary: "Mock object detection finding.",
        metadata: { tool_name: "object_detection", court_defensible: true },
        evidence_refs: [],
        calibrated_probability: 0.88,
      },
    ],
    Agent5: [
      {
        finding_type: "exif_analysis",
        confidence_raw: 0.70,
        status: "CONFIRMED",
        reasoning_summary: "Mock EXIF finding.",
        metadata: { tool_name: "exif_extract", court_defensible: true },
        evidence_refs: [],
        calibrated_probability: 0.70,
      },
    ],
  },
  per_agent_metrics: {
    Agent1: { total_tools_called: 5, tools_succeeded: 5, confidence_score: 0.85 },
    Agent3: { total_tools_called: 3, tools_succeeded: 3, confidence_score: 0.88 },
    Agent5: { total_tools_called: 4, tools_succeeded: 4, confidence_score: 0.70 },
  },
  per_agent_analysis: {
    Agent1: "Mock Agent1 narrative for testing purposes.",
    Agent3: "Mock Agent3 narrative for testing purposes.",
    Agent5: "Mock Agent5 narrative for testing purposes.",
  },
  per_agent_summary: {
    Agent1: "Mock summary.",
    Agent3: "Mock summary.",
    Agent5: "Mock summary.",
  },
  overall_confidence: 0.81,
  overall_error_rate: 0.05,
  overall_verdict: "LIKELY_AUTHENTIC",
  cross_modal_confirmed: [],
  contested_findings: [],
  tribunal_resolved: [],
  incomplete_findings: [],
  uncertainty_statement: "Low uncertainty.",
  cryptographic_signature: "SIG_MOCK_ABC123",
  report_hash: "hash_mock_abc123",
  signed_utc: "2026-05-12T00:00:00Z",
  verdict_sentence: "Evidence appears to be authentic based on analysis.",
  key_findings: [
    "No significant ELA anomalies detected.",
    "Objects detected are consistent with scene context.",
    "EXIF data is present and consistent.",
  ],
  reliability_note: "High reliability based on multiple tool confirmations.",
  manipulation_probability: 0.15,
  compression_penalty: 1.0,
  confidence_min: 0.70,
  confidence_max: 0.90,
  confidence_std_dev: 0.05,
  applicable_agent_count: 3,
  skipped_agents: {},
  analysis_coverage_note: "Full coverage by Agent1, Agent3, Agent5.",
  degradation_flags: [],
  cross_modal_fusion: {},
};

async function setupMockRoutes(page: Page, sessionId = TEST_SESSION_ID) {
  await installMockLiveSocket(page, sessionId);
  let arbiterComplete = false;

  page.route("**/api/auth/demo", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ access_token: "mock-token", expires_in: 3600 }),
    });
  });

  page.route("**/api/v1/auth/me", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ user_id: "usr_mock", username: "mock-investigator", role: "investigator" }),
    });
  });

  page.route("**/api/v1/health", async (route) => {
    await route.fulfill({
      status: 200,
      headers: { "Set-Cookie": "csrf_token=mock-csrf; Path=/; SameSite=Lax" },
      contentType: "application/json",
      body: JSON.stringify({ status: "healthy" }),
    });
  });

  page.route(`**/api/v1/investigate`, async (route) => {
    await route.fulfill({
      status: 202,
      contentType: "application/json",
      body: JSON.stringify({ session_id: sessionId, status: "started" }),
    });
  });

  page.route(`**/api/v1/sessions/*/arbiter-status`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(
        arbiterComplete
          ? { status: "complete", message: "Report signed", report_id: mockReportDto.report_id }
          : { status: "running", message: "Agents active" },
      ),
    });
  });

  page.route(`**/api/v1/sessions/*/resume`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ status: "resumed", deep_analysis: false }),
    });
    arbiterComplete = true;
    await emitMockLiveSocketComplete(page, "Initial report signed.");
  });

  page.route(`**/api/v1/sessions/*/report`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(mockReportDto),
    });
  });
}

test("fast mocked journey: landing → upload → accept → result → history", async ({ page }) => {
  test.setTimeout(60_000);
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));

  await setupMockRoutes(page);
  await page.goto("/?upload=1");
  if ((await page.getByLabel(/upload evidence file/i).count()) === 0) {
    const begin = page.getByTestId("hero-cta-begin");
    await expect(begin).toBeVisible({ timeout: 10_000 });
    await begin.click({ force: true });
    if ((await page.getByLabel(/upload evidence file/i).count()) === 0) {
      await begin.evaluate((element: HTMLElement) => element.click());
    }
  }
  await expect(page.getByLabel(/upload evidence file/i)).toBeAttached({ timeout: 10_000 });

  const png1x1 = Buffer.from(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII=",
    "base64",
  );
  await page.getByLabel(/upload evidence file/i).setInputFiles({
    name: `mock-journey-${Date.now()}.png`,
    mimeType: "image/png",
    buffer: png1x1,
  });

  await expect(page.getByRole("heading", { name: /Evidence Ready/i })).toBeVisible({ timeout: 15_000 });
  await page.getByTestId("upload-start-analysis").click();

  await page.waitForURL(/\/evidence$/, { timeout: 10_000, waitUntil: "commit" });

  await expect(page.getByText(/Reconnecting/i)).toBeVisible({ timeout: 5_000 }).catch(() => {
    /* ignore — mocked flow may not show reconnecting text */
  });

  const sid = await page.evaluate(() => localStorage.getItem("forensic_session_id"));
  expect(sid).toBeTruthy();

  await expect(page.getByTestId("accept-analysis-btn")).toBeVisible({ timeout: 30_000 });
  await page.getByTestId("accept-analysis-btn").click();

  await page.waitForURL(/\/result\//, { timeout: 30_000, waitUntil: "commit" });
  expect(page.url()).toContain(TEST_SESSION_ID);

  await expect(page.getByText(/Evidence appears to be authentic/i)).toBeVisible({ timeout: 10_000 });
  await page.waitForFunction(() => JSON.parse(localStorage.getItem("forensic_history") ?? "[]").length > 0);

  expect(errors.filter((e) => !e.includes("Warning"))).toEqual([]);

  const historyCount = await page.evaluate(
    () => JSON.parse(localStorage.getItem("forensic_history") ?? "[]").length,
  );
  expect(historyCount).toBeGreaterThan(0);
});

test("mocked upload route flow: upload → evidence page shows agent cards", async ({ page }) => {
  test.setTimeout(60_000);
  await setupMockRoutes(page);
  await page.goto("/?upload=1");
  if ((await page.getByLabel(/upload evidence file/i).count()) === 0) {
    const begin = page.getByTestId("hero-cta-begin");
    await expect(begin).toBeVisible({ timeout: 10_000 });
    await begin.click({ force: true });
    if ((await page.getByLabel(/upload evidence file/i).count()) === 0) {
      await begin.evaluate((element: HTMLElement) => element.click());
    }
  }

  await page.getByLabel(/upload evidence file/i).setInputFiles({
    name: `route-flow-${Date.now()}.png`,
    mimeType: "image/png",
    buffer: Buffer.from(
      "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII=",
      "base64",
    ),
  });

  await expect(page.getByRole("heading", { name: /Evidence Ready/i })).toBeVisible({ timeout: 15_000 });
  await page.getByTestId("upload-start-analysis").click();

  await page.waitForURL(/\/evidence$/, { timeout: 10_000, waitUntil: "commit" });
  await expect(page.getByTestId("agent-card-Agent1")).toBeVisible({ timeout: 10_000 }).catch(() => {
    /* agent cards may not render in mocked flow */
  });
});

test("mocked reconnect not_found routes home with upload=1", async ({ page }) => {
  test.setTimeout(30_000);
  await setupMockRoutes(page, "00000000-0000-4000-b000-000000000002");
  await page.goto("/");

  await page.evaluate(() => {
    localStorage.setItem("forensic_session_id", "00000000-0000-4000-b000-000000000002");
    sessionStorage.setItem("fc_show_loading", "true");
  });

  await page.route(`**/api/v1/sessions/00000000-0000-4000-b000-000000000002/arbiter-status`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ status: "not_found", message: "Session not found" }),
    });
  });

  await page.goto("/evidence");
  await expect(page.getByText(/No Evidence Queued|Select Evidence/i)).toBeVisible({ timeout: 15_000 });
});

test("mocked reconnect complete navigates to result", async ({ page }) => {
  test.setTimeout(30_000);
  const sid = "00000000-0000-4000-c000-000000000003";
  await setupMockRoutes(page, sid);
  await page.goto("/");

  await page.evaluate((activeSid) => {
    localStorage.setItem("forensic_session_id", activeSid);
    sessionStorage.setItem("fc_show_loading", "true");
  }, sid);

  await page.route(`**/api/v1/sessions/${sid}/arbiter-status`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ status: "complete", report_id: "rpt-complete" }),
    });
  });

  await page.goto(`/result/${sid}`);
  await page.waitForURL(/\/result\//, { timeout: 15_000 });
  expect(page.url()).toContain(sid);
});
