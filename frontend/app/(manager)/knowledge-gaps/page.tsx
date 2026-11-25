'use client';

import React, { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { FilePlus2, MessageSquareReply, XCircle } from 'lucide-react';
import { useRequireRole } from '@/lib/auth';
import { apiClient, ApiError } from '@/lib/api-client';
import { PageHeader } from '@/components/shared/PageHeader';
import { LoadingState } from '@/components/shared/LoadingState';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';

interface Gap {
  id: string; question: string; occurrences: number; status: 'open' | 'answered' | 'drafting' | 'resolved' | 'dismissed';
  reported_by_name: string | null; employee_reply: string | null; draft_id: string | null; created_at: string; updated_at: string;
}

const STATUS: Record<Gap['status'], { label: string; variant: 'warning' | 'default' | 'neutral' }> = {
  open: { label: 'Needs an answer', variant: 'warning' },
  answered: { label: 'Replied, no SOP yet', variant: 'warning' },
  drafting: { label: 'SOP being drafted', variant: 'default' },
  resolved: { label: 'SOP published', variant: 'default' },
  dismissed: { label: 'Dismissed', variant: 'neutral' },
};
const FILTERS: Array<{ id: string; label: string }> = [
  { id: 'live', label: 'Needs work' }, { id: 'resolved', label: 'Resolved' }, { id: 'dismissed', label: 'Dismissed' },
];

export default function KnowledgeGapsPage() {
  const { loading, user } = useRequireRole(['admin', 'manager']) as { loading: boolean; user?: { role: string } };
  const [rows, setRows] = useState<Gap[]>([]);
  const [filter, setFilter] = useState('live');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [replying, setReplying] = useState<string | null>(null);
  const [drafting, setDrafting] = useState<string | null>(null);
  const [reply, setReply] = useState('');
  const [title, setTitle] = useState('');
  const [steps, setSteps] = useState('');
  const isAdmin = user?.role === 'admin';

  const load = useCallback(async () => {
    setError('');
    try {
      const data = await apiClient<{ items: Gap[] }>('/knowledge-gaps');
      setRows(data.items);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not load questions. Check your connection and retry.');
    }
  }, []);
  useEffect(() => { if (!loading) void load(); }, [loading, load]);

  const shown = rows.filter((r) => filter === 'live' ? ['open', 'answered', 'drafting'].includes(r.status) : r.status === filter);

  async function run(fn: () => Promise<unknown>, done: string) {
    setBusy(true); setError(''); setNotice('');
    try { await fn(); setNotice(done); await load(); return true; }
    catch (e) { setError(e instanceof ApiError ? e.message : 'That did not go through. Nothing was changed.'); return false; }
    finally { setBusy(false); }
  }

  async function sendReply(gap: Gap) {
    if (await run(() => apiClient(`/knowledge-gaps/${gap.id}/reply`, { method: 'POST', body: JSON.stringify({ reply: reply.trim() }) }),
      'Reply sent. The employee can see it. It is not stored as company knowledge.')) { setReplying(null); setReply(''); }
  }

  async function createDraft(gap: Gap) {
    const list = steps.split('\n').map((s) => s.trim()).filter(Boolean);
    if (await run(() => apiClient(`/knowledge-gaps/${gap.id}/draft`, { method: 'POST', body: JSON.stringify({ title: title.trim(), steps: list }) }),
      'Draft created in Procedure Studio. Review every step, then ask a manager to approve it.')) { setDrafting(null); setTitle(''); setSteps(''); }
  }

  if (loading) return <LoadingState />;

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <PageHeader
        eyebrow="Closing the loop"
        title="Questions WorkMate couldn't answer"
        description="Employees asked something no approved SOP covers. Reply to them now, and turn repeated gaps into a new SOP that a manager approves before it goes live."
      />
      {error ? <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div> : null}
      {notice ? <div role="status" className="rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-900">{notice}</div> : null}

      <div role="group" aria-label="Filter questions" className="flex flex-wrap gap-2">
        {FILTERS.map((f) => (
          <Button key={f.id} size="sm" variant={filter === f.id ? 'default' : 'outline'} aria-pressed={filter === f.id} onClick={() => setFilter(f.id)}>
            {f.label} ({rows.filter((r) => f.id === 'live' ? ['open', 'answered', 'drafting'].includes(r.status) : r.status === f.id).length})
          </Button>
        ))}
      </div>

      {shown.length === 0 ? (
        <div className="grid min-h-40 place-items-center rounded-xl border border-dashed bg-muted/25 p-6 text-center text-sm text-muted-foreground">
          {filter === 'live' ? 'No open questions. When an employee asks something no SOP covers, it will appear here.' : 'Nothing here yet.'}
        </div>
      ) : (
        <ul className="space-y-4">
          {shown.map((g) => (
            <li key={g.id}>
              <Card>
                <CardContent className="space-y-3 p-5">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <p className="max-w-2xl text-base font-semibold leading-6">“{g.question}”</p>
                    <Badge variant={STATUS[g.status].variant}>{STATUS[g.status].label}</Badge>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    Asked {g.occurrences} time{g.occurrences === 1 ? '' : 's'} · first by {g.reported_by_name ?? 'an employee'} · {new Date(g.created_at).toLocaleDateString()}
                  </p>
                  {g.employee_reply ? <p className="rounded-lg bg-muted/50 p-3 text-sm"><span className="font-semibold">Reply shown to employee:</span> {g.employee_reply}</p> : null}

                  {['open', 'answered', 'drafting'].includes(g.status) ? (
                    <div className="flex flex-wrap gap-2">
                      <Button size="sm" variant="outline" disabled={busy} onClick={() => { setReplying(replying === g.id ? null : g.id); setDrafting(null); setReply(g.employee_reply ?? ''); }}><MessageSquareReply className="h-4 w-4" />{g.employee_reply ? 'Edit reply' : 'Reply to employee'}</Button>
                      {isAdmin && !g.draft_id ? <Button size="sm" variant="outline" disabled={busy} onClick={() => { setDrafting(drafting === g.id ? null : g.id); setReplying(null); setTitle(''); setSteps(''); }}><FilePlus2 className="h-4 w-4" />Draft an SOP</Button> : null}
                      {g.draft_id ? <Link href={`/procedure-studio/drafts/${encodeURIComponent(g.draft_id)}`}><Button size="sm" variant="secondary">Open the draft</Button></Link> : null}
                      {isAdmin ? <Button size="sm" variant="ghost" disabled={busy} onClick={() => run(() => apiClient(`/knowledge-gaps/${g.id}/dismiss`, { method: 'POST' }), 'Dismissed.')}><XCircle className="h-4 w-4" />Dismiss</Button> : null}
                    </div>
                  ) : null}

                  {replying === g.id ? (
                    <div className="space-y-2 border-t pt-3">
                      <label className="block"><span className="wm-label">Your reply (the employee will see this)</span>
                        <textarea className="wm-input min-h-24" value={reply} onChange={(e) => setReply(e.target.value)} maxLength={1500} /></label>
                      <p className="text-xs text-muted-foreground">A reply helps this person now. It does not become an approved procedure and WorkMate will not quote it to others.</p>
                      <Button size="sm" disabled={busy || reply.trim().length < 3} onClick={() => sendReply(g)}>Send reply</Button>
                    </div>
                  ) : null}

                  {drafting === g.id ? (
                    <div className="space-y-3 border-t pt-3">
                      <label className="block"><span className="wm-label">SOP title</span>
                        <input className="wm-input" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={180} /></label>
                      <label className="block"><span className="wm-label">Steps, one per line</span>
                        <textarea className="wm-input min-h-32" value={steps} onChange={(e) => setSteps(e.target.value)} placeholder={'Stop the labeller and tell your supervisor\nAsk authorised maintenance to recalibrate it'} /></label>
                      <p className="text-xs text-muted-foreground">This creates an unpublished draft. You will check each step in Procedure Studio, then a manager must approve it before you can publish.</p>
                      <Button size="sm" disabled={busy || title.trim().length < 5 || steps.trim().length < 10} onClick={() => createDraft(g)}>Create draft</Button>
                    </div>
                  ) : null}
                </CardContent>
              </Card>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
