import 'server-only';
import { NextRequest, NextResponse } from 'next/server';

export const ACCESS_COOKIE = 'wm_access';
export const REFRESH_COOKIE = 'wm_refresh';
const BACKEND_URL = process.env.WORKMATE_INTERNAL_API_URL ?? 'http://127.0.0.1:8000/api/v1';

export function backendUrl(path: string): string {
  // Relative routes only; disallow percent-decoded traversal and absolute URLs.
  if (!path.startsWith('/') || path.startsWith('//') || path.includes('..') || path.includes('\\')) {
    throw new Error('Invalid backend route');
  }
  return BACKEND_URL.replace(/\/$/, '') + path;
}

export function checkCsrf(request: NextRequest): boolean {
  if (['GET', 'HEAD', 'OPTIONS'].includes(request.method)) return true;
  const origin = request.headers.get('origin');
  const referer = request.headers.get('referer');
  const target = request.nextUrl.origin;
  // Require the browser Origin; non-browser clients have no authenticated cookie.
  if (origin) return origin === target;
  if (!referer) return false;
  try { return new URL(referer).origin === target; } catch { return false; }
}

export function cookieOptions(maxAge: number) {
  return {
    httpOnly: true,
    // Only the disposable HTTP-loopback browser CI may turn off Secure.
    secure: process.env.NODE_ENV === 'production' && !(
      process.env.WORKMATE_BROWSER_SMOKE === '1' &&
      /^http:\/\/(127\.0\.0\.1|localhost):8000\/api\/v1$/.test(BACKEND_URL)
    ),
    sameSite: 'strict' as const, path: '/', maxAge,
  };
}

export function setAuthCookies(response: NextResponse, access: string, refresh?: string) {
  response.cookies.set(ACCESS_COOKIE, access, cookieOptions(60 * 60));
  if (refresh) response.cookies.set(REFRESH_COOKIE, refresh, cookieOptions(60 * 60 * 24 * 7));
}

export function clearAuthCookies(response: NextResponse) {
  response.cookies.set(ACCESS_COOKIE, '', { ...cookieOptions(0), maxAge: 0 });
  response.cookies.set(REFRESH_COOKIE, '', { ...cookieOptions(0), maxAge: 0 });
}

export function jsonError(status: number, code: string, message: string) {
  return NextResponse.json({ error_code: code, message }, {
    status, headers: { 'Cache-Control': 'no-store' },
  });
}

export async function exchangeRefresh(request: NextRequest) {
  const refresh = request.cookies.get(REFRESH_COOKIE)?.value;
  if (!refresh) return null;
  try {
    const response = await fetch(backendUrl('/auth/refresh'), {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refresh }),
      cache: 'no-store', signal: AbortSignal.timeout(8000),
    });
    if (!response.ok) return null;
    const data = await response.json();
    return typeof data.access_token === 'string' ? data.access_token : null;
  } catch {
    return null;
  }
}
