import { test, expect } from '@playwright/test';

const ADMIN_API_KEY = process.env.ADMIN_API_KEY || 'test-admin-key';

test.describe('Dashboard Login', () => {
  test.beforeEach(async ({ page }) => {
    // Mock the API key verification
    await page.route('**/api/control/dashboard/summary', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          agents: { total: 0, active: 0, pending_approval: 0 },
          certificates: { total_active: 0, expiring_soon: 0 },
          rollouts: { running: 0 }
        })
      });
    });
  });

  test('should display login prompt on first visit', async ({ page }) => {
    await page.goto('/dashboard');

    // Should show API key input
    await expect(page.locator('input[type="password"]')).toBeVisible();
  });

  test('should accept valid API key and show dashboard', async ({ page }) => {
    await page.goto('/dashboard');

    // Enter API key
    await page.fill('input[type="password"]', ADMIN_API_KEY);
    await page.press('input[type="password"]', 'Enter');

    // Should show dashboard content (sidebar items are in Chinese)
    await expect(page.getByText('Agent 舰队')).toBeVisible();
  });

  test('should persist API key in sessionStorage', async ({ page }) => {
    await page.goto('/dashboard');

    // Enter API key
    await page.fill('input[type="password"]', ADMIN_API_KEY);
    await page.press('input[type="password"]', 'Enter');

    // Should be logged in
    await expect(page.getByText('Agent 舰队')).toBeVisible();

    // Reload page - should stay logged in via sessionStorage
    await page.reload();

    // Should not show login prompt again
    await expect(page.locator('input[type="password"]')).not.toBeVisible();
  });

  test('should clear expired API key session', async ({ page }) => {
    await page.addInitScript(() => {
      sessionStorage.setItem('admin_api_key', 'expired-test-key');
      sessionStorage.setItem('admin_api_key_last_active', '1');
    });

    await page.goto('/dashboard');

    await expect(page.locator('input[type="password"]')).toBeVisible();
    await expect(page.evaluate(() => sessionStorage.getItem('admin_api_key'))).resolves.toBeNull();
  });
});
