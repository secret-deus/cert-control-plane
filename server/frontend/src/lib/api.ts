/** Shared API fetch helper for the Cert Control Plane frontend. */

const API_BASE = '/api/control';

export function getApiKey(): string | null {
  return sessionStorage.getItem('admin_api_key');
}

/** Custom error class with HTTP status code */
export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

/** Generic fetch with API key header. Throws ApiError on failure. */
export async function apiFetch<T>(
  path: string,
  opts: RequestInit = {}
): Promise<T> {
  const apiKey = getApiKey();

  const res = await fetch(`${API_BASE}${path}`, {
    ...opts,
    headers: {
      'Content-Type': 'application/json',
      ...(apiKey ? { 'X-Admin-API-Key': apiKey } : {}),
      ...(opts.headers || {}),
    },
  });

  if (res.status === 401) {
    sessionStorage.removeItem('admin_api_key');
    window.dispatchEvent(new CustomEvent('auth:expired'));
    throw new ApiError(401, 'Authentication expired');
  }

  if (res.status === 403) {
    throw new ApiError(403, 'Permission denied');
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(res.status, body.detail || `API error ${res.status}`);
  }

  if (res.status === 204) {
    return undefined as T;
  }

  const bodyText = await res.text();
  if (!bodyText) {
    return undefined as T;
  }

  return JSON.parse(bodyText) as T;
}

// Query key factories for @tanstack/react-query
export const queryKeys = {
  dashboard: ['dashboard'] as const,
  dashboardSummary: ['dashboard', 'summary'] as const,
  dashboardHealth: ['dashboard', 'health'] as const,
  dashboardAlerts: ['dashboard', 'alerts'] as const,
  dashboardEvents: ['dashboard', 'events'] as const,
  agents: (params?: Record<string, string>) => ['agents', params] as const,
  agent: (id: string) => ['agent', id] as const,
  certificates: (params?: Record<string, string>) => ['certificates', params] as const,
  externalCerts: (params?: Record<string, string>) => ['externalCerts', params] as const,
  auditLogs: (params?: Record<string, string>) => ['auditLogs', params] as const,
};

/** POST helper */
export function apiPost<T>(path: string, body?: unknown): Promise<T> {
  return apiFetch<T>(path, {
    method: 'POST',
    body: body ? JSON.stringify(body) : undefined,
  });
}

/** DELETE helper */
export function apiDelete<T>(path: string): Promise<T> {
  return apiFetch<T>(path, { method: 'DELETE' });
}

/** Upload helper for multipart/form-data */
export async function apiUpload<T>(
  path: string,
  formData: FormData
): Promise<T> {
  const apiKey = getApiKey();

  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: {
      ...(apiKey ? { 'X-Admin-API-Key': apiKey } : {}),
    },
    body: formData,
  });

  if (res.status === 401) {
    sessionStorage.removeItem('admin_api_key');
    window.dispatchEvent(new CustomEvent('auth:expired'));
    throw new ApiError(401, 'Authentication expired');
  }

  if (res.status === 403) {
    throw new ApiError(403, 'Permission denied');
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(res.status, body.detail || `API error ${res.status}`);
  }

  const bodyText = await res.text();
  if (!bodyText) {
    return undefined as T;
  }

  return JSON.parse(bodyText) as T;
}
