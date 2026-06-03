// Render-only check against an existing completed session.
// Usage: node render_only.mjs <sessionId>
import { chromium } from "@playwright/test";
const API = "http://localhost:8000";
const WEB = "http://localhost:3000";
const PASSWORD = process.env.DEMO_PASSWORD;
const sid = process.argv[2];
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext();
  const r = await ctx.request.post(`${API}/api/v1/auth/login`, {
    form: { username: "investigator", password: PASSWORD },
  });
  if (!r.ok()) throw new Error("login failed " + r.status());
  const page = await ctx.newPage();
  const errs = [];
  page.on("pageerror", (e) => errs.push(e.message));
  await page.goto(`${WEB}/result/${sid}`, { waitUntil: "domcontentloaded" });
  await sleep(8000);
  const analysisTab = page.getByRole("button", { name: /analysis/i }).first();
  if (await analysisTab.count()) await analysisTab.click({ timeout: 3000 }).catch(() => {});
  await sleep(1000);
  for (let pass = 0; pass < 3; pass++) {
    const toggles = page.locator('button[aria-expanded="false"]');
    const n = await toggles.count();
    if (!n) break;
    for (let i = 0; i < n; i++) {
      await toggles.nth(i).click({ timeout: 2000 }).catch(() => {});
      await sleep(200);
    }
  }
  await sleep(1500);
  const body = (await page.locator("main, body").first().innerText().catch(() => "")).replace(/\n{2,}/g, "\n");
  console.log("PAGE_ERRORS", JSON.stringify(errs));
  console.log(body);
  await browser.close();
})().catch((e) => { console.error("ERR", e?.stack || e); process.exit(1); });
