import { test, expect } from '@playwright/test';

test.describe('Health Check', () => {
  test('should pass basic test', () => {
    expect(true).toBe(true);
  });

  test('should be able to navigate to a page', async ({ page }) => {
    // This test verifies Playwright browser is working
    await page.goto('data:text/html,<html><body><h1>Test</h1></body></html>');
    await expect(page.locator('h1')).toHaveText('Test');
  });
});