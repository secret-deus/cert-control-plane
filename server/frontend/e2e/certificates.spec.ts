import { test, expect } from '@playwright/test';

const ADMIN_API_KEY = process.env.ADMIN_API_KEY || 'test-admin-key';

test.describe('Certificate Management Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript((key) => {
      sessionStorage.setItem('admin_api_key', key);
    }, ADMIN_API_KEY);

    await page.route('**/api/control/external-certs**', async route => {
      if (route.request().method() === 'POST') {
        await route.fulfill({
          status: 201,
          contentType: 'application/json',
          body: JSON.stringify({
            id: 'new-cert-id',
            name: 'new.example.com',
            subject_cn: 'new.example.com',
            serial_hex: 'ABC123',
            not_after: new Date(Date.now() + 365 * 86400000).toISOString(),
            provider: 'manual',
          }),
        });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: [
            {
              id: 'cert-1',
              name: 'api.example.com',
              subject_cn: 'api.example.com',
              serial_hex: 'DEF456',
              not_before: new Date().toISOString(),
              not_after: new Date(Date.now() + 90 * 86400000).toISOString(),
              provider: 'aliyun',
              is_active: true,
              auto_renew: false,
              created_at: new Date().toISOString(),
            },
          ],
          total: 1,
        }),
      });
    });

    await page.route('**/api/control/agents**', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: [], total: 0 }),
      });
    });
  });

  test('should display certificate management page', async ({ page }) => {
    await page.goto('/certificates');
    await expect(page.getByRole('heading', { level: 1, name: '证书资产' })).toBeVisible();
  });

  test('should show certificates in table', async ({ page }) => {
    await page.goto('/certificates');
    await expect(page.getByText('api.example.com').first()).toBeVisible();
  });

  test('should show filter buttons', async ({ page }) => {
    await page.goto('/certificates');
    await expect(page.getByRole('button', { name: '全部' })).toBeVisible();
    await expect(page.getByRole('button', { name: '健康' })).toBeVisible();
  });

  test('should show upload button', async ({ page }) => {
    await page.goto('/certificates');
    await expect(page.getByRole('button', { name: /上传证书/ })).toBeVisible();
  });

  test('should show certificate detail drawer on click', async ({ page }) => {
    await page.route('**/api/control/external-certs/cert-1', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'cert-1',
          name: 'api.example.com',
          subject_cn: 'api.example.com',
          serial_hex: 'DEF456',
          not_before: new Date().toISOString(),
          not_after: new Date(Date.now() + 90 * 86400000).toISOString(),
          provider: 'aliyun',
          is_active: true,
          cert_pem: '-----BEGIN CERTIFICATE-----\nMIID...\n-----END CERTIFICATE-----',
          chain_pem: null,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        }),
      });
    });

    await page.goto('/certificates');
    await page.getByText('api.example.com').first().click();
    await expect(page.getByText('证书详情抽屉')).toBeVisible();
  });
});
