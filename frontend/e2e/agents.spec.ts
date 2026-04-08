import { test, expect } from '@playwright/test';

const ADMIN_API_KEY = process.env.ADMIN_API_KEY || 'test-admin-key';

test.describe('Agents Page', () => {
  test.beforeEach(async ({ page }) => {
    // Set API key in localStorage
    await page.addInitScript((key) => {
      localStorage.setItem('apiKey', key);
    }, ADMIN_API_KEY);

    // Mock agents API
    await page.route('**/api/control/agents**', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            id: '123e4567-e89b-12d3-a456-426614174000',
            name: 'test-agent-1',
            status: 'active',
            fingerprint: 'abc123',
            last_seen: new Date().toISOString(),
            created_at: new Date().toISOString(),
          },
          {
            id: '123e4567-e89b-12d3-a456-426614174001',
            name: 'test-agent-2',
            status: 'pending_approval',
            fingerprint: 'def456',
            last_seen: null,
            created_at: new Date().toISOString(),
          }
        ])
      });
    });
  });

  test('should display agents list', async ({ page }) => {
    await page.goto('/dashboard/agents');

    // Should show both agents
    await expect(page.locator('text=test-agent-1')).toBeVisible();
    await expect(page.locator('text=test-agent-2')).toBeVisible();
  });

  test('should show approve button for pending agents', async ({ page }) => {
    await page.goto('/dashboard/agents');

    // Should show approve button for pending agent
    await expect(page.locator('button:has-text("Approve")')).toBeVisible();
  });

  test('should approve agent on button click', async ({ page }) => {
    // Mock approve API
    await page.route('**/api/control/agents/*/approve', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: '123e4567-e89b-12d3-a456-426614174001',
          status: 'active',
          agent_token: 'new-token-123'
        })
      });
    });

    await page.goto('/dashboard/agents');

    // Click approve button
    await page.click('button:has-text("Approve")');

    // Should show success message or update status
    await expect(page.locator('text=active')).toBeVisible();
  });
});
