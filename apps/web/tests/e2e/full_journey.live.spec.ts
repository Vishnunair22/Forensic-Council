import { test, expect } from "@playwright/test";

test("runtime: landing upload through live initial analysis", async ({ page }) => {
  test.setTimeout(1_800_000);
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));

  await page.goto("/");
  await page.getByTestId("hero-cta-begin").click();

  const png1x1 = Buffer.from(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII=",
    "base64",
  );
  const uniquePng = Buffer.concat([
    png1x1,
    Buffer.from(`\nforensic-council-e2e-${Date.now()}`),
  ]);

  await page.getByLabel(/upload evidence file/i).setInputFiles({
    name: `runtime-evidence-${Date.now()}.png`,
    mimeType: "image/png",
    buffer: uniquePng,
  });

  await expect(page.getByRole("heading", { name: /Evidence Ready/i })).toBeVisible({ timeout: 15_000 });
  await page.getByTestId("upload-start-analysis").click();

  await expect(page.getByRole("heading", { name: /Authenticating|Connecting/i })).toBeVisible({ timeout: 60_000 });
  await page.waitForURL(/\/evidence$/, { timeout: 120_000, waitUntil: "commit" });
  await expect(page.getByText(/Uplinking/i)).toBeVisible({ timeout: 90_000 });
  await expect(page.getByText(/Uploading Evidence|Establishing Stream|Dispatching Agents/i).first()).toBeVisible();

  for (const agentId of ["Agent1", "Agent2", "Agent3", "Agent4", "Agent5"]) {
    await expect(page.getByTestId(`agent-card-${agentId}`)).toBeVisible({ timeout: 120_000 });
  }

  await expect(page.getByTestId("agent-card-Agent2")).toContainText(/skipped|does not support|Bypassed/i);
  await expect(page.getByTestId("agent-card-Agent4")).toContainText(/skipped|does not support|Bypassed/i);

  await expect(page.getByTestId("agent-card-Agent2")).toBeHidden({ timeout: 20_000 });
  await expect(page.getByTestId("agent-card-Agent4")).toBeHidden({ timeout: 20_000 });

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
  expect(pageErrors).toEqual([]);
});
