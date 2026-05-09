import { test, expect } from '@playwright/test';

const ADMIN_API_KEY = process.env.ADMIN_API_KEY || 'test-admin-key';

test.describe('Agents Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript((key) => {
      sessionStorage.setItem('admin_api_key', key);
    }, ADMIN_API_KEY);

    await page.route('**/api/control/agents**', async route => {
      if (route.request().url().includes('/detail')) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            id: '1',
            name: 'test-agent-1',
            description: 'Test agent',
            status: 'active',
            liveness: 'online',
            fingerprint: 'abc123',
            last_seen: new Date().toISOString(),
            created_at: new Date().toISOString(),
            cert_count: 3,
            expiring_soon_count: 0,
            certs: [
              {
                local_path: '/etc/nginx/ssl/api.example.com.crt',
                cert_name: 'api.example.com',
                subject_cn: 'api.example.com',
                not_after: new Date(Date.now() + 90 * 86400000).toISOString(),
                days_remaining: 90,
                urgency: 'normal',
              },
            ],
          }),
        });
        return;
      }

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
    await expect(page.getByRole('heading', { level: 1, name: 'Agent 舰队' })).toBeVisible();
  });

  test('should show stats cards', async ({ page }) => {
    await page.goto('/agents');
    await expect(page.getByText('在线').first()).toBeVisible();
    await expect(page.getByText('待审批').first()).toBeVisible();
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
    await expect(page.getByText('test-agent-1').first()).toBeVisible();
  });

  test('should show agent detail on click', async ({ page }) => {
    await page.goto('/agents');
    await page.getByText('test-agent-1').first().click();
    await expect(page.getByText('节点详情')).toBeVisible();
  });
});
