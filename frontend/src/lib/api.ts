/** Client API: cookie di sessione + header CSRF, redirect al login su 401. */
import { goto } from '$app/navigation';

let csrfToken: string | null = null;

export function setCsrf(token: string | null) {
  csrfToken = token;
  if (token) sessionStorage.setItem('ddr_csrf', token);
  else sessionStorage.removeItem('ddr_csrf');
}

export function getCsrf(): string | null {
  if (!csrfToken) csrfToken = sessionStorage.getItem('ddr_csrf');
  return csrfToken;
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = {};
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  const csrf = getCsrf();
  if (csrf && method !== 'GET') headers['X-CSRF-Token'] = csrf;

  const res = await fetch(path, {
    method,
    headers,
    credentials: 'same-origin',
    body: body !== undefined ? JSON.stringify(body) : undefined
  });

  if (res.status === 401) {
    const here = location.pathname;
    if (here !== '/login') goto(`/login?next=${encodeURIComponent(here)}`);
    throw new ApiError(401, 'Autenticazione richiesta');
  }
  if (!res.ok) {
    let detail = `Errore ${res.status}`;
    try {
      const data = await res.json();
      if (data?.detail) detail = String(data.detail);
    } catch {
      /* body non JSON */
    }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

export const api = {
  get: <T>(path: string) => request<T>('GET', path),
  post: <T>(path: string, body?: unknown) => request<T>('POST', path, body),
  put: <T>(path: string, body?: unknown) => request<T>('PUT', path, body),
  del: <T>(path: string) => request<T>('DELETE', path)
};
