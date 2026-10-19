'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import {
  Activity, AlertTriangle, ArrowRight, ArrowUpRight, BookOpenText,
  CheckCircle2, Clock3, FileSearch, History, MessageSquareText,
  Mic2, PackageCheck, Search, ShieldCheck, Sparkles, Truck,
} from 'lucide-react';
import { useRequireRole } from '@/lib/auth';
import { apiClient, type CopilotHistoryResponse } from '@/lib/api-client';
import { LoadingState } from '@/components/shared/LoadingState';

type AnswerMode = 'workflow' | 'reference';

function copilotDraft(prompt: string, mode: AnswerMode): string {
  return '/copilot?mode=' + mode + '&draft=' + encodeURIComponent(prompt.slice(0, 500));
}

const STARTERS = [
  {
    eyebrow: '01 / INBOUND',
    title: 'Receive a shipment',
    description: 'Find the receiving SOP and walk through its checkpoints.',
    icon: Truck,
    accent: 'bg-emerald-50 text-emerald-800',
    mode: 'workflow' as AnswerMode,
    prompt: 'I am receiving an inbound shipment. Find the approved receiving SOP for my department and guide me through its first checkpoint.',
  },
  {
    eyebrow: '02 / EXCEPTION',
    title: 'Resolve a mismatch',
    description: 'Check the correct procedure before taking action.',
    icon: AlertTriangle,
    accent: 'bg-amber-50 text-amber-800',
    mode: 'workflow' as AnswerMode,
    prompt: 'The physical shipment quantity does not match the delivery paperwork. Which approved SOP applies, and what should I verify first?',
  },
  {
    eyebrow: '03 / PUTAWAY',
    title: 'Handle damaged goods',
    description: 'Surface the handling rules and decision points.',
    icon: PackageCheck,
    accent: 'bg-sky-50 text-sky-800',
    mode: 'workflow' as AnswerMode,
    prompt: 'I discovered a damaged item during putaway. Find the published procedure and guide me through the safe next steps.',
  },
  {
    eyebrow: '04 / KNOWLEDGE',
    title: 'Find a policy',
    description: 'Ask against approved documents with cited excerpts.',
    icon: FileSearch,
    accent: 'bg-violet-50 text-violet-800',
    mode: 'reference' as AnswerMode,
    prompt: 'According to the approved company documents, how should an operational incident be escalated?',
  },
];

export default function OperationsWorkspace() {
  const { user, loading } = useRequireRole(['admin', 'manager', 'employee']);
  const router = useRouter();
  const [draft, setDraft] = useState('');
  const [mode, setMode] = useState<AnswerMode>('workflow');
  const [recent, setRecent] = useState<CopilotHistoryResponse['sessions']>([]);
  const [historyError, setHistoryError] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(true);

  useEffect(() => {
    if (loading || !user) return;
    let active = true;
    void apiClient<CopilotHistoryResponse>('/copilot/history')
      .then(result => { if (active) setRecent(result.sessions ?? []); })
      .catch(() => { if (active) setHistoryError(true); })
      .finally(() => { if (active) setHistoryLoading(false); });
    return () => { active = false; };
  }, [loading, user?.sub, user?.department_id]);

  if (loading) return <LoadingState label="Opening operations desk" />;

  const resumable = recent.filter(session => session.status === 'active' || session.status === 'paused');
  const hasDraft = draft.trim().length > 0;
  const onDraftSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (hasDraft) router.push(copilotDraft(draft.trim(), mode));
  };

  return (
    <div className="wm-page max-w-[1480px] space-y-7 pb-12">
      <section className="relative overflow-hidden rounded-[2rem] bg-[#102f29] text-white shadow-xl">
        <div aria-hidden="true" className="pointer-events-none absolute -right-16 -top-36 h-[30rem] w-[30rem] rounded-full border border-white/10 bg-emerald-300/10 blur-3xl" />
        <div aria-hidden="true" className="pointer-events-none absolute bottom-[-12rem] right-[14%] h-80 w-80 rounded-full bg-teal-600/20 blur-3xl" />
        <div className="relative grid gap-10 p-7 sm:p-10 lg:grid-cols-[minmax(0,1.35fr)_minmax(18rem,0.65fr)] lg:items-end lg:px-12 lg:py-12">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full border border-emerald-200/20 bg-emerald-200/10 px-3 py-1.5 text-[11px] font-semibold tracking-wide text-emerald-100">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-300" /> WORKMATE / OPERATIONS DESK
            </div>
            <h1 className="mt-6 max-w-2xl text-4xl font-semibold leading-[1.12] tracking-[-0.045em] sm:text-5xl lg:text-[3.4rem]">
              Less searching.
              <span className="block text-[#a4efcf]">More work getting done.</span>
            </h1>
            <p className="mt-5 max-w-xl text-sm leading-7 text-emerald-50/75 sm:text-base">
              Your department’s workflows, trusted references, and open conversations — one place to start the next task.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-3">
              <Link href="/copilot" className="inline-flex items-center gap-2 rounded-xl bg-[#b4efd2] px-5 py-3 text-sm font-bold text-[#0d3326] transition hover:bg-white">
                Open Copilot <ArrowRight className="h-4 w-4" />
              </Link>
              <Link href="/copilot/sources" className="inline-flex items-center gap-2 rounded-xl border border-white/25 px-5 py-3 text-sm font-semibold text-white transition hover:bg-white/10">
                Search sources <Search className="h-4 w-4" />
              </Link>
            </div>
          </div>
          <div className="rounded-2xl border border-white/15 bg-white/[0.08] p-5 backdrop-blur-lg sm:p-6">
            <div className="flex items-center justify-between gap-3">
              <span className="text-xs font-semibold uppercase tracking-widest text-emerald-100/70">Your workspace</span>
              <ShieldCheck className="h-5 w-5 text-[#b4efd2]" />
            </div>
            <p className="mt-4 break-words text-2xl font-semibold tracking-tight capitalize">{user?.department_id || 'Department'}</p>
            <p className="mt-1 text-xs capitalize text-emerald-50/60">{user?.role || 'Employee'} access</p>
            <div className="mt-5 grid grid-cols-2 gap-3 border-t border-white/15 pt-5">
              <div><p className="text-2xl font-bold">{historyLoading ? '—' : recent.length}</p><p className="mt-0.5 text-[11px] text-emerald-50/60">Recent sessions</p></div>
              <div><p className="text-2xl font-bold">{historyLoading ? '—' : resumable.length}</p><p className="mt-0.5 text-[11px] text-emerald-50/60">Open / paused</p></div>
            </div>
            {historyError ? <p className="mt-3 text-xs text-amber-100">Session metrics are temporarily unavailable.</p> : null}
          </div>
        </div>
      </section>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.65fr)_minmax(18rem,0.85fr)]">
        <section aria-labelledby="launchpad-title">
          <div className="mb-4 flex items-end justify-between gap-3">
            <div><p className="wm-eyebrow">Task launchpad</p><h2 id="launchpad-title" className="mt-1 text-2xl font-semibold tracking-tight">Choose your next move</h2></div>
            <span className="hidden text-xs text-muted-foreground sm:block">Examples · always checked against your published sources</span>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            {STARTERS.map(starter => {
              const Icon = starter.icon;
              return (
                <Link key={starter.title} href={copilotDraft(starter.prompt, starter.mode)} className="group wm-panel relative flex min-h-[13rem] flex-col justify-between p-5 transition duration-200 hover:-translate-y-1 hover:border-emerald-300 hover:shadow-lift sm:p-6">
                  <div className="flex items-start justify-between gap-3">
                    <span className={'grid h-11 w-11 place-items-center rounded-xl ' + starter.accent}><Icon className="h-5 w-5" /></span>
                    <ArrowUpRight className="h-4 w-4 text-muted-foreground transition group-hover:text-emerald-700" />
                  </div>
                  <div className="mt-7">
                    <p className="text-[10px] font-bold tracking-[0.13em] text-emerald-700">{starter.eyebrow}</p>
                    <h3 className="mt-1.5 text-lg font-semibold tracking-tight">{starter.title}</h3>
                    <p className="mt-1.5 max-w-[18rem] text-xs leading-5 text-muted-foreground">{starter.description}</p>
                  </div>
                </Link>
              );
            })}
          </div>
        </section>

        <section aria-labelledby="compose-title" className="wm-panel flex flex-col p-5 sm:p-6">
          <div className="flex items-center gap-2 text-emerald-800"><Sparkles className="h-5 w-5" /><span className="wm-eyebrow">Ask about your work</span></div>
          <h2 id="compose-title" className="mt-3 text-xl font-semibold tracking-tight">Start with your situation.</h2>
          <p className="mt-2 text-xs leading-6 text-muted-foreground">You provide the context. WorkMate looks for a published workflow or an approved source before it answers.</p>
          <form className="mt-5 flex flex-1 flex-col" onSubmit={onDraftSubmit}>
            <label htmlFor="task-draft" className="mb-2 text-xs font-semibold text-foreground">What do you need to do?</label>
            <textarea id="task-draft" maxLength={500} rows={5} value={draft} onChange={event => setDraft(event.target.value)} placeholder="Example: I found an item without a matching purchase order…" className="wm-input min-h-32 resize-y leading-6" />
            <div className="mt-4 grid grid-cols-2 gap-2 rounded-xl bg-muted p-1" role="group" aria-label="Guidance mode">
              <button type="button" aria-pressed={mode === 'workflow'} onClick={() => setMode('workflow')} className={mode === 'workflow' ? 'rounded-lg bg-white px-3 py-2.5 text-xs font-semibold text-emerald-900 shadow-sm' : 'rounded-lg px-3 py-2.5 text-xs font-semibold text-muted-foreground hover:text-foreground'}><Activity className="mr-1.5 inline h-3.5 w-3.5" />Workflow</button>
              <button type="button" aria-pressed={mode === 'reference'} onClick={() => setMode('reference')} className={mode === 'reference' ? 'rounded-lg bg-white px-3 py-2.5 text-xs font-semibold text-emerald-900 shadow-sm' : 'rounded-lg px-3 py-2.5 text-xs font-semibold text-muted-foreground hover:text-foreground'}><BookOpenText className="mr-1.5 inline h-3.5 w-3.5" />Reference</button>
            </div>
            <button type="submit" disabled={!hasDraft} className="mt-5 inline-flex w-full items-center justify-center gap-2 rounded-xl bg-[#165a45] px-4 py-3 text-sm font-semibold text-white transition hover:bg-[#0d3d30] disabled:cursor-not-allowed disabled:opacity-50">
              Prepare in Copilot <ArrowRight className="h-4 w-4" />
            </button>
            <p className="mt-3 text-center text-[11px] text-muted-foreground">Review and send the draft yourself. No task is started automatically.</p>
          </form>
        </section>
      </div>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.65fr)_minmax(18rem,0.85fr)]">
        <section className="wm-panel overflow-hidden" aria-labelledby="continuity-title">
          <div className="flex items-center justify-between gap-4 border-b border-border px-5 py-4 sm:px-6">
            <div className="flex items-center gap-3"><span className="grid h-9 w-9 place-items-center rounded-xl bg-emerald-50 text-emerald-700"><History className="h-4 w-4" /></span><div><h2 id="continuity-title" className="text-sm font-semibold">Pick up where you left off</h2><p className="mt-0.5 text-[11px] text-muted-foreground">Recent conversations, from your account</p></div></div>
            <Link href="/copilot/history" className="inline-flex items-center gap-1 text-xs font-semibold text-emerald-700 hover:underline">All history <ArrowRight className="h-3.5 w-3.5" /></Link>
          </div>
          {historyLoading ? <p className="p-6 text-xs text-muted-foreground" role="status">Loading your sessions…</p>
            : historyError ? <p className="p-6 text-xs text-muted-foreground">Sessions could not be loaded. You can still start a new task.</p>
            : recent.length === 0 ? <div className="flex items-center gap-3 p-6"><MessageSquareText className="h-5 w-5 text-emerald-600" /><p className="text-xs text-muted-foreground">Your first Copilot conversation will appear here.</p></div>
            : <div className="divide-y divide-border/70">
                {recent.slice(0, 3).map(session => (
                  <Link key={session.id} href={'/copilot?session=' + encodeURIComponent(session.id)} className="group flex items-center gap-3 px-5 py-4 transition hover:bg-emerald-50/50 sm:px-6">
                    <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-muted text-muted-foreground"><Clock3 className="h-4 w-4" /></span>
                    <div className="min-w-0 flex-1"><p className="truncate text-xs font-semibold">{session.title || 'Operational conversation'}</p><p className="mt-1 truncate text-[11px] text-muted-foreground">{session.last_message_preview || 'Continue with your prior context'}</p></div>
                    <span className="hidden rounded-md bg-muted px-2 py-1 text-[10px] font-medium capitalize text-muted-foreground sm:inline">{session.status || 'session'}</span>
                    <ArrowUpRight className="h-4 w-4 shrink-0 text-muted-foreground group-hover:text-emerald-700" />
                  </Link>
                ))}
              </div>}
        </section>
        <section className="wm-panel p-5 sm:p-6" aria-labelledby="trust-title">
          <div className="flex items-center gap-2 text-emerald-700"><ShieldCheck className="h-5 w-5" /><p className="wm-eyebrow">Built for accountable work</p></div>
          <h2 id="trust-title" className="mt-3 text-lg font-semibold tracking-tight">Guidance you can check.</h2>
          <div className="mt-5 space-y-4">
            <div className="flex items-start gap-3"><CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-700" /><div><p className="text-xs font-semibold">Published procedures</p><p className="mt-1 text-[11px] leading-5 text-muted-foreground">Workflow steps stay tied to active SOP versions.</p></div></div>
            <div className="flex items-start gap-3"><FileSearch className="mt-0.5 h-4 w-4 shrink-0 text-emerald-700" /><div><p className="text-xs font-semibold">Inspectable sources</p><p className="mt-1 text-[11px] leading-5 text-muted-foreground">View citations and export an evidence note from answers.</p></div></div>
            <div className="flex items-start gap-3"><Mic2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-700" /><div><p className="text-xs font-semibold">Voice with confirmation</p><p className="mt-1 text-[11px] leading-5 text-muted-foreground">Check the transcript before sending anything.</p></div></div>
          </div>
          <Link href="/copilot/sources" className="mt-6 inline-flex items-center gap-2 text-xs font-semibold text-emerald-700 hover:underline">Explore approved evidence <ArrowRight className="h-4 w-4" /></Link>
        </section>
      </div>
    </div>
  );
}
