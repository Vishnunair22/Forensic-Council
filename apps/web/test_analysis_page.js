const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  // Set a standard desktop viewport size
  await page.setViewportSize({ width: 1280, height: 800 });
  try {
    console.log('Navigating to landing page...');
    await page.goto('http://localhost:3000');
    
    console.log('Opening upload modal...');
    await page.click('[data-testid="hero-cta-begin"]');
    await page.waitForTimeout(600);
    
    console.log('Selecting file...');
    const fileInput = await page.$('input[id="evidence-file-input"]');
    await fileInput.setInputFiles('d:\\Forensic Council\\apps\\api\\tests\\fixtures\\test_image.webp');
    await page.waitForTimeout(1500);
    
    console.log('Starting analysis...');
    await page.click('[data-testid="upload-start-analysis"]');
    
    // Wait for transition to /evidence page
    console.log('Waiting for evidence page mount...');
    await page.waitForURL('**/evidence', { timeout: 15000 });
    
    // Wait 4 seconds for loading overlay (min 2.5s) to dismiss and capture active running state
    console.log('Waiting for loading overlay dismissal...');
    await page.waitForTimeout(4000);
    await page.screenshot({
      path: 'C:\\Users\\vishn\\.gemini\\antigravity\\brain\\fffeb7b3-013d-4966-962b-13176e682f13\\evidence_running.png',
      fullPage: true
    });
    console.log('Captured evidence_running.png');
    
    // Wait for the decision buttons to appear (up to 60s)
    console.log('Waiting for initial analysis completion and HITL decision gates...');
    await page.waitForSelector('[data-testid="deep-analysis-btn"]', { timeout: 60000 });
    await page.screenshot({
      path: 'C:\\Users\\vishn\\.gemini\\antigravity\\brain\\fffeb7b3-013d-4966-962b-13176e682f13\\evidence_decision.png',
      fullPage: true
    });
    console.log('Captured evidence_decision.png');
    
    // Trigger deep analysis
    console.log('Triggering Deep Analysis...');
    await page.click('[data-testid="deep-analysis-btn"]');
    
    // Wait for deep analysis completion (up to 60s)
    console.log('Waiting for deep analysis complete state...');
    await page.waitForSelector('[data-testid="view-report-btn"]', { timeout: 60000 });
    await page.screenshot({
      path: 'C:\\Users\\vishn\\.gemini\\antigravity\\brain\\fffeb7b3-013d-4966-962b-13176e682f13\\evidence_deep_complete.png',
      fullPage: true
    });
    console.log('Captured evidence_deep_complete.png');
    
    console.log('FLOW_VERIFICATION_COMPLETE');
  } catch (error) {
    console.error('Error during flow verification:', error);
  } finally {
    await browser.close();
  }
})();
