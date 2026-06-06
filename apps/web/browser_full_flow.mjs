// Full single-session flow: upload -> evidence page (read agent cards)
// -> accept baseline -> result page (read all fields). One fresh browser
// context per run (no persisted storage = clean cache).
// Usage: node browser_full_flow.mjs "<imagePath>" "<label>"
import { chromium } from "playwright";
import { mkdirSync, writeFileSync } from "node:fs";

const imagePath = process.argv[2];
const label = (process.argv[3] || "img").replace(/[^a-zA-Z0-9_-]/g, "_");
const OUT = "d:/Forensic Council/browser-shots";
mkdirSync(OUT, { recursive: true });
const log = (...a) => console.log(`[${label}]`, ...a);

const browser = await chromium.launch({ headless: true });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 1100 } });
const page = await ctx.newPage();
const pageErrors = [];
page.on("console", (m) => { if (m.type() === "error") { const t = m.text().slice(0, 200); pageErrors.push(t); log("PAGE-ERR:", t); } });
page.on("pageerror", (e) => { pageErrors.push(e.message.slice(0, 200)); log("PAGEERROR:", e.message.slice(0, 160)); });

const result = { label, evidence: {}, report: "", pageErrors, stage: "start" };

try {
  // Wait for the page to be interactive (networkidle) before clicking, so the
  // click can't beat React hydration — clicking the hero CTA before its onClick
  // is attached is a no-op (the upload modal never opens). Retry the click a few
  // times in case the first lands mid-hydration.
  await page.goto("http://localhost:3000", { waitUntil: "domcontentloaded", timeout: 30000 });
  await page.getByTestId("hero-cta-begin").waitFor({ state: "visible", timeout: 15000 });
  await page.waitForTimeout(800); // small settle for hydration before clicking
  const fileInput = page.locator('input[type="file"]');
  let modalOpen = false;
  for (let attempt = 0; attempt < 4 && !modalOpen; attempt++) {
    await page.getByTestId("hero-cta-begin").click({ timeout: 15000 });
    try {
      await fileInput.waitFor({ state: "attached", timeout: 6000 });
      modalOpen = true;
    } catch {
      log(`CTA click attempt ${attempt + 1} did not open modal (pre-hydration?), retrying`);
      await page.waitForTimeout(1500);
    }
  }
  if (!modalOpen) throw new Error("upload modal never opened after 4 CTA clicks");
  await fileInput.setInputFiles(imagePath);
  log("file set:", imagePath);
  await page.waitForTimeout(2500);

  try {
    await page.getByTestId("upload-start-analysis").click({ timeout: 15000 });
    log("clicked start-analysis");
  } catch { log("no start-analysis btn (auto-started?)"); }

  await page.waitForURL(/\/evidence/, { timeout: 30000 }).catch(() => log("no /evidence url change"));
  await page.locator('[data-testid^="agent-card-"]').first().waitFor({ state: "visible", timeout: 60000 });
  result.stage = "evidence";

  const acceptBtn = page.getByTestId("accept-analysis-btn");
  await acceptBtn.waitFor({ state: "visible", timeout: 180000 });
  log("initial analysis complete (decision gate visible)");
  // Allow the arbiter pre-warm's grounded per-agent reconciliation (AGENT_GROUNDED)
  // to land so the captured card reflects the same verdict the report will show.
  await page.waitForTimeout(8000);

  await page.screenshot({ path: `${OUT}/${label}__initial.png`, fullPage: true });
  const cards = await page.locator('[data-testid^="agent-card-"]').all();
  for (const c of cards) {
    const tid = await c.getAttribute("data-testid");
    result.evidence[tid] = (await c.innerText()).replace(/\s+\n/g, "\n").trim();
  }
  result.overallEvidence = await page.locator("main").first().innerText().catch(() => "");

  // Accept baseline -> result page
  await acceptBtn.click();
  log("accepted baseline");
  const viewBtn = page.getByTestId("view-report-btn");
  try {
    await viewBtn.waitFor({ state: "visible", timeout: 120000 });
    await viewBtn.click();
    log("clicked view-report");
  } catch { log("no view-report-btn; checking for /result nav"); }
  await page.waitForURL(/\/result/, { timeout: 90000 }).catch(() => log("no /result url"));
  await page.waitForTimeout(4000);
  result.stage = "report";

  await page.screenshot({ path: `${OUT}/${label}__report.png`, fullPage: true });
  const main = page.locator("main").first();
  result.report = await (await main.count() ? main : page.locator("body")).innerText();
  result.stage = "done";
} catch (e) {
  result.error = e.message;
  log("ERROR:", e.message);
  await page.screenshot({ path: `${OUT}/${label}__error.png`, fullPage: true }).catch(() => {});
  process.exitCode = 1;
} finally {
  writeFileSync(`${OUT}/${label}__data.json`, JSON.stringify(result, null, 1));
  await browser.close();
}
