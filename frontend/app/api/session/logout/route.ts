import { NextRequest, NextResponse } from 'next/server';
import { checkCsrf, clearAuthCookies, jsonError } from '@/lib/server-auth';
export async function POST(request: NextRequest) {
  if (!checkCsrf(request)) return jsonError(403, 'CSRF_DENIED', 'Invalid request origin.');
  const reply = NextResponse.json({ signed_out: true }, { headers: { 'Cache-Control': 'no-store' } });
  clearAuthCookies(reply);
  return reply;
}
