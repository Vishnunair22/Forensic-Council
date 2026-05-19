import { test, expect } from "@playwright/test";
import { deflateSync } from "node:zlib";

function crc32(buffer: Buffer): number {
  let crc = 0xffffffff;
  for (const byte of buffer) {
    crc ^= byte;
    for (let i = 0; i < 8; i++) {
      crc = (crc >>> 1) ^ (0xedb88320 & -(crc & 1));
    }
  }
  return (crc ^ 0xffffffff) >>> 0;
}

function pngChunk(type: string, data: Buffer): Buffer {
  const typeBuffer = Buffer.from(type, "ascii");
  const length = Buffer.alloc(4);
  length.writeUInt32BE(data.length, 0);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(Buffer.concat([typeBuffer, data])), 0);
  return Buffer.concat([length, typeBuffer, data, crc]);
}

function makeUniquePng(seed: number): Buffer {
  const width = 2;
  const height = 2;
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(width, 0);
  ihdr.writeUInt32BE(height, 4);
  ihdr[8] = 8; // bit depth
  ihdr[9] = 6; // RGBA

  const r = seed & 0xff;
  const g = (seed >> 8) & 0xff;
  const b = (seed >> 16) & 0xff;
  const rows = Buffer.from([
    0, r, g, b, 255, 255 - r, g, b, 255,
    0, r, 255 - g, b, 255, r, g, 255 - b, 255,
  ]);

  return Buffer.concat([
    Buffer.from("89504e470d0a1a0a", "hex"),
    pngChunk("IHDR", ihdr),
    pngChunk("IDAT", deflateSync(rows)),
    pngChunk("IEND", Buffer.alloc(0)),
  ]);
}

async function uploadThroughLiveInitialAnalysis(page: import("@playwright/test").Page, label: string) {
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));

  await page.goto("/");
  // NEW: Wait for backend readiness
  await page.waitForResponse(
    (response) => (response.url().includes("/api/v1/health") || response.url().includes("/health")) && response.status() === 200,
    { timeout: 30_000 }
  );

  await page.getByTestId("hero-cta-begin").click();

  const startedAt = Date.now();
  const uniquePng = makeUniquePng(startedAt);

  await page.getByLabel(/upload evidence file/i).setInputFiles({
    name: `runtime-${label}-evidence-${startedAt}.png`,
    mimeType: "image/png",
    buffer: uniquePng,
  });

  await expect(page.getByRole("heading", { name: /Evidence Ready/i })).toBeVisible({ timeout: 15_000 });
  await page.getByTestId("upload-start-analysis").click();

  // NEW: Wait for WebSocket handshake completion
  await page.waitForFunction(() => {
    return window.localStorage.getItem("forensic_ws_connected") === "true" ||
           window.location.pathname.includes("/evidence");
  }, { timeout: 60_000 });

  await page.waitForURL(/\/evidence$/, { timeout: 120_000, waitUntil: "commit" });
  await expect(page.getByText(/Uploading evidence|Connecting to analysis|Agents dispatching|Analysis Pipeline/i).first()).toBeVisible({ timeout: 90_000 });

  await expect(page.getByRole("button", { name: /Active Specialists \(3\)/i })).toBeVisible();
  await expect(page.getByRole("button", { name: /Skipped \(2\)/i })).toBeVisible();

  for (const agentId of ["Agent1", "Agent3", "Agent5"]) {
    await expect(page.getByTestId(`agent-card-${agentId}`)).toBeVisible({ timeout: 120_000 });
  }

  for (const agentId of ["Agent1", "Agent3", "Agent5"]) {
    await expect(page.getByTestId(`agent-card-${agentId}`)).toContainText(
      /Scanning|Verified|Confidence|Final Verdict|SIG_/i,
      { timeout: 900_000 },
    );
  }

  await expect(page.getByTestId("accept-analysis-btn")).toBeVisible({ timeout: 1_500_000 });
  await expect(page.getByTestId("deep-analysis-btn")).toBeVisible();
  await expect(page.getByTestId("agent-card-Agent1")).toContainText(/Final Verdict|Confidence|SIG_/i);
  await expect(page.getByTestId("agent-card-Agent3")).toContainText(/Final Verdict|Confidence|SIG_/i);
  await expect(page.getByTestId("agent-card-Agent5")).toContainText(/Final Verdict|Confidence|SIG_/i);

  return pageErrors;
}

test("runtime: landing upload through live initial analysis and accept result", async ({ page }) => {
  test.setTimeout(1_800_000);
  test.slow();  // NEW: Mark as slow test for Playwright reporting
  const pageErrors = await uploadThroughLiveInitialAnalysis(page, "accept");

  await page.getByTestId("accept-analysis-btn").click();
  await expect(page).toHaveURL(/\/result/, { timeout: 120_000 });
  await expect(page.getByRole("tab", { name: /Analysis/i })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(/initial analysis|council/i).first()).toBeVisible({ timeout: 30_000 });

  expect(pageErrors).toEqual([]);
});

test("runtime: landing upload through live deep analysis and final result", async ({ page }) => {
  test.setTimeout(1_800_000);
  test.slow();  // NEW: Mark as slow test for Playwright reporting
  const pageErrors = await uploadThroughLiveInitialAnalysis(page, "deep");

  await page.getByTestId("deep-analysis-btn").click();
  await expect(page.getByTestId("view-report-btn")).toBeVisible({ timeout: 600_000 });
  await page.getByTestId("view-report-btn").click();
  await expect(page).toHaveURL(/\/result/, { timeout: 120_000 });
  await expect(page.getByRole("tab", { name: /Analysis/i })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(/deep analysis|final report|council/i).first()).toBeVisible({ timeout: 30_000 });

  expect(pageErrors).toEqual([]);
});
