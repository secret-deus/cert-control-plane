import { test, expect } from '@playwright/test';

const ADMIN_API_KEY = process.env.ADMIN_API_KEY || 'test-admin-key';

test.describe('Dashboard', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript((key) => {
      sessionStorage.setItem('admin_api_key', key);
    }, ADMIN_API_KEY);

    await page.route('**/api/control/dashboard/summary', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          agents: { total: 5, active: 3, pending_approval: 1 },
          certificates: { total_active: 20, expiring_soon: 3 },
          rollouts: { running: 1 },
        }),
      });
    });

    await page.route('**/api/control/dashboard/agents-health', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          { id: '1', name: 'agent-01', status: 'active', liveness: 'online', last_seen: new Date().toISOString(), cert_expires_at: null, cert_revoked_at: null },
          { id: '2', name: 'agent-02', status: 'active', liveness: 'offline', last_seen: null, cert_expires_at: null, cert_revoked_at: null },
        ]),
      });
    });

    await page.route('**/api/control/dashboard/cert-alerts', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          summary: { external: { expired: 1, critical: 2, warning: 3, notice: 0 }, agent: { expired: 0, critical: 0, warning: 0, notice: 0 } },
          external_certs: { expired: [], critical: [], warning: [] },
          agent_certs: { expired: [], critical: [], warning: [] },
        }),
      });
    });

    await page.route('**/api/control/external-certs**', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: [], total: 0 }),
      });
    });

    await page.route('**/api/control/dashboard/certs-expiry**', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      });
    });

    await page.route('**/api/control/dashboard/events', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      });
    });
  });

  test('should display KPI cards', async ({ page }) => {
    await page.goto('/dashboard');
    await expect(page.getByText('证书总数').first()).toBeVisible();
    await expect(page.getByText('7天内过期').first()).toBeVisible();
  });

  test('should display agent health section', async ({ page }) => {
    await page.goto('/dashboard');
    await expect(page.getByText('Agent 健康状态')).toBeVisible();
  });

  test('should display activity log section', async ({ page }) => {
    await page.goto('/dashboard');
    await expect(page.getByRole('heading', { name: '最近操作日志' })).toBeVisible();
  });
});
