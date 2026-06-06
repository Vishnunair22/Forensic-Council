// Browser report-generation audit: upload -> initial -> Accept -> report page.
// Usage: node browser_report.mjs "<imagePath>" "<label>"
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";

const imagePath = process.argv[2];
const label = (process.argv[3] || "img").replace(/[^a-zA-Z0-9_-]/g, "_");
const OUT = "d:/Forensic Council/browser-shots";
mkdirSync(OUT, { recursive: true });
const log = (...a) => console.log(`[${label}]`, ...a);

const browser = await chromium.launch({ headless: true });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 1100 } });
const page = await ctx.newPage();

try {
  await page.goto("http://localhost:3000", { waitUntil: "domcontentloaded", timeout: 30000 });
  await page.waitForTimeout(1500);
  await page.getByTestId("hero-cta-begin").click({ timeout: 15000 });
  const fileInput = page.locator('input[type="file"]');
  await fileInput.waitFor({ state: "attached", timeout: 15000 });
  await fileInput.setInputFiles(imagePath);
  await page.waitForTimeout(2500);
  try {
    await page.getByTestId("upload-start-analysis").click({ timeout: 15000 });
  } catch { /* auto-started */ }
  await page.locator('[data-testid^="agent-card-"]').first().waitFor({ state: "visible", timeout: 60000 });
  const acceptBtn = page.getByTestId("accept-analysis-btn");
  await acceptBtn.waitFor({ state: "visible", timeout: 180000 });
  log("initial done — accepting baseline");
  await acceptBtn.click();

  // Wait for report: either view-report-btn appears, or page navigates to /result
  const viewBtn = page.getByTestId("view-report-btn");
  try {
    await viewBtn.waitFor({ state: "visible", timeout: 120000 });
    await viewBtn.click();
    log("clicked view-report");
  } catch {
    log("no view-report-btn; checking for /result nav");
  }
  await page.waitForURL(/\/result/, { timeout: 60000 }).catch(() => log("no /result url"));
  await page.waitForTimeout(4000); // let report render

  const shot = `${OUT}/${label}__report.png`;
  await page.screenshot({ path: shot, fullPage: true });
  log("report screenshot:", shot);

  // Extract the whole report text, section by section (main content)
  const main = page.locator("main").first();
  const text = await (await main.count() ? main : page.locator("body")).innerText();
  console.log("REPORT_TEXT_START");
  console.log(text);
  console.log("REPORT_TEXT_END");
} catch (e) {
  log("ERROR:", e.message);
  await page.screenshot({ path: `${OUT}/${label}__report_error.png`, fullPage: true }).catch(() => {});
  process.exitCode = 1;
} finally {
  await browser.close();
}
