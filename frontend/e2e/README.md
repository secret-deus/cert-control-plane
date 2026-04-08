# E2E Testing with Playwright

This directory contains end-to-end tests for the Cert Control Plane frontend.

## Prerequisites

1. Install dependencies:
   ```bash
   npm install
   ```

2. Install Playwright browsers:
   ```bash
   npx playwright install
   ```

## Running Tests

### Run all tests
```bash
npm run test:e2e
```

### Run tests with UI
```bash
npm run test:e2e:ui
```

### Run tests in debug mode
```bash
npm run test:e2e:debug
```

### Run specific test file
```bash
npx playwright test login.spec.ts
```

## Test Structure

- `login.spec.ts` - Dashboard login and authentication tests
- `agents.spec.ts` - Agent management page tests
- `certificates.spec.ts` - External certificates page tests
- `rollouts.spec.ts` - Rollout management page tests

## Writing Tests

### Best Practices

1. **Use mock APIs**: Tests should not depend on a running backend server. Use `page.route()` to mock API responses.

2. **Set authentication**: Use `page.addInitScript()` to set the API key in localStorage before tests run.

3. **Test user flows**: Focus on testing complete user interactions, not individual components.

4. **Keep tests independent**: Each test should be self-contained and not depend on other tests.

### Example Test

```typescript
import { test, expect } from '@playwright/test';

test.describe('My Feature', () => {
  test.beforeEach(async ({ page }) => {
    // Set up authentication
    await page.addInitScript((key) => {
      localStorage.setItem('apiKey', key);
    }, 'test-api-key');

    // Mock API responses
    await page.route('**/api/endpoint', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ data: 'mocked' })
      });
    });
  });

  test('should do something', async ({ page }) => {
    await page.goto('/dashboard');
    await expect(page.locator('text=Expected')).toBeVisible();
  });
});
```

## CI Integration

Tests are automatically run in CI pipeline. See `.github/workflows/ci.yml` for configuration.

## Debugging

1. **Use UI mode**: `npm run test:e2e:ui` opens an interactive UI where you can step through tests.

2. **Use debug mode**: `npm run test:e2e:debug` runs tests with the Playwright Inspector.

3. **View traces**: After a failed test, open the HTML report to view traces:
   ```bash
   npx playwright show-report
   ```

## Environment Variables

- `ADMIN_API_KEY`: Admin API key for authentication (defaults to 'test-admin-key')
- `BASE_URL`: Base URL for tests (defaults to 'https://localhost:443')
