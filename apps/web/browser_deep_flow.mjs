// Deep-analysis full flow: upload -> initial gate (capture INITIAL cards for
// cross-verification) -> Authorize Deep Analysis -> deep gate (capture DEEP
// cards) -> View Report -> result page. One session captures initial + deep.
// Usage: node browser_deep_flow.mjs "<imagePath>" "<label>"
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
page.on("console", (m) => { if (m.type() === "error") pageErrors.push(m.text().slice(0, 200)); });
page.on("pageerror", (e) => pageErrors.push(e.message.slice(0, 200)));

const result = { label, phase: "deep", initialEvidence: {}, deepEvidence: {}, report: "", pageErrors, stage: "start" };
const readCards = async () => {
  const out = {};
  for (const c of await page.locator('[data-testid^="agent-card-"]').all()) {
    out[await c.getAttribute("data-testid")] = (await c.innerText()).replace(/\s+\n/g, "\n").trim();
  }
  return out;
};

try {
  await page.goto("http://localhost:3000", { waitUntil: "domcontentloaded", timeout: 30000 });
  await page.getByTestId("hero-cta-begin").waitFor({ state: "visible", timeout: 15000 });
  await page.waitForTimeout(800);
  const fileInput = page.locator('input[type="file"]');
  let modalOpen = false;
  for (let i = 0; i < 4 && !modalOpen; i++) {
    await page.getByTestId("hero-cta-begin").click({ timeout: 15000 });
    try { await fileInput.waitFor({ state: "attached", timeout: 6000 }); modalOpen = true; }
    catch { await page.waitForTimeout(1500); }
  }
  if (!modalOpen) throw new Error("upload modal never opened");
  await fileInput.setInputFiles(imagePath);
  log("file set");
  await page.waitForTimeout(2500);
  try { await page.getByTestId("upload-start-analysis").click({ timeout: 15000 }); } catch {}

  await page.locator('[data-testid^="agent-card-"]').first().waitFor({ state: "visible", timeout: 60000 });
  // INITIAL gate
  const deepBtn = page.getByTestId("deep-analysis-btn");
  await deepBtn.waitFor({ state: "visible", timeout: 180000 });
  result.stage = "initial_gate";
  await page.waitForTimeout(8000); // let grounded reconciliation land
  await page.screenshot({ path: `${OUT}/${label}__initial.png`, fullPage: true });
  result.initialEvidence = await readCards();
  log("INITIAL captured; authorizing deep analysis");

  await deepBtn.click();
  // DEEP gate — deep analysis re-runs agents; wait for the deep view-report button
  const viewBtn = page.getByTestId("view-report-btn");
  await viewBtn.waitFor({ state: "visible", timeout: 360000 });
  result.stage = "deep_gate";
  await page.waitForTimeout(8000);
  result.deepEvidenceEarly = await readCards();   // ~8s after gate
  await page.waitForTimeout(20000);               // allow deep pre-warm grounded feed to land
  await page.screenshot({ path: `${OUT}/${label}__deep.png`, fullPage: true });
  result.deepEvidence = await readCards();        // ~28s after gate
  log("DEEP captured; viewing report");

  await viewBtn.click();
  await page.waitForURL(/\/result/, { timeout: 90000 }).catch(() => log("no /result url"));
  await page.waitForTimeout(4000);
  result.stage = "report";
  await page.screenshot({ path: `${OUT}/${label}__report.png`, fullPage: true });
  const main = page.locator("main").first();
  result.report = await (await main.count() ? main : page.locator("body")).innerText();
  result.stage = "done";
  log("report captured");
} catch (e) {
  result.error = e.message;
  log("ERROR:", e.message);
  await page.screenshot({ path: `${OUT}/${label}__error.png`, fullPage: true }).catch(() => {});
  process.exitCode = 1;
} finally {
  writeFileSync(`${OUT}/${label}__data.json`, JSON.stringify(result, null, 1));
  await browser.close();
}
