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

    // Should show dashboard content
    await expect(page.locator('text=Agents')).toBeVisible();
    await expect(page.locator('text=Certificates')).toBeVisible();
    await expect(page.locator('text=Rollouts')).toBeVisible();
  });

  test('should persist API key in localStorage', async ({ page }) => {
    await page.goto('/dashboard');

    // Enter API key
    await page.fill('input[type="password"]', ADMIN_API_KEY);
    await page.press('input[type="password"]', 'Enter');

    // Reload page
    await page.reload();

    // Should not show login prompt again
    await expect(page.locator('input[type="password"]')).not.toBeVisible();
    await expect(page.locator('text=Agents')).toBeVisible();
  });
});
