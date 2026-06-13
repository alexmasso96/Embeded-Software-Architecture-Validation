// Single fetch wrapper (plan §4.1). Every request carries the per-session
// bearer token. In dev the token comes from VITE_API_TOKEN (.env.development);
// in production (Phase 3) pywebview injects window.__ARCH_TOKEN__ before load.

declare global {
  interface Window {
    __ARCH_TOKEN__?: string;
  }
}

export function getToken(): string {
  return window.__ARCH_TOKEN__ || import.meta.env.VITE_API_TOKEN || "";
}

export class ApiError extends Error {
  status: number;
  detail: string;
  constructor(status: number, detail: string) {
    super(`${status}: ${detail}`);
    this.status = status;
    this.detail = detail;
  }
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
): Promise<T> {
  const headers: Record<string, string> = {
    Authorization: `Bearer ${getToken()}`,
  };
  if (body !== undefined) headers["Content-Type"] = "application/json";

  const res = await fetch(`/api${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const j = await res.json();
      detail = j.detail ?? detail;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, String(detail));
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, body),
  patch: <T>(path: string, body?: unknown) => request<T>("PATCH", path, body),
  put: <T>(path: string, body?: unknown) => request<T>("PUT", path, body),
  del: <T>(path: string) => request<T>("DELETE", path),
};

// EventSource for SSE — the token rides as a query param (EventSource can't set
// headers); the worker accepts ?token= for /api/events.
export function eventsUrl(): string {
  return `/api/events?token=${encodeURIComponent(getToken())}`;
}
