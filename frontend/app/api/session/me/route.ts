import { NextRequest, NextResponse } from 'next/server';
import { ACCESS_COOKIE, backendUrl, clearAuthCookies, exchangeRefresh, jsonError, setAuthCookies } from '@/lib/server-auth';

export async function GET(request: NextRequest) {
  let token = request.cookies.get(ACCESS_COOKIE)?.value;
  let rotatedRefresh: string | undefined;
  let refreshed = false;
  try {
    // Expired access cookies disappear from the browser. A still-valid
    // HttpOnly refresh cookie must restore the short-lived access cookie.
    if (!token) {
      const next = await exchangeRefresh(request);
      if (!next) return jsonError(401, 'AUTH_INVALID', 'Sign in required.');
      token = next.access;
      rotatedRefresh = next.refresh;
      refreshed = true;
    }
    let upstream = await fetch(backendUrl('/auth/me'), {
      headers: { Authorization: `Bearer ${token}` }, cache: 'no-store',
      signal: AbortSignal.timeout(8000),
    });
    if (upstream.status === 401 && !refreshed) {
      const next = await exchangeRefresh(request);
      if (next) {
        token = next.access;
        rotatedRefresh = next.refresh;
        refreshed = true;
        upstream = await fetch(backendUrl('/auth/me'), {
          headers: { Authorization: `Bearer ${token}` }, cache: 'no-store',
          signal: AbortSignal.timeout(8000),
        });
      }
    }
    if (!upstream.ok) {
      const response = jsonError(upstream.status === 401 ? 401 : 503,
        'AUTH_INVALID', 'Account verification failed.');
      if (upstream.status === 401) clearAuthCookies(response);
      return response;
    }
    const profile = await upstream.json();
    const reply = NextResponse.json({
      sub: profile.user_id, role: profile.role, department_id: profile.department_id,
      exp: Math.floor(Date.now() / 1000) + 1800,
    }, { headers: { 'Cache-Control': 'no-store' } });
    if (refreshed && token) setAuthCookies(reply, token, rotatedRefresh);
    return reply;
  } catch {
    return jsonError(503, 'AUTH_UNAVAILABLE', 'Account verification unavailable.');
  }
}
