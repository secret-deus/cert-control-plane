import { test, expect } from '@playwright/test';

const ADMIN_API_KEY = process.env.ADMIN_API_KEY || 'test-admin-key';

test.describe('Agents Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript((key) => {
      sessionStorage.setItem('admin_api_key', key);
    }, ADMIN_API_KEY);

    await page.route('**/api/control/agents**', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: [
            { id: '1', name: 'test-agent-1', status: 'active', liveness: 'online', fingerprint: 'abc123', last_seen: new Date().toISOString(), created_at: new Date().toISOString(), cert_count: 3, expiring_soon_count: 0 },
            { id: '2', name: 'test-agent-2', status: 'pending_approval', liveness: 'offline', fingerprint: 'def456', last_seen: null, created_at: new Date().toISOString(), cert_count: 0, expiring_soon_count: 0 },
          ],
          total: 2,
        }),
      });
    });
  });

  test('should display agents page', async ({ page }) => {
    await page.goto('/agents');
    await expect(page.getByRole('heading', { name: 'Agent 管理' })).toBeVisible();
  });

  test('should show stats cards', async ({ page }) => {
    await page.goto('/agents');
    await expect(page.getByRole('button', { name: '在线' })).toBeVisible();
    await expect(page.getByRole('button', { name: '待审批' })).toBeVisible();
  });

  test('should show approve button for pending agent', async ({ page }) => {
    await page.route('**/api/control/agents/*/approve', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ id: '2', status: 'active', agent_token: 'new-token' }),
      });
    });
    await page.goto('/agents');
    await expect(page.locator('button:has-text("批准")')).toBeVisible();
  });

  test('should display agent in table', async ({ page }) => {
    await page.goto('/agents');
    await expect(page.locator('text=test-agent-1')).toBeVisible();
  });
});