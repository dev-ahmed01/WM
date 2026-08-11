'use client';

import React, { useState } from 'react';
import { useRouter } from 'next/navigation';
import { ArrowRight, CheckCircle2, LockKeyhole, ShieldCheck, Sparkles } from 'lucide-react';
import { apiClient } from '@/lib/api-client';
import { getRoleRedirectPath, parseJwt } from '@/lib/auth';
import { Button } from '@/components/ui/button';

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const response = await apiClient<{ access_token: string; refresh_token?: string }>('/auth/login', {
        method: 'POST',
        body: JSON.stringify({ email: username, password }),
      });
      localStorage.setItem('token', response.access_token);
      if (response.refresh_token) localStorage.setItem('refresh_token', response.refresh_token);
      router.push(getRoleRedirectPath(parseJwt(response.access_token)?.role));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Invalid credentials');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main className="grid min-h-screen bg-[#0b1713] lg:grid-cols-[1.08fr_0.92fr]">
      <section className="relative hidden overflow-hidden border-r border-white/10 p-12 lg:flex lg:flex-col lg:justify-between xl:p-16">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_20%_20%,rgba(52,211,153,0.17),transparent_28rem),radial-gradient(circle_at_80%_90%,rgba(16,185,129,0.09),transparent_26rem)]" />
        <div className="relative flex items-center gap-3">
          <span className="grid h-11 w-11 place-items-center rounded-xl bg-emerald-400 text-sm font-black text-emerald-950 shadow-[0_12px_32px_rgba(52,211,153,0.2)]">WM</span>
          <div><p className="font-semibold text-white">WorkMate</p><p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500">Operations AI</p></div>
        </div>

        <div className="relative max-w-xl">
          <span className="inline-flex items-center gap-2 rounded-full border border-emerald-300/15 bg-emerald-300/[0.07] px-3 py-1.5 text-xs font-semibold text-emerald-300"><Sparkles className="h-3.5 w-3.5" />Verified operational intelligence</span>
          <h1 className="mt-6 text-4xl font-semibold leading-[1.08] tracking-[-0.045em] text-white xl:text-5xl">Every shift.<br />Every step.<br /><span className="text-emerald-300">Verified.</span></h1>
          <p className="mt-6 max-w-lg text-sm leading-7 text-slate-400">WorkMate turns published SOPs into clear, role-aware guidance without skipping workflow controls or inventing policy.</p>
          <ul className="mt-9 grid gap-4 text-sm text-slate-300 sm:grid-cols-2">
            {['One step at a time', 'Department scoped', 'Traceable sources', 'Voice enabled'].map((item) => <li key={item} className="flex items-center gap-2"><CheckCircle2 className="h-4 w-4 text-emerald-400" />{item}</li>)}
          </ul>
        </div>

        <p className="relative text-[11px] text-slate-600">Enterprise operational guidance · Secure access</p>
      </section>

      <section className="flex min-h-screen items-center justify-center bg-[#f6f9f7] px-5 py-10 sm:px-8">
        <div className="w-full max-w-md">
          <div className="mb-8 flex items-center gap-3 lg:hidden">
            <span className="grid h-10 w-10 place-items-center rounded-xl bg-[#102a22] text-xs font-black text-emerald-300">WM</span>
            <div><p className="font-semibold text-foreground">WorkMate</p><p className="text-[10px] uppercase tracking-[0.15em] text-muted-foreground">Operations AI</p></div>
          </div>
          <div className="wm-panel p-6 sm:p-8">
            <div className="grid h-11 w-11 place-items-center rounded-xl bg-emerald-50 text-emerald-700"><LockKeyhole className="h-5 w-5" /></div>
            <h2 className="mt-5 text-2xl font-semibold tracking-[-0.03em] text-foreground">Welcome back</h2>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">Sign in with your WorkMate organization account.</p>

            {error ? <div role="alert" className="mt-5 flex gap-2 rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700"><ShieldCheck className="mt-0.5 h-4 w-4 flex-none" />{error}</div> : null}

            <form onSubmit={handleSubmit} className="mt-7 space-y-5">
              <label className="block">
                <span className="wm-label">Email or username</span>
                <input type="text" required autoComplete="username" className="wm-input" value={username} onChange={(event) => setUsername(event.target.value)} placeholder="name@workmate.ai" />
              </label>
              <label className="block">
                <span className="wm-label">Password</span>
                <input type="password" required autoComplete="current-password" className="wm-input" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="Enter your password" />
              </label>
              <Button type="submit" size="lg" className="w-full" disabled={submitting}>{submitting ? 'Signing in…' : <>Sign in <ArrowRight className="h-4 w-4" /></>}</Button>
            </form>
          </div>
          <p className="mt-5 text-center text-[11px] leading-5 text-muted-foreground">Access is logged and governed by your assigned role and department.</p>
        </div>
      </section>
    </main>
  );
}
