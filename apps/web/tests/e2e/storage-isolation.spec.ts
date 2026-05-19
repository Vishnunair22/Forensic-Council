import { test, expect } from "@playwright/test";

test.describe.serial("E2E Storage and Session State Isolation Verification", () => {
  test.beforeEach(async ({ page }) => {
    // Clear cookies, localStorage, and sessionStorage
    await page.context().clearCookies();
    await page.goto("/");
    await page.evaluate(() => {
      window.localStorage.clear();
      window.sessionStorage.clear();
    });
  });

  test("Step 1: Set unique test keys in browser storage and verify persistence", async ({ page }) => {
    await page.goto("/");
    await page.evaluate(() => {
      window.localStorage.setItem("test_e2e_isolated_key", "polluted_value");
      window.sessionStorage.setItem("test_e2e_isolated_session_key", "polluted_session_value");
      document.cookie = "test_e2e_cookie=polluted_cookie_value; path=/";
    });

    const localVal = await page.evaluate(() => window.localStorage.getItem("test_e2e_isolated_key"));
    const sessionVal = await page.evaluate(() => window.sessionStorage.getItem("test_e2e_isolated_session_key"));
    const cookieVal = await page.evaluate(() => document.cookie);

    expect(localVal).toBe("polluted_value");
    expect(sessionVal).toBe("polluted_session_value");
    expect(cookieVal).toContain("test_e2e_cookie=polluted_cookie_value");
  });

  test("Step 2: Assert state pollution is prevented and storage is cleanly isolated", async ({ page }) => {
    await page.goto("/");

    const localVal = await page.evaluate(() => window.localStorage.getItem("test_e2e_isolated_key"));
    const sessionVal = await page.evaluate(() => window.sessionStorage.getItem("test_e2e_isolated_session_key"));
    const cookieVal = await page.evaluate(() => document.cookie);

    // Verify localStorage, sessionStorage and cookies are fully pristine/cleared
    expect(localVal).toBeNull();
    expect(sessionVal).toBeNull();
    expect(cookieVal).not.toContain("test_e2e_cookie=polluted_cookie_value");
  });
});
