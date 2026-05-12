import { test, expect, type Page } from "@playwright/test";

test.describe("Full Journey — Phase 7 Edge Cases", () => {
  test.beforeEach(async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await page.goto("/");
    await page.getByTestId("hero-cta-begin").click();
    await expect(page.getByLabel(/upload evidence file/i)).toBeVisible({ timeout: 10_000 });
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
    await page.waitForURL(/[\/\?]$/, { timeout: 10_000 });
    expect(page.url()).toMatch(/\?upload=1$/);
    await expect(page.getByLabel(/upload evidence file/i)).toBeVisible({ timeout: 5_000 });
    await page.waitForURL(/upload=1/, { timeout: 2_000 }).catch(() => {});
    expect(page.url()).not.toMatch(/upload=1/);
  });

  // ── Fix #3: Duplicate upload reconnects to existing session ─────────────────

  test("duplicate upload 409 → reconnects to existing session", async ({ page }) => {
    await uploadPng(page);
    await page.getByTestId("upload-start-analysis").click();
    await page.waitForURL(/\/evidence$/, { timeout: 30_000, waitUntil: "commit" });

    const sessionId = await page.evaluate(() => localStorage.getItem("forensic_session_id"));
    expect(sessionId).toBeTruthy();

    const sid1 = await page.evaluate(() => localStorage.getItem("forensic_session_id"));
    await page.goto("/");
    await page.getByTestId("hero-cta-begin").click();
    await uploadPng(page, `dup-${Date.now()}.png`);
    await page.getByTestId("upload-start-analysis").click();
    await page.waitForURL(/\/evidence$/, { timeout: 30_000, waitUntil: "commit" });

    const sid2 = await page.evaluate(() => localStorage.getItem("forensic_session_id"));
    expect(sid2).toBe(sid1);
  });

  // ── Fix #4: Reconnect routes by arbiter status ───────────────────────────────

  test("reconnect complete → navigates to result", async ({ page }) => {
    await uploadPng(page);
    await page.getByTestId("upload-start-analysis").click();
    await page.waitForURL(/\/evidence$/, { timeout: 30_000, waitUntil: "commit" });
    const sid = await page.evaluate(() => localStorage.getItem("forensic_session_id") ?? "");
    expect(sid).toBeTruthy();

    await page.goto("/evidence");
    await page.waitForURL(/\/result\//, { timeout: 30_000, waitUntil: "commit" });
    expect(page.url()).toContain(sid);
  });

  test("reconnect not_found → routes to home with upload=1", async ({ page }) => {
    await uploadPng(page);
    await page.getByTestId("upload-start-analysis").click();
    await page.waitForURL(/\/evidence$/, { timeout: 30_000, waitUntil: "commit" });
    await page.evaluate(() => localStorage.removeItem("forensic_session_id"));
    await page.goto("/evidence");
    await page.waitForURL(/upload=1/, { timeout: 10_000 });
    await expect(page.getByLabel(/upload evidence file/i)).toBeVisible({ timeout: 5_000 });
  });

  // ── Fix #6: Duplicate accept/deep decisions ──────────────────────────────────

  test("double-click Accept Analysis → only one resume fires", async ({ page }) => {
    await uploadPng(page);
    await page.getByTestId("upload-start-analysis").click();
    await page.waitForURL(/\/evidence$/, { timeout: 60_000, waitUntil: "commit" });

    await expect(page.getByTestId("accept-analysis-btn")).toBeVisible({ timeout: 900_000 });
    await page.getByTestId("accept-analysis-btn").click();
    const url1 = page.url();
    await page.getByTestId("accept-analysis-btn").click({ force: true });
    const url2 = page.url();
    expect(url1).toBe(url2);
  });

  test("double-click Deep Analysis → only one resume fires", async ({ page }) => {
    await uploadPng(page);
    await page.getByTestId("upload-start-analysis").click();
    await page.waitForURL(/\/evidence$/, { timeout: 60_000, waitUntil: "commit" });

    await expect(page.getByTestId("deep-analysis-btn")).toBeVisible({ timeout: 900_000 });
    await page.getByTestId("deep-analysis-btn").click();
    const url1 = page.url();
    await page.getByTestId("deep-analysis-btn").click({ force: true });
    const url2 = page.url();
    expect(url1).toBe(url2);
  });

  // ── Fix #7: forensic_history preserved across new upload ───────────────────

  test("forensic_history persists through new upload", async ({ page }) => {
    await uploadPng(page);
    await page.getByTestId("upload-start-analysis").click();
    await page.waitForURL(/\/evidence$/, { timeout: 120_000, waitUntil: "commit" });
    await expect(page.getByTestId("accept-analysis-btn")).toBeVisible({ timeout: 900_000 });
    await page.getByTestId("accept-analysis-btn").click();
    await page.waitForURL(/\/result\//, { timeout: 300_000, waitUntil: "commit" });

    const historyBefore = await page.evaluate(
      () => JSON.parse(localStorage.getItem("forensic_history") ?? "[]").length,
    );
    expect(historyBefore).toBeGreaterThan(0);

    await page.goto("/");
    await page.getByTestId("hero-cta-begin").click();
    const empty = await page.evaluate(
      () => JSON.parse(localStorage.getItem("forensic_history") ?? "[]").length,
    );
    expect(empty).toBe(historyBefore);
  });

  // ── Fix #7: forensic_history preserved through home ───────────────────────────

  test("forensic_history persists through home", async ({ page }) => {
    await uploadPng(page);
    await page.getByTestId("upload-start-analysis").click();
    await page.waitForURL(/\/evidence$/, { timeout: 120_000, waitUntil: "commit" });
    await expect(page.getByTestId("accept-analysis-btn")).toBeVisible({ timeout: 900_000 });
    await page.getByTestId("accept-analysis-btn").click();
    await page.waitForURL(/\/result\//, { timeout: 300_000, waitUntil: "commit" });

    const historyBefore = await page.evaluate(
      () => JSON.parse(localStorage.getItem("forensic_history") ?? "[]").length,
    );
    expect(historyBefore).toBeGreaterThan(0);

    await page.getByRole("button", { name: /hub/i }).click();
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
    await expect(page.getByTestId(/agent-card-agent1/i).first()).toBeVisible({ timeout: 30_000 });
  });
});
