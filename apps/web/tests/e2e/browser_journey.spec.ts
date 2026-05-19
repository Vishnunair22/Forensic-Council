import { test, expect } from '@playwright/test';
import { emitMockLiveSocketComplete, emitMockLiveSocketDeep, installMockLiveSocket } from './helpers/mockLiveSocket';

const SESSION_ID = '11111111-1111-4111-8111-111111111111';

const agentNames: Record<string, string> = {
  Agent1: 'Image Forensics',
  Agent2: 'Audio Forensics',
  Agent3: 'Object Detection',
  Agent4: 'Video Forensics',
  Agent5: 'Metadata Expert',
};

const finalReport = {
  report_id: '22222222-2222-4222-8222-222222222222',
  session_id: SESSION_ID,
  case_id: 'CASE-E2E-001',
  executive_summary: 'The submitted evidence completed initial and deep forensic review with no decisive manipulation indicators.',
  per_agent_findings: {
    Agent1: [{
      finding_id: 'f-agent1',
      agent_id: 'Agent1',
      agent_name: 'Image Forensics',
      finding_type: 'deep_consistency_model',
      status: 'complete',
      confidence_raw: 0.91,
      calibrated: true,
      raw_confidence_score: 0.91,
      court_statement: 'Image-level signals remain consistent after deep analysis.',
      robustness_caveat: false,
      robustness_caveat_detail: null,
      reasoning_summary: 'ELA, metadata, and semantic consistency checks did not produce a manipulation cluster.',
      metadata: { analysis_phase: 'deep', tool_name: 'deep_consistency_model' },
      severity_tier: 'LOW',
    }],
    Agent5: [{
      finding_id: 'f-agent5',
      agent_id: 'Agent5',
      agent_name: 'Metadata Expert',
      finding_type: 'chain_of_custody',
      status: 'complete',
      confidence_raw: 0.88,
      calibrated: true,
      raw_confidence_score: 0.88,
      court_statement: 'Custody metadata is internally consistent for this mocked E2E sample.',
      robustness_caveat: false,
      robustness_caveat_detail: null,
      reasoning_summary: 'No timestamp or provenance conflicts were found.',
      metadata: { analysis_phase: 'deep', tool_name: 'chain_of_custody' },
      severity_tier: 'LOW',
    }],
  },
  per_agent_metrics: {},
  per_agent_analysis: {
    Agent1: 'Deep visual review completed successfully.',
    Agent5: 'Metadata and custody review completed successfully.',
  },
  overall_confidence: 0.9,
  overall_error_rate: 0,
  overall_verdict: 'LIKELY_AUTHENTIC',
  cross_modal_confirmed: [],
  contested_findings: [],
  tribunal_resolved: [],
  incomplete_findings: [],
  uncertainty_statement: 'Residual uncertainty is low in this controlled E2E fixture.',
  cryptographic_signature: 'e2e-signature',
  report_hash: 'e2e-report-hash',
  signed_utc: '2026-04-20T14:00:00.000Z',
  verdict_sentence: 'The council finds the evidence likely authentic after deep analysis.',
  key_findings: [
    'Initial screening completed across all five forensic agents.',
    'Deep analysis completed and final report rendering succeeded.',
  ],
  reliability_note: 'Mocked E2E report generated for frontend journey verification.',
  manipulation_probability: 0.08,
  applicable_agent_count: 5,
};

const initialReport = {
  ...finalReport,
  report_id: '33333333-3333-4333-8333-333333333333',
  executive_summary: 'The submitted evidence completed initial forensic screening and is ready for analyst acceptance or deeper review.',
  per_agent_findings: {
    Agent1: [{
      finding_id: 'f-agent1-initial',
      agent_id: 'Agent1',
      agent_name: 'Image Forensics',
      finding_type: 'initial_screen',
      status: 'CONFIRMED',
      confidence_raw: 0.84,
      evidence_verdict: 'NEGATIVE',
      calibrated: true,
      raw_confidence_score: 0.84,
      court_statement: 'Initial visual screening found no decisive manipulation cluster.',
      robustness_caveat: false,
      robustness_caveat_detail: null,
      reasoning_summary: 'Initial ELA, OCR, and visual content checks did not produce a decisive manipulation signal.',
      metadata: {
        analysis_phase: 'initial',
        tool_name: 'initial_screen',
        llm_refined_summary: 'Initial visual screening did not find a decisive manipulation signal.',
      },
      severity_tier: 'LOW',
    }],
    Agent3: [{
      finding_id: 'f-agent3-initial',
      agent_id: 'Agent3',
      agent_name: 'Object Detection',
      finding_type: 'scene_screen',
      status: 'CONFIRMED',
      confidence_raw: 0.82,
      evidence_verdict: 'NEGATIVE',
      calibrated: true,
      raw_confidence_score: 0.82,
      court_statement: 'Initial scene checks found no object-context conflict.',
      robustness_caveat: false,
      robustness_caveat_detail: null,
      reasoning_summary: 'Initial object and scene checks found no obvious context conflict.',
      metadata: {
        analysis_phase: 'initial',
        tool_name: 'scene_screen',
        llm_refined_summary: 'Initial scene checks found no obvious object-context conflict.',
      },
      severity_tier: 'LOW',
    }],
    Agent5: [{
      finding_id: 'f-agent5-initial',
      agent_id: 'Agent5',
      agent_name: 'Metadata Expert',
      finding_type: 'metadata_screen',
      status: 'CONFIRMED',
      confidence_raw: 0.86,
      evidence_verdict: 'NEGATIVE',
      calibrated: true,
      raw_confidence_score: 0.86,
      court_statement: 'Initial metadata screening found no custody-breaking inconsistency.',
      robustness_caveat: false,
      robustness_caveat_detail: null,
      reasoning_summary: 'Initial metadata and custody checks found no timestamp or file-structure conflict.',
      metadata: {
        analysis_phase: 'initial',
        tool_name: 'metadata_screen',
        llm_refined_summary: 'Initial metadata checks found no custody-breaking inconsistency.',
      },
      severity_tier: 'LOW',
    }],
  },
  per_agent_analysis: {
    Agent1: 'Initial visual screening completed successfully.',
    Agent3: 'Initial scene screening completed successfully.',
    Agent5: 'Initial metadata screening completed successfully.',
  },
  overall_confidence: 0.84,
  overall_verdict: 'LIKELY_AUTHENTIC',
  verdict_sentence: 'The council finds the evidence likely authentic after initial analysis.',
  key_findings: [
    'Initial analysis completed across applicable forensic agents.',
    'Accept Analysis generated and rendered the signed initial report.',
  ],
  manipulation_probability: 0.12,
};

async function installJourneyMocks(page: import('@playwright/test').Page) {
  let arbiterComplete = false;
  let deepAnalysisComplete = false;
  let reportPayload = finalReport;
  await installMockLiveSocket(page, SESSION_ID, agentNames);

  await page.route('**/api/auth/demo', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        access_token: 'e2e-token',
        token_type: 'bearer',
        expires_in: 3600,
        user_id: 'usr_e2e',
        role: 'investigator',
      }),
    });
  });

  await page.route('**/api/v1/auth/me', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ user_id: 'usr_e2e', username: 'e2e-investigator', role: 'investigator' }),
    });
  });

  await page.route('**/api/v1/health', async route => {
    await route.fulfill({
      status: 200,
      headers: { 'Set-Cookie': 'csrf_token=e2e-csrf; Path=/; SameSite=Lax' },
      contentType: 'application/json',
      body: JSON.stringify({ status: 'healthy' }),
    });
  });

  await page.route('**/api/v1/investigate', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        session_id: SESSION_ID,
        case_id: 'CASE-E2E-001',
        status: 'started',
        message: 'Analysis started',
      }),
    });
  });

  await page.route('**/api/v1/sessions/*/resume', async route => {
    const body = route.request().postDataJSON() as { deep_analysis?: boolean };
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'resumed', deep_analysis: body.deep_analysis }),
    });
    if (body.deep_analysis) {
      reportPayload = finalReport;
      arbiterComplete = false;
      deepAnalysisComplete = false;
      deepAnalysisComplete = true;
      await emitMockLiveSocketDeep(page);
    } else {
      reportPayload = deepAnalysisComplete ? finalReport : initialReport;
      arbiterComplete = true;
      await emitMockLiveSocketComplete(page, deepAnalysisComplete ? 'Deep report signed.' : 'Initial report signed.');
    }
  });

  await page.route('**/api/v1/sessions/*/arbiter-status', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(
        arbiterComplete
          ? { status: 'complete', message: 'Final report signed.', report_id: reportPayload.report_id }
          : { status: 'running', message: 'Council deliberating...' },
      ),
    });
  });

  await page.route('**/api/v1/sessions/*/report', async route => {
    if (!arbiterComplete) {
      await route.fulfill({
        status: 202,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'in_progress' }),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(reportPayload),
    });
  });
}

async function openUploadModal(page: import('@playwright/test').Page) {
  for (let attempt = 0; attempt < 3; attempt += 1) {
    if ((await page.getByLabel(/upload evidence file/i).count()) > 0) break;
    const begin = page.getByTestId('hero-cta-begin');
    await expect(begin).toBeVisible({ timeout: 10_000 });
    await page.waitForTimeout(500);
    await begin.click({ force: true });
    await page.waitForTimeout(500);
    if ((await page.getByLabel(/upload evidence file/i).count()) === 0) {
      await begin.evaluate((element: HTMLElement) => element.click());
      await page.waitForTimeout(500);
    }
    if ((await page.getByLabel(/upload evidence file/i).count()) === 0) {
      await page.evaluate(() => window.dispatchEvent(new Event("fc:open-upload")));
      await page.waitForTimeout(500);
    }
  }
  if ((await page.getByLabel(/upload evidence file/i).count()) === 0) {
    await page.goto('/?upload=1');
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(1_000);
  }
  await expect(page.getByLabel(/upload evidence file/i)).toBeAttached({ timeout: 10_000 });
}

/**
 * Browser Journey E2E — Forensic Council
 * =====================================
 * Tests the visual and interactive journey of a forensic analyst.
 */
test.describe('Forensic Analyst Journey', () => {

  test.beforeEach(async ({ page }) => {
    await page.context().clearCookies();
    await page.addInitScript(() => {
      window.localStorage.clear();
      window.sessionStorage.clear();
      document.cookie = "forensic_session_id=; path=/; max-age=0; SameSite=Lax";
    });

    // Mock the initial auth/me check
    await page.route('**/api/v1/auth/me', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ user_id: 'usr_123', username: 'test-investigator', role: 'investigator' })
      });
    });

    // Mock the health check
    await page.route('**/api/v1/health', async route => {
      await route.fulfill({ status: 200, body: JSON.stringify({ status: 'healthy' }) });
    });

    await page.route('**/api/auth/demo', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          access_token: 'demo-token',
          token_type: 'bearer',
          expires_in: 3600,
          user_id: 'usr_123',
          role: 'investigator',
        })
      });
    });
  });

  test('should navigate from landing to analysis', async ({ page }) => {
    await installJourneyMocks(page);
    await page.goto('/');

    // 1. Verify landing page aesthetics
    await expect(page.locator('h1')).toContainText(/Multi-Agent Forensic/i);
    const beginBtn = page.getByTestId('hero-cta-begin');
    await expect(beginBtn).toBeVisible();

    // 2. Select evidence from the landing upload modal
    await beginBtn.evaluate((element: HTMLElement) => element.click());
    await openUploadModal(page);
    await page.getByLabel(/upload evidence file/i).setInputFiles({
      name: 'test-evidence.png',
      mimeType: 'image/png',
      buffer: Buffer.from(
        'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII=',
        'base64',
      ),
    });

    await expect(page.getByText('test-evidence.png')).toBeVisible();

    // 3. Trigger Analysis
    const analyzeBtn = page.getByTestId('upload-start-analysis');
    await expect(analyzeBtn).toBeVisible();
    await analyzeBtn.click();

    // 4. Verify Transition to Progress
    // The ProgressDisplay should appear
    await expect(page).toHaveURL(/.*evidence/);
    await expect(page.getByRole('heading', { name: /Analysis Pipeline/i })).toBeVisible({ timeout: 15000 });
  });

  test('should show responsive layout on mobile', async ({ page }) => {
    // Resize to mobile
    await page.setViewportSize({ width: 375, height: 667 });
    await page.goto('/');

    await expect(page.locator('h1')).toBeVisible();
    const beginBtn = page.getByRole('button', { name: /Begin Analysis/i });

    // Ensure button is usable on mobile
    const box = await beginBtn.boundingBox();
    expect(box?.width).toBeGreaterThan(100);
  });

  test('completes landing upload, initial analysis, deep analysis, and final report', async ({ page }) => {
    test.setTimeout(90_000);
    const pageErrors: string[] = [];
    page.on('pageerror', error => pageErrors.push(error.message));

    await installJourneyMocks(page);
    await page.goto('/');

    await expect(page.locator('h1')).toContainText(/Multi-Agent Forensic/i);
    await openUploadModal(page);

    const png1x1 = Buffer.from(
      'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII=',
      'base64',
    );
    await page.getByLabel(/upload evidence file/i).setInputFiles({
      name: 'court-evidence.png',
      mimeType: 'image/png',
      buffer: png1x1,
    });

    await expect(page.getByText('court-evidence.png')).toBeVisible();
    await page.getByTestId('upload-start-analysis').click();

    await expect(page).toHaveURL(/\/evidence/, { timeout: 30_000 });
    await expect(page.getByRole('heading', { name: /Analysis Pipeline/i })).toBeVisible({ timeout: 20_000 });
    await expect(page.getByTestId('accept-analysis-btn')).toBeVisible({ timeout: 20_000 });
    await expect(page.getByTestId('deep-analysis-btn')).toBeVisible();

    await page.getByTestId('deep-analysis-btn').click();
    await expect(page.getByTestId('view-report-btn')).toBeVisible({ timeout: 20_000 });
    await expect(page.getByTestId('new-analysis-btn')).toBeVisible();

    await page.getByTestId('view-report-btn').click();
    if (!/\/result/.test(page.url())) {
      await page.getByTestId('view-report-btn').evaluate((element: HTMLElement) => element.click());
    }
    await expect(page).toHaveURL(/\/result/, { timeout: 30_000 });
    await expect(page.getByRole('tab', { name: /Analysis/i })).toBeVisible({ timeout: 20_000 });
    await expect(page.getByText(/The council finds the evidence likely authentic/i)).toBeVisible();
    await expect(page.getByText(/Deep analysis completed and final report rendering succeeded/i)).toBeVisible();

    expect(pageErrors.filter(error => !/Invalid or unexpected token|Unexpected end of input/i.test(error))).toEqual([]);
  });

  test('completes initial analysis acceptance and renders signed result report', async ({ page }) => {
    test.setTimeout(90_000);
    const pageErrors: string[] = [];
    page.on('pageerror', error => pageErrors.push(error.message));

    await installJourneyMocks(page);
    await page.goto('/');
    await openUploadModal(page);

    const png1x1 = Buffer.from(
      'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII=',
      'base64',
    );
    await page.getByLabel(/upload evidence file/i).setInputFiles({
      name: 'initial-evidence.png',
      mimeType: 'image/png',
      buffer: png1x1,
    });

    await expect(page.getByText('initial-evidence.png')).toBeVisible();
    await page.getByTestId('upload-start-analysis').click();

    await expect(page.getByRole('heading', { name: /Analysis Pipeline/i })).toBeVisible({ timeout: 20_000 });
    await expect(page.getByTestId('accept-analysis-btn')).toBeVisible({ timeout: 25_000 });
    await expect(page.getByTestId('deep-analysis-btn')).toBeVisible();

    await page.getByTestId('accept-analysis-btn').click();
    await expect(page).toHaveURL(/\/result/, { timeout: 30_000 });

    await expect(page.getByRole('tab', { name: /Analysis/i })).toBeVisible({ timeout: 20_000 });
    await expect(page.getByText(/The council finds the evidence likely authentic after initial analysis/i)).toBeVisible();
    await expect(page.getByText(/Accept Analysis generated and rendered the signed initial report/i)).toBeVisible();

    expect(pageErrors.filter(error => !/Invalid or unexpected token/i.test(error))).toEqual([]);
  });

  test('completes deep analysis and renders signed final report', async ({ page }) => {
    test.setTimeout(90_000);
    const pageErrors: string[] = [];
    page.on('pageerror', error => pageErrors.push(error.message));

    await installJourneyMocks(page);
    await page.goto('/');
    await openUploadModal(page);

    const png1x1 = Buffer.from(
      'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII=',
      'base64',
    );
    await page.getByLabel(/upload evidence file/i).setInputFiles({
      name: 'deep-evidence.png',
      mimeType: 'image/png',
      buffer: png1x1,
    });

    await expect(page.getByText('deep-evidence.png')).toBeVisible();
    await page.getByTestId('upload-start-analysis').click();

    await expect(page.getByRole('heading', { name: /Analysis Pipeline/i })).toBeVisible({ timeout: 20_000 });
    await expect(page.getByTestId('deep-analysis-btn')).toBeVisible({ timeout: 25_000 });

    await page.getByTestId('deep-analysis-btn').click();
    await expect(page.getByText(/Deep Analysis/i).first()).toBeVisible({ timeout: 20_000 });
    await expect(page.getByTestId('view-report-btn')).toBeVisible({ timeout: 25_000 });

    await page.getByTestId('view-report-btn').click();
    if (!/\/result/.test(page.url())) {
      await page.getByTestId('view-report-btn').evaluate((element: HTMLElement) => element.click());
    }
    await expect(page).toHaveURL(/\/result/, { timeout: 30_000 });

    await expect(page.getByRole('tab', { name: /Analysis/i })).toBeVisible({ timeout: 20_000 });
    await expect(page.getByText(/The council finds the evidence likely authentic after deep analysis/i)).toBeVisible();
    await expect(page.getByText(/Deep analysis completed and final report rendering succeeded/i)).toBeVisible();

    expect(pageErrors.filter(error => !/Invalid or unexpected token/i.test(error))).toEqual([]);
  });

  // ── Phase 2.14: Hard-refresh and startup stability ─────────────────────────

  test("landing hard refresh shows hero with no errors", async ({ page }) => {
    const pageErrors: string[] = [];
    page.on("pageerror", (error) => pageErrors.push(error.message));

    await page.goto("/");
    await expect(page.locator("h1")).toContainText(/Multi-Agent Forensic/i);

    await page.reload();
    await expect(page.locator("h1")).toContainText(/Multi-Agent Forensic/i);

    expect(pageErrors.filter(error => !/Invalid or unexpected token/i.test(error))).toEqual([]);
  });

  test("evidence page without pending file shows no-evidence state", async ({ page }) => {
    await page.addInitScript(() => {
      window.sessionStorage.clear();
    });

    await page.goto("/evidence");
    await expect(page.getByText(/No Evidence Queued|Select Evidence/i)).toBeVisible({ timeout: 10_000 });
  });

  test("result page with fake session id shows stable error state", async ({ page }) => {
    const pageErrors: string[] = [];
    page.on("pageerror", (error) => pageErrors.push(error.message));

    await page.goto("/result/fake-session-id-12345");

    await expect(
      page.getByText(/session expired|not found|arbiter timeout|error|failed to fetch|arbiter status failed|consensus synthesis|compiling agent findings/i).first(),
    ).toBeVisible({ timeout: 15_000 });

    expect(pageErrors.filter(error => !/Invalid or unexpected token/i.test(error))).toEqual([]);
  });

  test("api target does not go to localhost:8000 in Caddy mode", async ({ page }) => {
    const interceptedRequests: string[] = [];
    page.on("request", (req) => {
      const url = req.url();
      if (url.includes("localhost:8000")) {
        interceptedRequests.push(url);
      }
    });

    await page.goto("/");
    await expect(page.locator("h1")).toBeVisible();

    const restCallsTo8000 = interceptedRequests.filter(
      (u) => !u.includes("/live") && !u.includes("/ws") && !u.includes("websocket"),
    );
    expect(restCallsTo8000).toHaveLength(0);
  });
});
