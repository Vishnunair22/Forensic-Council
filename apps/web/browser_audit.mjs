// Browser-based initial-analysis audit. Drives the real UI like a user.
// Usage: node browser_audit.mjs "<imagePath>" "<label>"
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";

const imagePath = process.argv[2];
const label = (process.argv[3] || "img").replace(/[^a-zA-Z0-9_-]/g, "_");
const OUT = "d:/Forensic Council/browser-shots";
mkdirSync(OUT, { recursive: true });

const log = (...a) => console.log(`[${label}]`, ...a);

const browser = await chromium.launch({ headless: true });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
const page = await ctx.newPage();
page.on("console", (m) => { if (m.type() === "error") log("PAGE-ERR:", m.text().slice(0, 160)); });

try {
  await page.goto("http://localhost:3000", { waitUntil: "domcontentloaded", timeout: 30000 });
  await page.waitForTimeout(1500);

  // 1. CTA → upload modal
  await page.getByTestId("hero-cta-begin").click({ timeout: 15000 });
  log("clicked CTA");
  const fileInput = page.locator('input[type="file"]');
  await fileInput.waitFor({ state: "attached", timeout: 15000 });
  await fileInput.setInputFiles(imagePath);
  log("file set:", imagePath);
  await page.waitForTimeout(2500); // hash compute + handoff

  // 2. Start analysis (success modal) — try the explicit button, else any "start"
  const startBtn = page.getByTestId("upload-start-analysis");
  try {
    await startBtn.waitFor({ state: "visible", timeout: 15000 });
    await startBtn.click();
    log("clicked start-analysis");
  } catch {
    log("no start-analysis btn (auto-started?)");
  }

  // 3. Evidence page — wait for agent cards to appear
  await page.waitForURL(/\/evidence/, { timeout: 30000 }).catch(() => log("no /evidence url change"));
  await page.locator('[data-testid^="agent-card-"]').first().waitFor({ state: "visible", timeout: 60000 });
  log("evidence page + agent cards visible");

  // 4. Wait for INITIAL analysis to finish → accept-analysis-btn appears (awaiting decision)
  const acceptBtn = page.getByTestId("accept-analysis-btn");
  await acceptBtn.waitFor({ state: "visible", timeout: 180000 });
  log("initial analysis complete (decision gate visible)");
  await page.waitForTimeout(1500);

  // 5. Screenshot the evidence analysis page (full)
  const shot = `${OUT}/${label}__initial.png`;
  await page.screenshot({ path: shot, fullPage: true });
  log("screenshot:", shot);

  // 6. Extract per-agent findings text
  const cards = await page.locator('[data-testid^="agent-card-"]').all();
  const findings = {};
  for (const c of cards) {
    const tid = await c.getAttribute("data-testid");
    const txt = (await c.innerText()).replace(/\s+\n/g, "\n").trim();
    findings[tid] = txt;
  }
  console.log("FINDINGS_JSON_START");
  console.log(JSON.stringify(findings, null, 1));
  console.log("FINDINGS_JSON_END");
} catch (e) {
  log("ERROR:", e.message);
  await page.screenshot({ path: `${OUT}/${label}__error.png`, fullPage: true }).catch(() => {});
  process.exitCode = 1;
} finally {
  await browser.close();
}
