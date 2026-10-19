'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { AlertTriangle, ArrowLeft, ArrowRight, CheckCircle2, ClipboardCheck, Clock3, ListChecks, ShieldCheck } from 'lucide-react';
import { useRequireRole } from '@/lib/auth';
import { apiClient } from '@/lib/api-client';
import { LoadingState } from '@/components/shared/LoadingState';

type Handover = {
  id: string;
  conversation_id: string;
  created_by: string;
  department_id: string;
  recipient_label: string;
  next_action: string;
  notes: string;
  disposition: string;
  exception_type: string;
  severity: 'normal' | 'high' | 'critical';
  snapshot_state: { workflow_status?: string | null; step_title?: string | null };
  status: 'submitted' | 'acknowledged' | 'follow_up_requested';
  reviewed_by: string | null;
  review_note: string | null;
  created_at: string;
};

const issueLabel = (value: string) => value.replaceAll('_', ' ');

function ReviewCard({ item, userId, onReviewed }: {
  item: Handover; userId: string;
  onReviewed: (item: Handover) => void;
}) {
  const [note, setNote] = useState('');
  const [working, setWorking] = useState(false);
  const [error, setError] = useState('');
  const pending = item.status === 'submitted';
  const canReview = pending && item.created_by !== userId;

  async function decide(decision: 'acknowledged' | 'follow_up_requested') {
    if (!canReview || note.trim().length < 8) return;
    setWorking(true);
    setError('');
    try {
      const record = await apiClient<Handover>('/handover/' + encodeURIComponent(item.id) + '/review', {
        method: 'POST', body: JSON.stringify({ decision, review_note: note.trim() }),
      });
      onReviewed(record);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Review could not be saved.');
    } finally {
      setWorking(false);
    }
  }

  return (
    <article className="wm-panel overflow-hidden">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-border bg-white px-5 py-4 sm:px-6">
        <div>
          <p className="text-[10px] font-bold uppercase tracking-widest text-emerald-700">{item.recipient_label}</p>
          <h3 className="mt-1.5 text-base font-semibold tracking-tight capitalize">{issueLabel(item.exception_type === 'none' ? item.disposition : item.exception_type)}</h3>
          <p className="mt-1 text-[11px] text-muted-foreground">Prepared by {item.created_by} · {new Date(item.created_at).toLocaleString()}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className={'rounded-lg px-2.5 py-1.5 text-[11px] font-semibold capitalize ' + (item.severity === 'critical' ? 'bg-red-50 text-red-800' : item.severity === 'high' ? 'bg-amber-50 text-amber-800' : 'bg-slate-100 text-slate-700')}>{item.severity}</span>
          <span className={'rounded-lg px-2.5 py-1.5 text-[11px] font-semibold capitalize ' + (pending ? 'bg-emerald-50 text-emerald-800' : 'bg-slate-100 text-slate-600')}>{issueLabel(item.status)}</span>
        </div>
      </div>
      <div className="space-y-4 p-5 sm:p-6">
        <div className="grid gap-3 rounded-xl border border-border bg-muted/40 p-4 sm:grid-cols-2">
          <div><p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Saved workflow status</p><p className="mt-1 text-xs font-semibold capitalize">{item.snapshot_state?.workflow_status || 'No active workflow'}</p></div>
          <div><p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Recorded step</p><p className="mt-1 text-xs font-semibold">{item.snapshot_state?.step_title || 'Not recorded'}</p></div>
        </div>
        {item.severity !== 'normal' ? <div className="flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs leading-5 text-amber-950"><AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" /><span>High-priority handover. An acknowledgment records receipt only; it does not authorize unsafe work or resolve the exception.</span></div> : null}
        <div><p className="wm-label">Requested next action</p><p className="whitespace-pre-wrap break-words text-sm leading-7">{item.next_action}</p></div>
        {item.notes ? <div><p className="wm-label">Operator context</p><p className="whitespace-pre-wrap break-words text-xs leading-6 text-muted-foreground">{item.notes}</p></div> : null}
        <Link href={'/copilot?session=' + encodeURIComponent(item.conversation_id)} className="inline-flex items-center gap-2 text-xs font-semibold text-emerald-700 hover:underline">Open associated session <ArrowRight className="h-3.5 w-3.5" /></Link>
        {canReview ? (
          <div className="border-t border-border pt-4">
            <label className="wm-label" htmlFor={'review-' + item.id}>Reviewer note (required)</label>
            <textarea id={'review-' + item.id} className="wm-input min-h-24" maxLength={1000} rows={2}
              placeholder="Record the follow-up, owner coordination, or acknowledgment details…"
              value={note} onChange={event => setNote(event.target.value)} />
            {error ? <p className="mt-2 text-xs text-red-700" role="alert">{error}</p> : null}
            <div className="mt-3 flex flex-wrap gap-2">
              <button type="button" disabled={working || note.trim().length < 8} onClick={() => void decide('acknowledged')}
                className="inline-flex items-center gap-2 rounded-xl bg-emerald-700 px-4 py-2.5 text-xs font-semibold text-white hover:bg-emerald-800 disabled:opacity-50"><CheckCircle2 className="h-4 w-4" />Acknowledge receipt</button>
              <button type="button" disabled={working || note.trim().length < 8} onClick={() => void decide('follow_up_requested')}
                className="inline-flex items-center gap-2 rounded-xl border border-border px-4 py-2.5 text-xs font-semibold hover:bg-muted disabled:opacity-50"><ListChecks className="h-4 w-4" />Request follow-up</button>
            </div>
          </div>
        ) : item.status !== 'submitted' ? (
          <div className="border-t border-border pt-4 text-xs leading-6 text-muted-foreground">Reviewed by {item.reviewed_by} · {item.review_note}</div>
        ) : <p className="text-xs text-muted-foreground">Your own handover must be reviewed by another manager or administrator.</p>}
      </div>
    </article>
  );
}

export default function HandoverReviewPage() {
  const { user, loading } = useRequireRole(['admin', 'manager']);
  const [items, setItems] = useState<Handover[]>([]);
  const [pending, setPending] = useState(true);
  const [error, setError] = useState('');
  const [showAll, setShowAll] = useState(false);
  const fetchQueue = useCallback(async () => {
    setPending(true);
    setError('');
    try {
      const result = await apiClient<{items: Handover[]}>('/handover?limit=100');
      setItems(result.items || []);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Handover queue unavailable.');
    } finally {
      setPending(false);
    }
  }, []);

  useEffect(() => {
    if (!user || loading) return;
    void fetchQueue();
  }, [loading, user?.sub, user?.department_id, fetchQueue]);
  const waiting = useMemo(() => items.filter(item => item.status === 'submitted'), [items]);
  const urgent = waiting.filter(item => item.severity !== 'normal').length;
  const visible = showAll ? items : waiting;
  if (loading) return <LoadingState label="Opening handover review" />;
  return (
    <div className="wm-page max-w-6xl space-y-7 pb-12">
      <Link href="/workspace" className="inline-flex items-center gap-2 text-xs font-semibold text-muted-foreground hover:text-emerald-700"><ArrowLeft className="h-4 w-4" />Operations desk</Link>
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div><p className="wm-eyebrow">Department review</p><h1 className="mt-2 text-3xl font-semibold tracking-tight sm:text-4xl">Shift handover queue</h1><p className="mt-2 text-sm text-muted-foreground">Acknowledge the next action and flag work needing supervisor follow-up. No workflow changes happen here.</p></div>
        <button type="button" className="rounded-xl border border-border bg-white px-4 py-2.5 text-xs font-semibold hover:bg-muted" onClick={() => void fetchQueue()}>Refresh queue</button>
      </header>
      <div className="grid gap-3 sm:grid-cols-3">
        <div className="wm-panel p-5"><p className="text-xs text-muted-foreground">Awaiting review</p><p className="mt-2 text-3xl font-bold">{pending ? '—' : waiting.length}</p></div>
        <div className="wm-panel p-5"><p className="text-xs text-muted-foreground">High / critical in queue</p><p className="mt-2 text-3xl font-bold">{pending ? '—' : urgent}</p></div>
        <div className="wm-panel p-5"><p className="text-xs text-muted-foreground">Reviewed in loaded results</p><p className="mt-2 text-3xl font-bold">{pending ? '—' : items.length - waiting.length}</p></div>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2"><ClipboardCheck className="h-4 w-4 text-emerald-700" /><h2 className="text-sm font-semibold">{showAll ? 'Recent department handovers' : 'Needs reviewer action'}</h2></div>
        <button type="button" onClick={() => setShowAll(value => !value)} className="rounded-lg border border-border px-3 py-2 text-xs font-semibold hover:bg-muted">{showAll ? 'Show pending' : 'Show all'}</button>
      </div>
      {error ? <p role="alert" className="rounded-xl bg-red-50 p-4 text-sm text-red-700">{error}</p> : null}
      {pending ? <LoadingState label="Checking saved department handovers" /> :
        visible.length ? <div className="grid gap-4">{visible.map(item =>
          <ReviewCard key={item.id} item={item} userId={user?.sub || ''}
            onReviewed={updated => setItems(current => current.map(original => original.id === updated.id ? updated : original))} />)}
        </div> : <div className="wm-panel p-10 text-center"><Clock3 className="mx-auto h-7 w-7 text-emerald-700" /><h3 className="mt-3 text-sm font-semibold">No handovers in this view</h3><p className="mt-1 text-xs text-muted-foreground">Submitted records appear when an employee chooses Submit for review.</p></div>}
      <div className="flex items-start gap-2 text-xs leading-6 text-muted-foreground"><ShieldCheck className="mt-1 h-4 w-4 shrink-0 text-emerald-700" /><p>Only your department's handovers are listed. All submissions and review actions are stored with a separate audit event; acknowledgment never validates SOP compliance.</p></div>
    </div>
  );
}
