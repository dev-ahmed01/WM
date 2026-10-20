import { NextRequest, NextResponse } from 'next/server';
import { backendUrl, checkCsrf, jsonError, setAuthCookies } from '@/lib/server-auth';

export async function POST(request: NextRequest) {
  if (!checkCsrf(request)) return jsonError(403, 'CSRF_DENIED', 'Invalid request origin.');
  try {
    const data = await request.json();
    if (typeof data.email !== 'string' || typeof data.password !== 'string') {
      return jsonError(422, 'LOGIN_INVALID', 'Email and password required.');
    }
    const upstream = await fetch(backendUrl('/auth/login'), {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: data.email, password: data.password }),
      cache: 'no-store', signal: AbortSignal.timeout(10000),
    });
    if (!upstream.ok) return jsonError(upstream.status === 401 ? 401 : 503,
      'LOGIN_FAILED', upstream.status === 401 ? 'Invalid credentials.' : 'Sign-in is unavailable.');
    const tokens = await upstream.json();
    if (typeof tokens.access_token !== 'string' || typeof tokens.refresh_token !== 'string') {
      return jsonError(502, 'LOGIN_FAILED', 'Unexpected authentication response.');
    }
    const reply = NextResponse.json({
      role: tokens.role, department_id: tokens.department_id, user_id: tokens.user_id,
    }, { headers: { 'Cache-Control': 'no-store' } });
    setAuthCookies(reply, tokens.access_token, tokens.refresh_token);
    return reply;
  } catch {
    return jsonError(503, 'LOGIN_FAILED', 'Sign-in is unavailable.');
  }
}
