/** Shared API fetch helper for the Cert Control Plane frontend. */

const API_BASE = '/api/control';

export function getApiKey(): string | null {
  return sessionStorage.getItem('admin_api_key');
}

/** Generic fetch with API key header. Throws on auth failure. */
export async function apiFetch<T>(
  path: string,
  opts: RequestInit = {}
): Promise<T> {
  const apiKey = getApiKey();
  if (!apiKey) throw new Error('Not authenticated');

  const res = await fetch(`${API_BASE}${path}`, {
    ...opts,
    headers: {
      'Content-Type': 'application/json',
      'X-Admin-API-Key': apiKey,
      ...(opts.headers || {}),
    },
  });

  if (res.status === 401 || res.status === 403) {
    sessionStorage.removeItem('admin_api_key');
    window.location.reload();
    throw new Error('Unauthorized');
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail || `API error ${res.status}`);
  }

  return res.json();
}

/** POST helper */
export function apiPost<T>(path: string, body?: unknown): Promise<T> {
  return apiFetch<T>(path, {
    method: 'POST',
    body: body ? JSON.stringify(body) : undefined,
  });
}
