'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { CheckCircle2, Undo2 } from 'lucide-react';
import { useRequireRole } from '@/lib/auth';
import { apiClient, ApiError } from '@/lib/api-client';
import { PageHeader } from '@/components/shared/PageHeader';
import { LoadingState } from '@/components/shared/LoadingState';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';

interface Step { id: string; instruction: string; output_type?: string; evidence_type?: string }
interface Pending {
  id: string; title: string; revision: number; steps: Step[]; warnings: string[]; approved: boolean;
  gap_question: string | null; reviewed_at: string | null; source_filename: string;
  decision?: { question?: string; options?: { code: string; label: string; requires_supervisor_review?: boolean }[] } | null;
}

export default function ApprovalsPage() {
  const { loading } = useRequireRole(['manager']);
  const [rows, setRows] = useState<Pending[]>([]);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [returning, setReturning] = useState<string | null>(null);
  const [note, setNote] = useState('');

  const load = useCallback(async () => {
    setError('');
    try { setRows((await apiClient<{ items: Pending[] }>('/procedure/approvals')).items); }
    catch (e) { setError(e instanceof ApiError ? e.message : 'Could not load approvals. Check your connection and retry.'); }
  }, []);
  useEffect(() => { if (!loading) void load(); }, [loading, load]);

  async function decide(p: Pending, decision: 'approve' | 'return') {
    setBusy(true); setError(''); setNotice('');
    try {
      await apiClient(`/procedure/approvals/${p.id}`, { method: 'POST', body: JSON.stringify({ expected_revision: p.revision, decision, note: note.trim() }) });
      setNotice(decision === 'approve' ? 'Approved. An administrator can now publish this exact revision.' : 'Returned to the administrator with your note.');
      setReturning(null); setNote(''); await load();
    } catch (e) { setError(e instanceof ApiError ? e.message : 'That did not go through. Nothing was changed.'); }
    finally { setBusy(false); }
  }

  if (loading) return <LoadingState />;
  const waiting = rows.filter((r) => !r.approved);
  const approved = rows.filter((r) => r.approved);

  const renderCard = (p: Pending) => (
    <li key={p.id}>
      <Card>
        <CardContent className="space-y-4 p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h3 className="text-base font-semibold">{p.title}</h3>
              <p className="mt-1 text-xs text-muted-foreground">Revision {p.revision} · reviewed {p.reviewed_at ? new Date(p.reviewed_at).toLocaleString() : ''}</p>
            </div>
            <Badge variant={p.approved ? 'default' : 'warning'}>{p.approved ? 'Approved, awaiting publish' : 'Needs your decision'}</Badge>
          </div>
          {p.gap_question ? <p className="rounded-lg bg-muted/50 p-3 text-sm"><span className="font-semibold">Answers an employee question:</span> “{p.gap_question}”</p> : null}
          <ol className="space-y-2 text-sm">
            {p.steps.map((s, i) => (
              <li key={s.id} className="flex gap-3"><span className="mt-0.5 grid h-6 w-6 flex-none place-items-center rounded-full bg-emerald-50 text-xs font-bold text-emerald-800">{i + 1}</span>
                <span>{s.instruction}{s.evidence_type && s.evidence_type !== 'NONE' ? <Badge variant="neutral" className="ml-2">needs {s.evidence_type === 'PHOTO_JPEG' ? 'photo' : 'document'}</Badge> : null}</span></li>
            ))}
          </ol>
          {p.decision?.question ? <p className="text-sm"><span className="font-semibold">Decision:</span> {p.decision.question} ({(p.decision.options ?? []).map((o) => o.label).join(' / ')})</p> : null}
          {p.warnings.length ? <ul className="list-disc pl-5 text-xs text-amber-800">{p.warnings.map((w) => <li key={w}>{w}</li>)}</ul> : null}
          {!p.approved ? (
            <div className="space-y-3 border-t pt-3">
              <p className="text-xs text-muted-foreground">Approve only if each step is correct, safe, and within what an untrained worker may do. Your approval covers this exact revision; any edit voids it.</p>
              <div className="flex flex-wrap gap-2">
                <Button size="sm" disabled={busy} onClick={() => decide(p, 'approve')}><CheckCircle2 className="h-4 w-4" />Approve this revision</Button>
                <Button size="sm" variant="outline" disabled={busy} onClick={() => { setReturning(returning === p.id ? null : p.id); setNote(''); }}><Undo2 className="h-4 w-4" />Return with a note</Button>
              </div>
              {returning === p.id ? (
                <div className="space-y-2">
                  <label className="block"><span className="wm-label">What needs to change?</span>
                    <textarea className="wm-input min-h-20" value={note} maxLength={800} onChange={(e) => setNote(e.target.value)} /></label>
                  <Button size="sm" disabled={busy || note.trim().length < 8} onClick={() => decide(p, 'return')}>Send back</Button>
                </div>
              ) : null}
            </div>
          ) : null}
        </CardContent>
      </Card>
    </li>
  );

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <PageHeader eyebrow="Governance" title="SOP approvals" description="Administrators prepare and review procedures. You decide whether an exact revision may go live. You cannot approve something you created or reviewed." />
      {error ? <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div> : null}
      {notice ? <div role="status" className="rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-900">{notice}</div> : null}
      {rows.length === 0 ? (
        <div className="grid min-h-40 place-items-center rounded-xl border border-dashed bg-muted/25 p-6 text-center text-sm text-muted-foreground">Nothing is waiting. Reviewed drafts from your administrators will appear here.</div>
      ) : (
        <>
          {waiting.length ? <ul className="space-y-4">{waiting.map(renderCard)}</ul> : null}
          {approved.length ? <><h2 className="pt-2 text-sm font-semibold text-muted-foreground">Approved, not yet published</h2><ul className="space-y-4">{approved.map(renderCard)}</ul></> : null}
        </>
      )}
    </div>
  );
}
