import { NextRequest } from 'next/server';
import { backendUrl, checkCsrf, jsonError } from '@/lib/server-auth';

// Public on purpose: an invited or recovering employee has no session yet.
// Only the one-time token and the new password are forwarded.
export async function POST(request: NextRequest) {
  if (!checkCsrf(request)) return jsonError(403, 'CSRF_DENIED', 'Invalid request origin.');
  try {
    const data = await request.json();
    if (typeof data.token !== 'string' || typeof data.password !== 'string') {
      return jsonError(422, 'REDEEM_INVALID', 'A token and a new password are required.');
    }
    const upstream = await fetch(backendUrl('/auth/token/redeem'), {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token: data.token, password: data.password }),
      cache: 'no-store', signal: AbortSignal.timeout(10000),
    });
    if (upstream.ok) return Response.json({ password_set: true }, { headers: { 'Cache-Control': 'no-store' } });
    if (upstream.status === 400) return jsonError(400, 'TOKEN_INVALID', 'This link is invalid, expired or already used.');
    if (upstream.status === 422) return jsonError(422, 'PASSWORD_REJECTED', 'Use a password of at least 12 characters.');
    if (upstream.status === 429) return jsonError(429, 'RATE_LIMITED', 'Too many attempts. Try again later.');
    return jsonError(503, 'REDEEM_FAILED', 'This could not be completed right now.');
  } catch {
    return jsonError(503, 'REDEEM_FAILED', 'This could not be completed right now.');
  }
}
