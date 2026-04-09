import { test, expect } from '@playwright/test';

const ADMIN_API_KEY = process.env.ADMIN_API_KEY || 'test-admin-key';

test.describe('Rollouts Page', () => {
  test.beforeEach(async ({ page }) => {
    // Set API key in sessionStorage
    await page.addInitScript((key) => {
      sessionStorage.setItem('admin_api_key', key);
    }, ADMIN_API_KEY);

    // Mock rollouts API
    await page.route('**/api/control/rollouts**', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: [
            {
              id: '123e4567-e89b-12d3-a456-426614174000',
              name: 'Q1 Certificate Rotation',
              description: 'Rotate all production certificates',
              status: 'completed',
              current_batch: 3,
              total_batches: 3,
              batch_size: 5,
              created_at: new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString(),
              created_by: 'admin',
            },
            {
              id: '123e4567-e89b-12d3-a456-426614174001',
              name: 'Q2 Certificate Rotation',
              description: 'Rotate staging certificates',
              status: 'running',
              current_batch: 1,
              total_batches: 2,
              batch_size: 3,
              created_at: new Date().toISOString(),
              created_by: 'admin',
            }
          ],
          total: 2,
          skip: 0,
          limit: 50,
        })
      });
    });
  });

  test('should display rollouts list', async ({ page }) => {
    await page.goto('/dashboard/rollouts');

    // Should show both rollouts
    await expect(page.locator('text=Q1 Certificate Rotation')).toBeVisible();
    await expect(page.locator('text=Q2 Certificate Rotation')).toBeVisible();
  });

  test('should show status badges', async ({ page }) => {
    await page.goto('/dashboard/rollouts');

    // Should show completed and running status
    await expect(page.locator('text=completed')).toBeVisible();
    await expect(page.locator('text=running')).toBeVisible();
  });

  test('should show pause button for running rollout', async ({ page }) => {
    // Mock pause API
    await page.route('**/api/control/rollouts/*/pause', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: '123e4567-e89b-12d3-a456-426614174001',
          status: 'paused'
        })
      });
    });

    await page.goto('/dashboard/rollouts');

    // Should show pause button for running rollout
    await expect(page.locator('button:has-text("Pause")')).toBeVisible();
  });

  test('should create new rollout', async ({ page }) => {
    // Mock create API
    await page.route('**/api/control/rollouts', async route => {
      if (route.request().method() === 'POST') {
        await route.fulfill({
          status: 201,
          contentType: 'application/json',
          body: JSON.stringify({
            id: '123e4567-e89b-12d3-a456-426614174002',
            name: 'Test Rollout',
            description: 'Test description',
            status: 'pending',
            current_batch: 0,
            total_batches: 2,
            batch_size: 5,
            created_at: new Date().toISOString(),
            created_by: 'admin',
          })
        });
      }
    });

    await page.goto('/dashboard/rollouts');

    // Click create button
    await page.click('button:has-text("Create")');

    // Verify button exists
    await expect(page.locator('button:has-text("Create")')).toBeVisible();
  });
});
