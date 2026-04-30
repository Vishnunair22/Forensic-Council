import { test, expect } from '@playwright/test';
import { injectAxe, checkA11y } from 'axe-playwright';

test.describe('Accessibility (A11y) Audit', () => {
  test.beforeEach(async ({ page }) => {
    // Basic mocks to allow page to load without 401s if needed
    await page.route('**/api/v1/health', async route => {
      await route.fulfill({ status: 200, body: JSON.stringify({ status: 'healthy' }) });
    });
    await page.route('**/api/v1/auth/me', async route => {
      await route.fulfill({ status: 200, body: JSON.stringify({ user_id: 'usr_123', username: 'tester', role: 'investigator' }) });
    });
  });

  test('landing page should be WCAG 2.1 AA compliant', async ({ page }) => {
    await page.goto('/');
    await injectAxe(page);

    // Check for violations against WCAG 2.1 AA tags
    await checkA11y(page, undefined, {
      axeOptions: {
        runOnly: {
          type: 'tag',
          values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']
        }
      },
      detailedReport: true,
      detailedReportOptions: { html: true }
    });
  });

  test('upload modal should be accessible', async ({ page }) => {
    await page.goto('/');
    // Open the upload modal
    const beginBtn = page.getByRole('button', { name: /Begin Analysis/i });
    if (await beginBtn.isVisible()) {
        await beginBtn.click();
    } else {
        // Fallback for different landing page variants
        await page.getByRole('button', { name: /upload/i }).first().click();
    }

    await injectAxe(page);

    // Ensure modal focus management and labels are correct
    await checkA11y(page, '.fixed', { // Target the modal container if possible, or check whole page
        axeOptions: {
            runOnly: ['wcag2aa']
        }
    });
  });
});
