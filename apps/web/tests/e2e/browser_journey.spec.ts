import { test, expect } from '@playwright/test';

const SESSION_ID = '11111111-1111-4111-8111-111111111111';

const agentNames: Record<string, string> = {
  Agent1: 'Image Forensics',
  Agent2: 'Audio Forensics',
  Agent3: 'Object Detection',
  Agent4: 'Video Forensics',
  Agent5: 'Metadata Expert',
};

function liveMessage(type: string, data: Record<string, unknown> = {}) {
  return JSON.stringify({
    type,
    session_id: SESSION_ID,
    agent_id: data.agent_id ?? null,
    agent_name: data.agent_id ? agentNames[String(data.agent_id)] : null,
    message: data.message ?? 'Forensic update received',
    data: data.data ?? null,
  });
}

function completedAgent(agentId: string, phase: 'initial' | 'deep') {
  return liveMessage('AGENT_COMPLETE', {
    agent_id: agentId,
    message: `${agentNames[agentId]} ${phase} analysis complete`,
    data: {
      status: 'complete',
      confidence: phase === 'deep' ? 0.91 : 0.84,
      findings_count: phase === 'deep' ? 2 : 1,
      tools_ran: phase === 'deep' ? 5 : 3,
      tools_failed: 0,
      agent_verdict: 'LIKELY_AUTHENTIC',
      findings_preview: [{
        tool: phase === 'deep' ? 'deep_consistency_model' : 'initial_screen',
        summary: `${agentNames[agentId]} found no decisive manipulation markers during ${phase} analysis.`,
        confidence: phase === 'deep' ? 0.91 : 0.84,
        flag: 'PASS',
        severity: 'LOW',
        verdict: 'LIKELY_AUTHENTIC',
        key_signal: 'No critical artifact cluster detected.',
        section: phase,
      }],
    },
  });
}

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
      calibrated_probability: null,
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
      calibrated_probability: null,
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

async function installJourneyMocks(page: import('@playwright/test').Page) {
  let liveSocket: import('@playwright/test').WebSocketRoute | null = null;
  let arbiterComplete = false;

  const sendInitialPhase = () => {
    if (!liveSocket) return;
    liveSocket.send(liveMessage('CONNECTED', { message: 'Live stream connected' }));
    liveSocket.send(liveMessage('AGENT_UPDATE', {
      message: 'Initial forensic screening started',
      data: { thinking: 'Initial pass is dispatching across the council.' },
    }));
    for (const agentId of Object.keys(agentNames)) {
      liveSocket.send(completedAgent(agentId, 'initial'));
    }
    liveSocket.send(liveMessage('PIPELINE_PAUSED', {
      message: 'Initial analysis complete. Awaiting analyst decision.',
    }));
  };

  const sendDeepPhase = () => {
    if (!liveSocket) return;
    liveSocket.send(liveMessage('AGENT_UPDATE', {
      message: 'Deep analysis started',
      data: { thinking: 'Deep detectors are running.' },
    }));
    for (const agentId of Object.keys(agentNames)) {
      liveSocket.send(completedAgent(agentId, 'deep'));
    }
    liveSocket.send(liveMessage('PIPELINE_COMPLETE', {
      message: 'Deep analysis complete. Arbiter report ready.',
    }));
    arbiterComplete = true;
  };

  await page.routeWebSocket('**/api/v1/sessions/*/live', ws => {
    liveSocket = ws;
    setTimeout(sendInitialPhase, 100);
  });

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
      setTimeout(sendDeepPhase, 100);
    }
  });

  await page.route('**/api/v1/sessions/*/arbiter-status', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(
        arbiterComplete
          ? { status: 'complete', message: 'Final report signed.', report_id: finalReport.report_id }
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
      body: JSON.stringify(finalReport),
    });
  });
}

/**
 * Browser Journey E2E — Forensic Council
 * =====================================
 * Tests the visual and interactive journey of a forensic analyst.
 */
test.describe('Forensic Analyst Journey', () => {
  
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      window.localStorage.clear();
      window.sessionStorage.clear();
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
    await expect(page.locator('h1')).toContainText(/Multi Agent Forensic/i);
    const beginBtn = page.getByRole('button', { name: /Begin Analysis/i });
    await expect(beginBtn).toBeVisible();

    // 2. Select evidence from the landing upload modal
    await beginBtn.click();
    await page.getByLabel(/select evidence file/i).setInputFiles({
      name: 'test-evidence.png',
      mimeType: 'image/png',
      buffer: Buffer.from(
        'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII=',
        'base64',
      ),
    });

    await expect(page.getByText('test-evidence.png')).toBeVisible();

    // 3. Trigger Analysis
    const analyzeBtn = page.getByRole('button', { name: /Analyze/i });
    await expect(analyzeBtn).toBeVisible();
    await analyzeBtn.click();

    // 4. Verify Transition to Progress
    // The ProgressDisplay should appear
    await expect(page).toHaveURL(/.*evidence/);
    await expect(page.getByRole('heading', { name: /Evidence Analysis/i })).toBeVisible({ timeout: 15000 });
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

    await expect(page.locator('h1')).toContainText(/Multi Agent Forensic/i);
    await page.getByRole('button', { name: /upload a file to begin analysis/i }).click();

    const png1x1 = Buffer.from(
      'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII=',
      'base64',
    );
    await page.getByLabel(/select evidence file/i).setInputFiles({
      name: 'court-evidence.png',
      mimeType: 'image/png',
      buffer: png1x1,
    });

    await expect(page.getByText('court-evidence.png')).toBeVisible();
    await page.getByRole('button', { name: /analyze/i }).click();

    await expect(page).toHaveURL(/\/evidence/);
    await expect(page.getByRole('heading', { name: /Evidence Analysis/i })).toBeVisible({ timeout: 20_000 });
    await expect(page.getByText(/Initial results ready/i)).toBeVisible({ timeout: 20_000 });

    await page.getByRole('button', { name: /Deep Analysis/i }).click();
    await expect(page.getByText(/Comprehensive analysis finalized/i)).toBeVisible({ timeout: 20_000 });

    await page.getByRole('button', { name: /View Final Report/i }).click();
    await expect(page).toHaveURL(/\/result/);
    await expect(page.getByRole('tab', { name: /Overview/i })).toBeVisible({ timeout: 20_000 });
    await expect(page.getByText(/The council finds the evidence likely authentic/i)).toBeVisible();
    await expect(page.getByText(/Deep analysis completed and final report rendering succeeded/i)).toBeVisible();

    expect(pageErrors).toEqual([]);
  });
});
