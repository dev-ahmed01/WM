import { NextRequest, NextResponse } from 'next/server';
import {
  ACCESS_COOKIE, backendUrl, checkCsrf, clearAuthCookies,
  cookieOptions, exchangeRefresh, jsonError, setAuthCookies,
} from '@/lib/server-auth';

export const runtime = 'nodejs';

async function handler(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  if (!checkCsrf(request)) return jsonError(403, 'CSRF_DENIED', 'Invalid request origin.');
  let token = request.cookies.get(ACCESS_COOKIE)?.value;
  let refreshed: { access: string; refresh?: string } | null = null;
  if (!token) {
    refreshed = await exchangeRefresh(request);
    if (!refreshed) return jsonError(401, 'AUTH_INVALID', 'Sign in required.');
    token = refreshed.access;
  }
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
  const maxBodyBytes = 26 * 1024 * 1024;
  const declaredSize = Number(request.headers.get('content-length') || 0);
  if (!Number.isFinite(declaredSize) || declaredSize > maxBodyBytes) {
    return jsonError(413, 'BODY_TOO_LARGE', 'Upload exceeds the 26 MB proxy limit.');
  }
  const body = ['GET', 'HEAD'].includes(request.method) ? undefined : await request.arrayBuffer();
  if (body && body.byteLength > maxBodyBytes) {
    return jsonError(413, 'BODY_TOO_LARGE', 'Upload exceeds the 26 MB proxy limit.');
  }
  // Local CPU inference can exceed the normal API timeout. Keep bounded long
  // requests exclusive to Copilot, rather than timing out unrelated operations.
  const isInference = path[0] === 'copilot' && (path[1] === 'message' || path[1] === 'voice');
  const requestTimeoutMs = isInference ? 120000 : 25000;
  async function send(access: string) {
    safeHeaders.set('Authorization', `Bearer ${access}`);
    return fetch(dest, {
      method: request.method, headers: safeHeaders,
      body, cache: 'no-store', signal: AbortSignal.timeout(requestTimeoutMs),
    });
  }
  try {
    let response = await send(token);
    if (response.status === 401 && !refreshed) {
      refreshed = await exchangeRefresh(request);
      if (refreshed) response = await send(refreshed.access);
    }
    const reply = new NextResponse(response.body, {
      status: response.status,
      headers: {
        'Content-Type': response.headers.get('content-type') ?? 'application/octet-stream',
        'Cache-Control': 'no-store',
        'X-Content-Type-Options': 'nosniff',
      },
    });
    if (refreshed && response.ok) setAuthCookies(reply, refreshed.access, refreshed.refresh);
    if (response.status === 401) clearAuthCookies(reply);
    return reply;
  } catch (error) {
    const name = error instanceof Error ? error.name : 'UnknownError';
    // Never log cookies, authorization headers, request bodies or SOP text.
    console.error('WorkMate backend proxy failure', { route: path[0], kind: name });
    if (name === 'TimeoutError' || name === 'AbortError') {
      return jsonError(504, 'BACKEND_TIMEOUT', isInference
        ? 'Copilot response timed out. Check the local model and retry.'
        : 'The backend request timed out. Please retry.');
    }
    return jsonError(502, 'BACKEND_UNAVAILABLE', 'Unable to connect to the WorkMate API. Check backend status.');
  }
}

export { handler as GET, handler as POST, handler as PUT, handler as PATCH, handler as DELETE };
