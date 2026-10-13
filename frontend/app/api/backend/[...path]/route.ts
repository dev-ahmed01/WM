import { NextRequest, NextResponse } from 'next/server';
import {
  ACCESS_COOKIE, backendUrl, checkCsrf, clearAuthCookies,
  cookieOptions, exchangeRefresh, jsonError,
} from '@/lib/server-auth';

export const runtime = 'nodejs';

async function handler(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  if (!checkCsrf(request)) return jsonError(403, 'CSRF_DENIED', 'Invalid request origin.');
  const token = request.cookies.get(ACCESS_COOKIE)?.value;
  if (!token) return jsonError(401, 'AUTH_INVALID', 'Sign in required.');
  const { path } = await context.params;
  if (!path.length || path.some(segment => !/^[a-zA-Z0-9_\-.]+$/.test(segment) || segment === '..')) {
    return jsonError(400, 'INVALID_ROUTE', 'Unsupported API path.');
  }
  const suffix = '/' + path.join('/') + request.nextUrl.search;
  let dest: string;
  try { dest = backendUrl(suffix); } catch { return jsonError(400, 'INVALID_ROUTE', 'Unsupported API path.'); }
  // Do not forward browser-supplied authorization, host, cookies, or hop headers.
  const safeHeaders = new Headers();
  const contentType = request.headers.get('content-type');
  if (contentType) safeHeaders.set('Content-Type', contentType);
  safeHeaders.set('Authorization', `Bearer ${token}`);
  const body = ['GET', 'HEAD'].includes(request.method) ? undefined : await request.arrayBuffer();
  async function send(access: string) {
    safeHeaders.set('Authorization', `Bearer ${access}`);
    return fetch(dest, {
      method: request.method, headers: safeHeaders,
      body, cache: 'no-store', signal: AbortSignal.timeout(25000),
    });
  }
  try {
    let response = await send(token);
    let refreshed: string | null = null;
    if (response.status === 401) {
      refreshed = await exchangeRefresh(request);
      if (refreshed) response = await send(refreshed);
    }
    const reply = new NextResponse(response.body, {
      status: response.status,
      headers: {
        'Content-Type': response.headers.get('content-type') ?? 'application/octet-stream',
        'Cache-Control': 'no-store',
        'X-Content-Type-Options': 'nosniff',
      },
    });
    if (refreshed && response.ok) reply.cookies.set(ACCESS_COOKIE, refreshed, cookieOptions(60 * 60));
    if (response.status === 401) clearAuthCookies(reply);
    return reply;
  } catch {
    return jsonError(502, 'BACKEND_UNAVAILABLE', 'The backend is temporarily unavailable.');
  }
}

export { handler as GET, handler as POST, handler as PUT, handler as PATCH, handler as DELETE };
