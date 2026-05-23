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

function makeValidPng(): Buffer {
  const width = 2;
  const height = 2;
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(width, 0);
  ihdr.writeUInt32BE(height, 4);
  ihdr[8] = 8;
  ihdr[9] = 6;
  const rows = Buffer.from([
    0, 40, 80, 120, 255, 160, 80, 120, 255,
    0, 40, 180, 120, 255, 40, 80, 220, 255,
  ]);
  return Buffer.concat([
    Buffer.from("89504e470d0a1a0a", "hex"),
    pngChunk("IHDR", ihdr),
    pngChunk("IDAT", deflateSync(rows)),
    pngChunk("IEND", Buffer.alloc(0)),
  ]);
}

test("landing CTA routes selected file into evidence analysis overlay", async ({ page }) => {
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));

  await page.goto("/");

  await expect(page.getByTestId("hero-cta-begin")).toBeVisible();
  await page.getByTestId("hero-cta-begin").click();

  await expect(page.getByRole("dialog", { name: /upload evidence/i })).toBeVisible();

  await page.locator('#evidence-file-input').setInputFiles({
    name: "route-flow-evidence.png",
    mimeType: "image/png",
    buffer: makeValidPng(),
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
