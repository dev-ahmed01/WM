import { NextRequest, NextResponse } from 'next/server';
import { REFRESH_COOKIE, backendUrl, checkCsrf, clearAuthCookies, jsonError } from '@/lib/server-auth';

export async function POST(request: NextRequest) {
  if (!checkCsrf(request)) return jsonError(403, 'CSRF_DENIED', 'Invalid request origin.');
  const refresh = request.cookies.get(REFRESH_COOKIE)?.value;
  if (refresh) {
    // Never claim server-side sign-out when PostgreSQL revocation failed.
    try {
      const upstream = await fetch(backendUrl('/auth/revoke'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refresh }),
        cache: 'no-store', signal: AbortSignal.timeout(8000),
      });
      if (!upstream.ok) return jsonError(503, 'LOGOUT_UNAVAILABLE', 'Could not revoke the session. Retry.');
    } catch {
      return jsonError(503, 'LOGOUT_UNAVAILABLE', 'Could not revoke the session. Retry.');
    }
  }
  const reply = NextResponse.json({ signed_out: true }, { headers: { 'Cache-Control': 'no-store' } });
  clearAuthCookies(reply);
  return reply;
}
