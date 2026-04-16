import { test, expect } from '@playwright/test';

/**
 * Browser Journey E2E — Forensic Council
 * =====================================
 * Tests the visual and interactive journey of a forensic analyst.
 */
test.describe('Forensic Analyst Journey', () => {
  
  test.beforeEach(async ({ page }) => {
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

    // Mock investigation start
    await page.route('**/api/v1/investigate', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ session_id: 'sess_mock_001', message: 'Analysis started' })
      });
    });

    // Mock report fetch
    await page.route('**/api/v1/sessions/*/report', async route => {
      await route.fulfill({
        status: 202, // In progress
        contentType: 'application/json',
        body: JSON.stringify({ status: 'in_progress' })
      });
    });
  });

  test('should navigate from landing to analysis', async ({ page }) => {
    await page.goto('/');

    // 1. Verify landing page aesthetics
    await expect(page.locator('h1')).toContainText(/Multi Agent Forensic/i);
    const beginBtn = page.getByRole('button', { name: /Begin Analysis/i });
    await expect(beginBtn).toBeVisible();

    // 2. Start movement
    await beginBtn.click();
    await expect(page).toHaveURL(/.*evidence/);

    // 3. File Upload Interaction
    // Note: We use the hidden input for reliability
    const fileChooserPromise = page.waitForEvent('filechooser');
    await page.locator('div').filter({ hasText: /^Drop forensic evidence here$/ }).click();
    const fileChooser = await fileChooserPromise;
    await fileChooser.setFiles({
      name: 'test-evidence.jpg',
      mimeType: 'image/jpeg',
      buffer: Buffer.from('fake-image-content'),
    });

    await expect(page.getByText('test-evidence.jpg')).toBeVisible();

    // 4. Trigger Analysis
    const analyseBtn = page.getByRole('button', { name: /Begin Investigation|Analyse/i });
    await expect(analyseBtn).toBeVisible();
    await analyseBtn.click();

    // 5. Verify Transition to Progress
    // The ProgressDisplay should appear
    await expect(page.getByText(/Agents Verified/i)).toBeVisible({ timeout: 15000 });
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
});
