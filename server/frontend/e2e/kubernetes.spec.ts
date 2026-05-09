import { test, expect } from '@playwright/test';

const ADMIN_API_KEY = process.env.ADMIN_API_KEY || 'test-admin-key';

const assignment = {
  id: 'assignment-1',
  cluster_id: 'cluster-1',
  external_cert_id: 'cert-1',
  namespace: 'default',
  secret_name: 'api-tls',
  lifecycle_status: 'pending',
  health_status: 'unknown',
  auto_track_latest: true,
  auto_deploy: false,
  pending_update: false,
  current_resource_version: null,
  current_serial_hex: null,
  last_snapshot_serial_hex: null,
  last_deployed_at: null,
  last_validated_at: null,
  is_active: true,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
  cluster_name: 'minikube-dev',
  external_cert_subject_cn: 'api.example.com',
};

test.describe('Kubernetes Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript((key) => {
      sessionStorage.setItem('admin_api_key', key);
    }, ADMIN_API_KEY);

    await page.route('**/api/control/dashboard/cert-alerts', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          summary: {
            external: { expired: 0, critical: 0, warning: 0, notice: 0 },
            agent: { expired: 0, critical: 0, warning: 0, notice: 0 },
          },
        }),
      });
    });

    await page.route('**/api/control/kubernetes/clusters**', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: [
            {
              id: 'cluster-1',
              name: 'minikube-dev',
              environment: 'dev',
              api_server: 'https://127.0.0.1:8443',
              default_namespace: 'default',
              connection_status: 'unknown',
              last_checked_at: null,
              created_at: new Date().toISOString(),
              updated_at: new Date().toISOString(),
            },
          ],
          total: 1,
          skip: 0,
          limit: 500,
        }),
      });
    });

    await page.route('**/api/control/kubernetes/assignments**', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: [assignment], total: 1, skip: 0, limit: 500 }),
      });
    });

    await page.route('**/api/control/kubernetes/operations**', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: [], total: 0, skip: 0, limit: 100 }),
      });
    });

    await page.route('**/api/control/external-certs**', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: [
            {
              id: 'cert-1',
              name: 'api.example.com',
              subject_cn: 'api.example.com',
              serial_hex: 'abc123',
              not_before: new Date().toISOString(),
              not_after: new Date(Date.now() + 90 * 86400000).toISOString(),
              provider: 'manual',
              is_active: true,
              created_at: new Date().toISOString(),
              updated_at: new Date().toISOString(),
            },
          ],
          total: 1,
          skip: 0,
          limit: 1000,
        }),
      });
    });
  });

  test('should display kubernetes page and assignments', async ({ page }) => {
    await page.goto('/kubernetes');

    await expect(page.getByRole('heading', { name: 'Kubernetes TLS Secret' })).toBeVisible();
    await expect(page.getByText('minikube-dev').first()).toBeVisible();
    await expect(page.getByText('default/api-tls').first()).toBeVisible();
    await expect(page.getByText('api.example.com').first()).toBeVisible();
  });

  test('should run deploy dry-run and confirm with dry_run_id', async ({ page }) => {
    let confirmBody = '';

    await page.route('**/api/control/kubernetes/assignments/assignment-1/deploy/dry-run', async route => {
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'dry-run-1',
          cluster_id: 'cluster-1',
          assignment_id: 'assignment-1',
          action: 'deploy',
          external_cert_id: 'cert-1',
          namespace: 'default',
          secret_name: 'api-tls',
          current_resource_version: null,
          diff: [
            { path: 'data.tls.crt', before: null, after: 'abc123', sensitive: false },
            { path: 'data.tls.key', before: null, after: 'updated', sensitive: true },
          ],
          status: 'pending',
          expires_at: new Date(Date.now() + 600000).toISOString(),
          created_by: 'admin',
          created_at: new Date().toISOString(),
        }),
      });
    });

    await page.route('**/api/control/kubernetes/assignments/assignment-1/deploy/confirm', async route => {
      confirmBody = route.request().postData() || '';
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ...assignment,
          lifecycle_status: 'deployed',
          health_status: 'healthy',
          current_serial_hex: 'abc123',
        }),
      });
    });

    await page.goto('/kubernetes');
    await page.getByRole('button', { name: 'Dry run' }).click();
    await expect(page.getByText('data.tls.crt')).toBeVisible();

    await page.getByRole('button', { name: 'Confirm deploy' }).click();
    expect(confirmBody).toContain('dry-run-1');
  });
});
