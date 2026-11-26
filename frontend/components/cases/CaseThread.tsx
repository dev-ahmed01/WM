'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { apiClient } from '@/lib/api-client';
import { ErrorNote, StatusPill, buttonPrimary, buttonQuiet, inputClass, relativeDate } from '@/components/shared/ui';

export interface CaseSummary {
  id: string; kind: string; title: string; question: string; status: string; public_status: string; priority: string;
  department_id: string; reporter_name?: string; assignee_name?: string | null; assigned_to?: string | null;
  escalated_to_manager: boolean; draft_id?: string | null; created_at: string; updated_at: string; latest_reply?: string | null;
  messages?: number;
}
interface ThreadMessage { id: string; kind: 'message' | 'context' | 'event'; body: string; internal: boolean; author_role: string; author: string; created_at: string }
interface CaseDetail extends CaseSummary { thread: ThreadMessage[] }
interface Person { id: string; name: string; role: string }

const KIND_LABEL: Record<string, string> = { human_request: 'Asked for a person', unanswered: 'No approved answer', incorrect_answer: 'Answer marked not helpful' };

function Bubble({ m, mine }: { m: ThreadMessage; mine: boolean }) {
  if (m.kind === 'context') {
    return (
      <details className="rounded-lg border border-border bg-muted/40 px-3 py-2 text-sm">
        <summary className="cursor-pointer text-xs font-medium text-muted-foreground">Conversation shared with this request</summary>
        <p className="mt-2 whitespace-pre-wrap text-muted-foreground">{m.body}</p>
      </details>
    );
  }
  return (
    <div className={mine ? 'flex flex-col items-end' : 'flex flex-col items-start'}>
      <div className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-sm leading-6 ${m.internal ? 'border border-dashed border-amber-300 bg-amber-50 text-amber-950' : mine ? 'bg-primary text-primary-foreground' : 'bg-muted text-foreground'}`}>
        {m.internal ? <p className="mb-0.5 text-[11px] font-medium uppercase tracking-wide">Internal note</p> : null}
        <p className="whitespace-pre-wrap break-words">{m.body}</p>
      </div>
      <p className="mt-1 px-1 text-[11px] text-muted-foreground">{m.author} · {relativeDate(m.created_at)}</p>
    </div>
  );
}

export function CaseThread({ caseId, mode, onChanged, onProposeKnowledge }: {
  caseId: string; mode: 'employee' | 'staff'; onChanged?: () => void; onProposeKnowledge?: (c: CaseDetail) => void;
}) {
  const staff = mode === 'staff';
  const base = staff ? '/cases' : '/my/cases';
  const [data, setData] = useState<CaseDetail | null>(null);
  const [people, setPeople] = useState<Person[]>([]);
  const [text, setText] = useState('');
  const [internal, setInternal] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try { setData(await apiClient<CaseDetail>(`${base}/${caseId}`)); setError(null); }
    catch { setError('Could not open this request.'); }
  }, [base, caseId]);

  useEffect(() => { setData(null); setText(''); setInternal(false); void load(); }, [load]);
  useEffect(() => { if (staff) void apiClient<{ items: Person[] }>('/cases/people').then((r) => setPeople(r.items)).catch(() => setPeople([])); }, [staff]);

  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true); setError(null);
    try { await fn(); await load(); onChanged?.(); }
    catch (e) { setError(e instanceof Error && e.message ? e.message : 'That did not work. Please try again.'); }
    finally { setBusy(false); }
  };
  const post = (path: string, body?: unknown) => apiClient(`${base}/${caseId}/${path}`, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) });

  if (!data) return error ? <ErrorNote>{error}</ErrorNote> : <p className="p-6 text-sm text-muted-foreground">Loading…</p>;
  const closed = ['closed', 'dismissed'].includes(data.status);
  const resolved = data.public_status === 'resolved';
  const myRole = staff ? null : 'employee';

  return (
    <section className="flex h-full min-h-0 flex-col" aria-label="Request details">
      <header className="space-y-2 border-b border-border px-4 py-4 sm:px-6">
        <div className="flex flex-wrap items-center gap-2">
          <StatusPill status={data.public_status} />
          {data.priority !== 'normal' ? <StatusPill status={data.priority} /> : null}
          {data.escalated_to_manager ? <span className="rounded-full border border-border px-2 py-0.5 text-xs text-muted-foreground">With manager</span> : null}
          <span className="text-xs text-muted-foreground">{KIND_LABEL[data.kind] ?? data.kind}</span>
        </div>
        <h2 className="font-display text-lg font-semibold leading-snug">{data.title}</h2>
        <p className="text-xs text-muted-foreground">
          {staff ? <>From {data.reporter_name ?? 'an employee'} · </> : null}
          Opened {relativeDate(data.created_at)}{data.assignee_name ? <> · Assigned to {data.assignee_name}</> : staff ? ' · Not assigned' : ' · Waiting for someone to pick it up'}
        </p>

        {staff && !closed ? (
          <div className="flex flex-wrap items-center gap-2 pt-1">
            <label className="sr-only" htmlFor="assignee">Assign to</label>
            <select id="assignee" className={`${inputClass} !h-9 !w-auto min-w-40`} value={data.assigned_to ?? ''} disabled={busy}
              onChange={(e) => void run(() => post('assign', { assignee_id: e.target.value || null }))}>
              <option value="">Unassigned</option>
              {people.map((p) => <option key={p.id} value={p.id}>{p.name} ({p.role})</option>)}
            </select>
            <label className="sr-only" htmlFor="priority">Priority</label>
            <select id="priority" className={`${inputClass} !h-9 !w-auto`} value={data.priority} disabled={busy}
              onChange={(e) => void run(() => post('flags', { priority: e.target.value }))}>
              {['low', 'normal', 'high', 'urgent'].map((p) => <option key={p} value={p}>{p[0].toUpperCase() + p.slice(1)}</option>)}
            </select>
            <button type="button" className={`${buttonQuiet} !h-9`} disabled={busy} onClick={() => void run(() => post('flags', { escalate_to_manager: !data.escalated_to_manager }))}>
              {data.escalated_to_manager ? 'Take back from manager' : 'Escalate to manager'}
            </button>
            {data.kind === 'unanswered' && onProposeKnowledge && !data.draft_id ? (
              <button type="button" className={`${buttonQuiet} !h-9`} onClick={() => onProposeKnowledge(data)}>Propose an SOP</button>
            ) : null}
            {data.draft_id ? <span className="text-xs text-muted-foreground">An SOP draft exists for this question</span> : null}
          </div>
        ) : null}
      </header>

      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-4 py-5 sm:px-6" aria-live="polite">
        {data.thread.length === 0 ? <p className="text-sm text-muted-foreground">{staff ? 'No messages yet. Reply to the employee below.' : 'Your supervisor has not replied yet. You will see the answer here.'}</p> : null}
        {data.thread.map((m) => <Bubble key={m.id} m={m} mine={staff ? m.author_role !== 'employee' : m.author_role === myRole} />)}
      </div>

      <footer className="space-y-2 border-t border-border px-4 py-3 sm:px-6">
        {error ? <ErrorNote>{error}</ErrorNote> : null}
        {closed ? <p className="text-sm text-muted-foreground">This request is closed.</p> : (
          <>
            {!staff && resolved ? (
              <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-900">
                <span>Marked as resolved. Did that solve it?</span>
                <button type="button" className={buttonPrimary} disabled={busy} onClick={() => void run(() => post('acknowledge'))}>Yes, close it</button>
              </div>
            ) : null}
            <label className="sr-only" htmlFor="case-reply">{staff ? 'Reply' : 'Add more information'}</label>
            <textarea id="case-reply" value={text} onChange={(e) => setText(e.target.value)} rows={2} maxLength={2000}
              placeholder={staff ? (internal ? 'Write an internal note (the employee will not see it)…' : 'Reply to the employee…') : (resolved ? 'Not solved? Tell us what is still wrong…' : 'Add more information…')}
              className="w-full resize-none rounded-lg border border-input bg-card px-3 py-2 text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/15" />
            <div className="flex flex-wrap items-center justify-between gap-2">
              {staff ? (
                <label className="flex items-center gap-2 text-sm text-muted-foreground">
                  <input type="checkbox" checked={internal} onChange={(e) => setInternal(e.target.checked)} className="h-4 w-4 accent-[hsl(var(--primary))]" /> Internal note
                </label>
              ) : <span />}
              <div className="flex gap-2">
                {staff ? <button type="button" className={buttonQuiet} disabled={busy} onClick={() => void run(async () => { await post('resolve', { note: text.trim() }); setText(''); })}>Resolve{text.trim() ? ' with message' : ''}</button> : null}
                <button type="button" className={buttonPrimary} disabled={busy || !text.trim()}
                  onClick={() => void run(async () => { await post('messages', staff ? { body: text.trim(), internal } : { body: text.trim() }); setText(''); })}>
                  {staff ? (internal ? 'Add note' : 'Send reply') : 'Send'}
                </button>
              </div>
            </div>
          </>
        )}
      </footer>
    </section>
  );
}
