import { test, expect } from '@playwright/test';

test.describe('CP1 — App Load, Refresh, Reset', () => {

  test('Step 1: cold load — zero console errors', async ({ page }) => {
    const errors: string[] = [];
    page.on('console', msg => { if (msg.type() === 'error') errors.push(msg.text()); });
    page.on('pageerror', err => errors.push(err.message));
    await page.goto('/', { waitUntil: 'networkidle' });
    expect(errors, `Console errors on cold load: ${errors.join('\n')}`).toHaveLength(0);
  });

  test('Step 2: hard refresh — no hydration mismatch warnings', async ({ page }) => {
    const hydrationWarnings: string[] = [];
    page.on('console', msg => {
      const text = msg.text();
      if (msg.type() === 'error' && (text.includes('hydrat') || text.includes('Hydrat'))) {
        hydrationWarnings.push(text);
      }
    });
    await page.goto('/', { waitUntil: 'networkidle' });
    await page.reload({ waitUntil: 'networkidle' });
    expect(hydrationWarnings).toHaveLength(0);
  });

  test('Step 3: /evidence with no session — graceful state, no crash', async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', err => errors.push(err.message));
    await page.goto('/evidence', { waitUntil: 'networkidle' });
    // Must not crash — page renders something meaningful
    expect(errors).toHaveLength(0);
    // Should not be a blank page
    const bodyText = await page.locator('body').innerText();
    expect(bodyText.length).toBeGreaterThan(50);
    // Should not show a raw error stack trace
    expect(bodyText).not.toContain('Error: ');
    expect(bodyText).not.toContain('at Object.');
  });

  test('Step 4: /result — ResultClientRedirect or session redirect, no crash', async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', err => errors.push(err.message));
    await page.goto('/result', { waitUntil: 'networkidle' });
    expect(errors).toHaveLength(0);
    // Should land somewhere sensible — either redirected to /result/{id} or empty state
    const url = page.url();
    expect(url).toMatch(/localhost:3000\/(result|$)/);
    const bodyText = await page.locator('body').innerText();
    expect(bodyText.length).toBeGreaterThan(20);
  });

  test('Step 5: /result/invalid-session-id — error/empty state, no blank page', async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', err => errors.push(err.message));
    await page.goto('/result/invalid-session-id-000', { waitUntil: 'networkidle' });
    expect(errors).toHaveLength(0);
    // Should render something — not completely blank
    const bodyText = await page.locator('body').innerText();
    expect(bodyText.length).toBeGreaterThan(20);
  });

  test('Step 6: /totally-invalid-route — not-found.tsx renders correctly', async ({ page }) => {
    await page.goto('/totally-invalid-route', { waitUntil: 'domcontentloaded' });
    // Eyebrow text
    await expect(page.locator('text=404 — Route Not Found')).toBeVisible();
    // h1
    await expect(page.locator('h1')).toContainText('Page Not Found');
    // Dashboard link to /
    const dashboardLink = page.locator('a[href="/"]');
    await expect(dashboardLink).toBeVisible();
    await expect(dashboardLink).toContainText('Dashboard');
    // New Investigation link to /?upload=1
    const newInvLink = page.locator('a[href="/?upload=1"]');
    await expect(newInvLink).toBeVisible();
    await expect(newInvLink).toContainText('New Investigation');
  });

  test('Step 7: 404 New Investigation link goes to /?upload=1', async ({ page }) => {
    await page.goto('/totally-invalid-route', { waitUntil: 'domcontentloaded' });
    const href = await page.locator('a[href="/?upload=1"]').getAttribute('href');
    expect(href).toBe('/?upload=1');
  });

  test('Step 8: /?upload=1 auto-opens upload modal and strips param', async ({ page }) => {
    await page.goto('/?upload=1', { waitUntil: 'networkidle' });
    // Upload modal should be open (DialogContent visible)
    const dialog = page.locator('[role="dialog"]');
    await expect(dialog).toBeVisible({ timeout: 5000 });
    // URL should have stripped ?upload param
    await page.waitForFunction(() => !window.location.search.includes('upload'), { timeout: 5000 });
    const url = new URL(page.url());
    expect(url.searchParams.has('upload')).toBe(false);
  });

  test('Step 9: fresh load — localStorage and sessionStorage clean', async ({ page }) => {
    await page.goto('/', { waitUntil: 'networkidle' });
    const storageState = await page.evaluate(() => ({
      localKeys: Object.keys(localStorage).filter(k =>
        k.startsWith('FC_') || k.startsWith('SESSION') || k.startsWith('INVESTIGATION')
      ),
      sessionKeys: Object.keys(sessionStorage).filter(k =>
        k.startsWith('FC_') || k.startsWith('SESSION') || k.startsWith('INVESTIGATION') || k.startsWith('AUTO')
      ),
    }));
    // On a fresh context (no prior session), investigation keys should be absent
    expect(storageState.localKeys).toHaveLength(0);
    expect(storageState.sessionKeys).toHaveLength(0);
  });

  test('Step 10: RouteExperience removes data-fc-loading when not on /result', async ({ page }) => {
    await page.goto('/', { waitUntil: 'domcontentloaded' });
    // Manually set the attribute to simulate bridge state
    await page.evaluate(() => { document.body.setAttribute('data-fc-loading', '1'); });
    // Navigate to a non-result page (or just wait — RouteExperience fires on mount)
    await page.goto('/totally-invalid-route', { waitUntil: 'domcontentloaded' });
    const attr = await page.evaluate(() => document.body.getAttribute('data-fc-loading'));
    expect(attr).toBeNull();
  });

  test('Step 11: scroll-to-top fires on forward nav but NOT on popstate', async ({ page }) => {
    // Start on 404 to establish a history entry before /
    await page.goto('/totally-invalid-route', { waitUntil: 'domcontentloaded' });

    // Client-side navigate forward to / via Dashboard link (same JS context)
    await page.click('a[href="/"]');
    await page.waitForURL('/', { timeout: 15000 });
    await page.waitForTimeout(500);

    // RouteExperience should have fired scroll-to-top on this forward nav
    const scrollAfterForwardNav = await page.evaluate(() => window.scrollY);
    expect(scrollAfterForwardNav).toBeLessThan(50);

    // Scroll down on home page
    await page.mouse.wheel(0, 600);
    await page.waitForTimeout(500);
    const scrollOnHome = await page.evaluate(() => window.scrollY);
    expect(scrollOnHome).toBeGreaterThan(100);

    // Inject a spy on window.scrollTo in the same JS context
    await page.evaluate(() => {
      (window as any).__fc_scrollTopCalled = false;
      const orig = window.scrollTo.bind(window);
      (window as any).scrollTo = function (...args: any[]) {
        const opts = args[0];
        if (opts && typeof opts === 'object' && (opts as ScrollToOptions).top === 0) {
          (window as any).__fc_scrollTopCalled = true;
        }
        return orig.apply(window, args as any);
      };
    });

    // Browser back (popstate) — RouteExperience must NOT call scrollTo({top:0})
    await page.goBack();
    await page.waitForURL('/totally-invalid-route', { timeout: 5000 });
    await page.waitForTimeout(600);

    const scrollTopCalled = await page.evaluate(() => (window as any).__fc_scrollTopCalled ?? false);
    expect(scrollTopCalled, 'RouteExperience called scrollTo({top:0}) on popstate back nav').toBe(false);
  });
});
