'use client';

import React, { Suspense, useState } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { CircleCheck, KeyRound, ShieldCheck } from 'lucide-react';
import { Button } from '@/components/ui/button';

function AcceptInviteForm() {
  const token = useSearchParams().get('token') ?? '';
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState('');
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError('');
    if (password.length < 12) return setError('Use at least 12 characters.');
    if (password !== confirm) return setError('The two passwords do not match.');
    setBusy(true);
    try {
      const res = await fetch('/api/session/redeem', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token, password }),
      });
      if (res.ok) setDone(true);
      else setError((await res.json().catch(() => null))?.message ?? 'This could not be completed.');
    } catch {
      setError('Could not reach the server. Check your connection and try again.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="grid min-h-screen place-items-center bg-background px-4 py-10">
      <div className="wm-panel w-full max-w-md p-6 sm:p-8">
        <div className="grid h-11 w-11 place-items-center rounded-xl bg-emerald-50 text-emerald-700">
          {done ? <CircleCheck className="h-5 w-5" /> : <KeyRound className="h-5 w-5" />}
        </div>
        <h1 className="mt-5 text-2xl font-semibold tracking-[-0.03em]">{done ? 'Password set' : 'Set your password'}</h1>
        {done ? (
          <>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">Your account is ready. Sign in with your email and the new password.</p>
            <Link href="/login" className="mt-6 inline-flex"><Button size="lg">Go to sign in</Button></Link>
          </>
        ) : !token ? (
          <p role="alert" className="mt-4 rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">This link has no token. Ask your administrator for a new one.</p>
        ) : (
          <>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">Choose a password with at least 12 characters. This link works once.</p>
            {error ? <div role="alert" className="mt-5 flex gap-2 rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700"><ShieldCheck className="mt-0.5 h-4 w-4 flex-none" />{error}</div> : null}
            <form onSubmit={submit} className="mt-6 space-y-5">
              <label className="block"><span className="wm-label">New password</span>
                <input type="password" required minLength={12} autoComplete="new-password" className="wm-input" value={password} onChange={(e) => setPassword(e.target.value)} /></label>
              <label className="block"><span className="wm-label">Confirm password</span>
                <input type="password" required minLength={12} autoComplete="new-password" className="wm-input" value={confirm} onChange={(e) => setConfirm(e.target.value)} /></label>
              <Button type="submit" size="lg" className="w-full" disabled={busy}>{busy ? 'Saving…' : 'Save password'}</Button>
            </form>
          </>
        )}
      </div>
    </main>
  );
}

export default function AcceptInvitePage() {
  return <Suspense fallback={null}><AcceptInviteForm /></Suspense>;
}
