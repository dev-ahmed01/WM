'use client';

import React, { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { ArrowLeft, Search } from 'lucide-react';
import { apiClient } from '@/lib/api-client';
import { CaseThread, type CaseSummary } from '@/components/cases/CaseThread';
import { EmptyState, ErrorNote, StatusPill, Tabs, buttonPrimary, buttonQuiet, inputClass, relativeDate } from '@/components/shared/ui';

type View = 'all' | 'escalated' | 'unanswered' | 'resolved';
interface Counts { all: number; escalated: number; unanswered: number; resolved: number; manager_open: number }
const KIND: Record<string, string> = { human_request: 'Asked for a person', unanswered: 'No approved answer', incorrect_answer: 'Marked not helpful' };

function ProposeSop({ item, onClose, onDone }: { item: CaseSummary; onClose: () => void; onDone: () => void }) {
  const [title, setTitle] = useState(item.title.slice(0, 120));
  const [steps, setSteps] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const submit = async () => {
    setBusy(true); setError(null);
    try {
      await apiClient(`/knowledge-gaps/${item.id}/draft`, { method: 'POST', body: JSON.stringify({ title: title.trim(), steps: steps.split('\n').map((s) => s.trim()).filter(Boolean) }) });
      setDone(true); onDone();
    } catch (e) { setError(e instanceof Error && e.message ? e.message : 'Could not create the draft.'); }
    finally { setBusy(false); }
  };
  return (
    <div role="dialog" aria-modal="true" aria-label="Propose an SOP" className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4">
      <div className="w-full max-w-lg space-y-3 rounded-2xl bg-card p-5 shadow-xl">
        <h2 className="font-display text-lg font-semibold">Propose an SOP</h2>
        {done ? (
          <>
            <p className="text-sm">Draft created. It is not live: it must be reviewed in Knowledge Studio and approved by a manager first.</p>
            <div className="flex justify-end gap-2"><Link href="/knowledge-studio" className={buttonPrimary}>Open Knowledge Studio</Link><button type="button" className={buttonQuiet} onClick={onClose}>Close</button></div>
          </>
        ) : (
          <>
            <p className="text-sm text-muted-foreground">Write the steps you know to be correct, one per line. This only creates a draft for review; the reply to the employee is separate.</p>
            <input value={title} onChange={(e) => setTitle(e.target.value)} aria-label="SOP title" className={inputClass} minLength={5} maxLength={180} />
            <textarea value={steps} onChange={(e) => setSteps(e.target.value)} rows={6} aria-label="Steps, one per line" placeholder={'Scan the pallet label\nCount the cartons\n…'}
              className="w-full resize-none rounded-lg border border-input bg-card px-3 py-2 text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/15" />
            {error ? <ErrorNote>{error}</ErrorNote> : null}
            <div className="flex justify-end gap-2">
              <button type="button" className={buttonQuiet} onClick={onClose}>Cancel</button>
              <button type="button" className={buttonPrimary} disabled={busy || title.trim().length < 5 || !steps.trim()} onClick={() => void submit()}>{busy ? 'Creating…' : 'Create draft'}</button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

/** List-and-detail case management for admins (Conversations) and managers (Requests in the escalation centre). */
export function StaffCases({ managed = false }: { managed?: boolean }) {
  const [view, setView] = useState<View>(managed ? 'escalated' : 'all');
  const [q, setQ] = useState('');
  const [priority, setPriority] = useState('');
  const [items, setItems] = useState<CaseSummary[] | null>(null);
  const [counts, setCounts] = useState<Counts | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [propose, setPropose] = useState<CaseSummary | null>(null);

  const load = useCallback(async () => {
    try {
      const qs = new URLSearchParams({ view: managed ? 'all' : view, q: q.trim() });
      if (managed) qs.set('managed', 'true');
      if (priority) qs.set('priority', priority);
      const r = await apiClient<{ items: CaseSummary[]; counts: Counts }>(`/cases?${qs}`);
      setItems(r.items); setCounts(r.counts); setError(null);
    } catch { setError('Could not load requests.'); setItems([]); }
  }, [view, q, priority, managed]);

  useEffect(() => { const t = setTimeout(() => void load(), q ? 250 : 0); return () => clearTimeout(t); }, [load, q]);
  useEffect(() => { setSelected(null); }, [view]);

  const tabs = managed ? [] : [
    { id: 'all', label: 'All conversations', count: counts?.all },
    { id: 'escalated', label: 'Escalated', count: counts?.escalated },
    { id: 'unanswered', label: 'Unanswered', count: counts?.unanswered },
    { id: 'resolved', label: 'Resolved', count: counts?.resolved },
  ];

  return (
    <div className="flex h-full min-h-0 flex-col">
      {!managed ? <div className="px-4 sm:px-6 lg:px-8"><Tabs tabs={tabs} value={view} onChange={(v) => setView(v as View)} label="Conversation filters" /></div> : null}
      <div className="grid min-h-0 flex-1 lg:grid-cols-[24rem_minmax(0,1fr)]">
        <div className={`${selected ? 'hidden lg:flex' : 'flex'} min-h-0 flex-col border-border lg:border-r`}>
          <div className="flex gap-2 px-4 py-3 sm:px-6 lg:px-4">
            <div className="relative min-w-0 flex-1">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
              <input value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search" placeholder="Search" className={`${inputClass} pl-9`} />
            </div>
            <select value={priority} onChange={(e) => setPriority(e.target.value)} aria-label="Priority" className={`${inputClass} !w-auto`}>
              <option value="">Any priority</option><option value="urgent">Urgent</option><option value="high">High</option><option value="normal">Normal</option><option value="low">Low</option>
            </select>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-6">
            {error ? <div className="px-2"><ErrorNote>{error}</ErrorNote></div> : null}
            {items === null ? <p className="px-4 text-sm text-muted-foreground">Loading…</p> : items.length === 0 ? (
              <div className="px-2"><EmptyState title="Nothing to show" hint={managed ? 'Requests escalated to a manager, and urgent ones, appear here.' : 'Try another filter.'} /></div>
            ) : (
              <ul className="divide-y divide-border" aria-label="Requests">
                {items.map((c) => (
                  <li key={c.id}>
                    <button type="button" onClick={() => setSelected(c.id)} aria-current={selected === c.id}
                      className={`block w-full rounded-lg px-3 py-3 text-left transition hover:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring ${selected === c.id ? 'bg-accent/50' : ''}`}>
                      <div className="flex items-center justify-between gap-2">
                        <span className="flex items-center gap-1.5"><StatusPill status={c.public_status} />{c.priority === 'urgent' || c.priority === 'high' ? <StatusPill status={c.priority} /> : null}</span>
                        <span className="text-xs text-muted-foreground">{relativeDate(c.updated_at)}</span>
                      </div>
                      <p className="mt-2 line-clamp-2 text-sm font-medium">{c.title}</p>
                      <p className="mt-1 truncate text-xs text-muted-foreground">{c.reporter_name} · {KIND[c.kind]}{c.assignee_name ? ` · ${c.assignee_name}` : ''}</p>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        <div className={`${selected ? 'flex' : 'hidden lg:flex'} min-h-0 flex-col`}>
          {selected ? (
            <>
              <button type="button" onClick={() => setSelected(null)} className="flex h-11 items-center gap-2 px-4 text-sm text-muted-foreground lg:hidden"><ArrowLeft className="h-4 w-4" /> Back</button>
              <div className="min-h-0 flex-1"><CaseThread key={selected} caseId={selected} mode="staff" onChanged={() => void load()} onProposeKnowledge={(c) => setPropose(c)} /></div>
            </>
          ) : <div className="grid flex-1 place-items-center text-sm text-muted-foreground">Select a conversation to review it.</div>}
        </div>
      </div>
      {propose ? <ProposeSop item={propose} onClose={() => setPropose(null)} onDone={() => void load()} /> : null}
    </div>
  );
}
