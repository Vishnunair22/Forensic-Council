// Live E2E driver: real browser context → real backend pipeline → real report.
// Usage: node e2e_drive.mjs <imagePath> <initial|deep> [--render]
import { chromium } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

const API = "http://localhost:8000";
const WEB = "http://localhost:3000";
const PASSWORD = process.env.DEMO_PASSWORD;
const imagePath = process.argv[2];
const mode = process.argv[3] || "initial";
const doRender = process.argv.includes("--render");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function mimeFor(name) {
  const e = path.extname(name).toLowerCase();
  if (e === ".png") return "image/png";
  if (e === ".jpg" || e === ".jpeg") return "image/jpeg";
  if (e === ".webp") return "image/webp";
  return "application/octet-stream";
}

(async () => {
  if (!PASSWORD) throw new Error("DEMO_PASSWORD env not set");
  if (!imagePath || !fs.existsSync(imagePath)) throw new Error("image not found: " + imagePath);

  const browser = await chromium.launch();
  const ctx = await browser.newContext();
  const req = ctx.request;

  // 1. Authenticate (sets access_token + csrf_token cookies on the context)
  let r = await req.post(`${API}/api/v1/auth/login`, {
    form: { username: "investigator", password: PASSWORD },
  });
  if (!r.ok()) throw new Error(`login failed ${r.status()} ${await r.text()}`);
  const csrf = (await ctx.cookies()).find((c) => c.name === "csrf_token")?.value || "";
  const H = { "X-CSRF-Token": csrf };

  // 2. Upload evidence → start investigation
  const name = path.basename(imagePath);
  const buffer = fs.readFileSync(imagePath);
  const caseId = "CASE-E2E-" + Date.now();
  r = await req.post(`${API}/api/v1/investigate`, {
    headers: H,
    multipart: {
      file: { name, mimeType: mimeFor(name), buffer },
      case_id: caseId,
      investigator_id: "investigator",
    },
  });
  if (!r.ok()) throw new Error(`investigate failed ${r.status()} ${await r.text()}`);
  const sid = (await r.json()).session_id;
  console.error(`[drive] session=${sid} mode=${mode} image="${name}"`);

  const status = async () => {
    const s = await req.get(`${API}/api/v1/sessions/${sid}/arbiter-status`);
    return await s.json();
  };
  const waitFor = async (states, timeoutMs, label) => {
    const t0 = Date.now();
    let last = "";
    while (Date.now() - t0 < timeoutMs) {
      const st = await status();
      if (st.status !== last) {
        console.error(`[drive] ${Math.round((Date.now() - t0) / 1000)}s status=${st.status} ${st.message || ""}`);
        last = st.status;
      }
      if (states.includes(st.status)) return st;
      if (st.status === "error") throw new Error("pipeline error: " + JSON.stringify(st));
      await sleep(3000);
    }
    throw new Error(`timeout waiting for ${states} (${label})`);
  };
  const resume = async (deep, phase) => {
    const rr = await req.post(`${API}/api/v1/sessions/${sid}/resume`, {
      headers: H,
      data: { deep_analysis: deep, expected_phase: phase },
    });
    console.error(`[drive] resume deep=${deep} phase=${phase} -> ${rr.status()}`);
    if (!rr.ok()) throw new Error(`resume failed ${rr.status()} ${await rr.text()}`);
  };

  // 3. Drive through the gates
  await waitFor(["awaiting_decision"], 900_000, "initial gate");
  if (mode === "initial") {
    await resume(false, "initial");
    await waitFor(["complete"], 300_000, "initial finalize");
  } else {
    await resume(true, "initial");
    await waitFor(["awaiting_deep_report"], 1_500_000, "deep gate");
    await resume(false, "deep");
    await waitFor(["complete"], 300_000, "deep finalize");
  }

  // 4. Fetch the real report DTO
  const rep = await req.get(`${API}/api/v1/sessions/${sid}/report`);
  if (!rep.ok()) throw new Error(`report fetch failed ${rep.status()} ${await rep.text()}`);
  const dto = await rep.json();

  const nar = dto.per_agent_narrative_structured || {};
  const metrics = dto.per_agent_metrics || {};
  const summary = dto.per_agent_summary || {};
  const out = {
    image: name,
    mode,
    session: sid,
    overall_verdict: dto.overall_verdict,
    manipulation_probability: dto.manipulation_probability,
    overall_confidence: dto.overall_confidence,
    verdict_sentence: dto.verdict_sentence,
    key_findings: dto.key_findings,
    per_agent: {},
  };
  for (const a of ["Agent1", "Agent3", "Agent5"]) {
    out.per_agent[a] = {
      verdict_badge: summary[a]?.verdict,
      confidence_pct: summary[a]?.confidence_pct,
      metrics_confidence: metrics[a]?.confidence_score,
      synthesis_source: nar[a]?.synthesis_source,
      agent_brief: nar[a]?.agent_brief,
      visual_description: nar[a]?.visual_description,
      key_findings: nar[a]?.key_findings,
      opinion: nar[a]?.opinion,
    };
  }

  // 5. Optional: render the real result page and read the DOM
  if (doRender) {
    const page = await ctx.newPage();
    const pageErrors = [];
    page.on("pageerror", (e) => pageErrors.push(e.message));
    await page.goto(`${WEB}/result/${sid}`, { waitUntil: "domcontentloaded" });
    await sleep(8000);
    try {
      const analysisTab = page.getByRole("button", { name: /analysis/i }).first();
      if (await analysisTab.count()) await analysisTab.click({ timeout: 3000 }).catch(() => {});
      await sleep(1000);
    } catch {}
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
    out.rendered = {
      page_errors: pageErrors,
      body_text: (await page.locator("main, body").first().innerText().catch(() => "")).replace(/\n{2,}/g, "\n"),
    };
  }

  console.log(JSON.stringify(out, null, 2));
  await browser.close();
})().catch((e) => {
  console.error("ERR", e?.stack || e);
  process.exit(1);
});
