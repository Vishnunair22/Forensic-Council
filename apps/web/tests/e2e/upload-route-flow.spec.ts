import { test, expect } from "@playwright/test";

test("landing CTA routes selected file into evidence analysis overlay", async ({ page }) => {
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));

  await page.goto("/");

  await expect(page.getByTestId("hero-cta-begin")).toBeVisible();
  await page.getByTestId("hero-cta-begin").click();

  await expect(page.getByRole("dialog", { name: /upload evidence/i })).toBeVisible();

  const png1x1 = Buffer.from(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII=",
    "base64",
  );

  await page.getByLabel(/upload evidence file/i).setInputFiles({
    name: "route-flow-evidence.png",
    mimeType: "image/png",
    buffer: png1x1,
  });

  await expect(page.getByRole("heading", { name: /evidence ready/i })).toBeVisible();
  await expect(page.getByText("route-flow-evidence.png")).toBeVisible();

  await page.getByTestId("upload-start-analysis").click();

  await expect(page.getByText(/opening evidence analysis/i)).toBeVisible();
  await page.waitForURL(/\/evidence$/, { timeout: 30_000 });

  await expect(
    page.getByText(/uploading evidence|connecting to analysis stream|agents dispatching|analysis pipeline/i).first(),
  ).toBeVisible({ timeout: 30_000 });

  await expect(page.getByText(/no evidence queued/i)).toHaveCount(0);
  expect(pageErrors).toEqual([]);
});