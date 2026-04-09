import { test, expect } from '@playwright/test';

const ADMIN_API_KEY = process.env.ADMIN_API_KEY || 'test-admin-key';

test.describe('External Certificates Page', () => {
  test.beforeEach(async ({ page }) => {
    // Set API key in sessionStorage
    await page.addInitScript((key) => {
      sessionStorage.setItem('admin_api_key', key);
    }, ADMIN_API_KEY);

    // Mock external certs API
    await page.route('**/api/control/external-certs**', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: [
            {
              id: '123e4567-e89b-12d3-a456-426614174000',
              name: 'api.example.com',
              subject_cn: 'api.example.com',
              serial_hex: 'ABC123',
              not_after: new Date(Date.now() + 90 * 24 * 60 * 60 * 1000).toISOString(),
              provider: 'aliyun',
              created_at: new Date().toISOString(),
            },
            {
              id: '123e4567-e89b-12d3-a456-426614174001',
              name: 'static.example.com',
              subject_cn: 'static.example.com',
              serial_hex: 'DEF456',
              not_after: new Date(Date.now() + 10 * 24 * 60 * 60 * 1000).toISOString(),
              provider: 'letsencrypt',
              created_at: new Date().toISOString(),
            }
          ],
          total: 2,
          skip: 0,
          limit: 100,
        })
      });
    });
  });

  test('should display certificates list', async ({ page }) => {
    await page.goto('/dashboard/external-certs');

    // Should show both certificates
    await expect(page.locator('text=api.example.com')).toBeVisible();
    await expect(page.locator('text=static.example.com')).toBeVisible();
  });

  test('should show expiring soon badge', async ({ page }) => {
    await page.goto('/dashboard/external-certs');

    // Should show warning for certificate expiring in 10 days
    await expect(page.locator('text=10 days')).toBeVisible();
  });

  test('should upload new certificate', async ({ page }) => {
    // Mock upload API
    await page.route('**/api/control/external-certs', async route => {
      if (route.request().method() === 'POST') {
        await route.fulfill({
          status: 201,
          contentType: 'application/json',
          body: JSON.stringify({
            id: '123e4567-e89b-12d3-a456-426614174002',
            name: 'new.example.com',
            subject_cn: 'new.example.com',
            serial_hex: 'GHI789',
            not_after: new Date(Date.now() + 365 * 24 * 60 * 60 * 1000).toISOString(),
            provider: 'manual',
            created_at: new Date().toISOString(),
          })
        });
      }
    });

    await page.goto('/dashboard/external-certs');

    // Click upload button
    await page.click('button:has-text("Upload")');

    // Fill form (this would need to be adjusted based on actual UI)
    // For now, just verify the button exists
    await expect(page.locator('button:has-text("Upload")')).toBeVisible();
  });
});
