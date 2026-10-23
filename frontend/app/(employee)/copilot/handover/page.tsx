'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { ArrowLeft, ArrowRight, ClipboardCheck, ClipboardCopy, Download, FileText, History, ShieldCheck } from 'lucide-react';
import { useRequireRole } from '@/lib/auth';
import { apiClient, type CopilotConversationDetail, type CopilotHistoryResponse, type CopilotSessionSummary } from '@/lib/api-client';
import { LoadingState } from '@/components/shared/LoadingState';

const HANDOVER_STATES = [
  { value: 'pending_next_shift', label: 'Pending next shift' },
  { value: 'blocked_supervisor', label: 'Blocked — needs supervisor' },
  { value: 'information', label: 'For information' },
  { value: 'follow_up', label: 'Ready for follow-up' },
] as const;
const EXCEPTION_TYPES = [
  { value: 'none', label: 'No exception' }, { value: 'damage', label: 'Damaged goods' },
  { value: 'quantity_mismatch', label: 'Quantity mismatch' },
  { value: 'missing_document', label: 'Missing document' },
  { value: 'safety_concern', label: 'Safety concern' }, { value: 'other', label: 'Other issue' },
] as const;

function handoverText(args: {
  session: CopilotSessionSummary;
  detail: CopilotConversationDetail;
  author: string;
  department: string;
  recipient: string;
  disposition: string;
  nextAction: string;
  notes: string;
}) {
  const recent = args.detail.messages.slice(-4);
  return [
    'WORKMATE · SHIFT HANDOVER DRAFT',
    'Prepared: ' + new Date().toISOString(),
    'Prepared by: ' + args.author,
    'Department: ' + args.department,
    'Recipient / next shift: ' + (args.recipient.trim() || 'Not specified'),
    'Handover status (employee assessment): ' + (HANDOVER_STATES.find(item => item.value === args.disposition)?.label || args.disposition),
    '',
    'LINKED WORK SESSION',
    'Session title: ' + (args.session.title || 'Operational conversation'),
    'Session ID: ' + args.session.id,
    'Recorded workflow status: ' + (args.detail.active_session_status || 'Not available'),
    'Recorded current step: ' + (args.detail.active_step_title || 'Not available'),
    '',
    'NEXT ACTION (employee-entered)',
    args.nextAction.trim() || 'Not recorded',
    '',
    'ADDITIONAL CONTEXT (employee-entered)',
    args.notes.trim() || 'None',
    '',
    'RECENT CONVERSATION EXCERPTS',
    ...recent.flatMap((message, index) => [
      '[' + (index + 1) + '] ' + (message.sender === 'employee' ? 'EMPLOYEE' : 'WORKMATE'),
      message.content.slice(0, 1000),
      '',
    ]),
    'IMPORTANT: Prepared locally for human review. This is not an approved policy, verified work completion, official audit log, or transmitted handover.',
    'The recipient must check the original workflow and supporting cited sources before acting.',
  ].join('\n');
}

export default function ShiftHandoverPage() {
  const { user, loading } = useRequireRole(['employee', 'admin', 'manager']);
  const [sessions, setSessions] = useState<CopilotSessionSummary[]>([]);
  const [selectedId, setSelectedId] = useState('');
  const [detail, setDetail] = useState<CopilotConversationDetail | null>(null);
  const [listLoading, setListLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState('');
  const [recipient, setRecipient] = useState('');
  const [disposition, setDisposition] = useState<string>(HANDOVER_STATES[0].value);
  const [exceptionType, setExceptionType] = useState<string>('none');
  const [severity, setSeverity] = useState<'normal' | 'high' | 'critical'>('normal');
  const [saving, setSaving] = useState(false);
  const [savedId, setSavedId] = useState('');
  const [nextAction, setNextAction] = useState('');
  const [notes, setNotes] = useState('');
  const [notice, setNotice] = useState('');
  const [saveError, setSaveError] = useState('');

  useEffect(() => {
    if (loading || !user) return;
    let active = true;
    void apiClient<CopilotHistoryResponse>('/copilot/history')
      .then(response => {
        if (!active) return;
        const available = response.sessions ?? [];
        setSessions(available);
        if (available.length) setSelectedId(available[0].id);
      })
      .catch(caught => { if (active) setError(caught instanceof Error ? caught.message : 'Sessions could not be loaded.'); })
      .finally(() => { if (active) setListLoading(false); });
    return () => { active = false; };
  }, [loading, user?.sub, user?.department_id]);

  useEffect(() => {
    if (!selectedId) return;
    let active = true;
    setDetail(null);
    setSavedId('');
    setSaveError('');
    setDetailLoading(true);
    setNotice('');
    setError('');
    void apiClient<CopilotConversationDetail>('/copilot/history/' + encodeURIComponent(selectedId))
      .then(result => { if (active) setDetail(result); })
      .catch(caught => { if (active) setError(caught instanceof Error ? caught.message : 'Session could not be loaded.'); })
      .finally(() => { if (active) setDetailLoading(false); });
    return () => { active = false; };
  }, [selectedId]);

  if (loading) return <LoadingState label="Opening shift handover" />;

  const chosen = sessions.find(session => session.id === selectedId);
  const canExport = Boolean(chosen && detail && !detailLoading);
  const getText = () => handoverText({
    session: chosen!,
    detail: detail!,
    author: user?.sub || 'Current user',
    department: user?.department_id || 'Current department',
    recipient, disposition, nextAction, notes,
  });
  const validSave = canExport && !saving && recipient.trim().length >= 2 &&
    nextAction.trim().length >= 5 && !(severity === 'critical' && exceptionType === 'none') &&
    !(exceptionType === 'safety_concern' && disposition === 'information');

  const saveForReview = async () => {
    if (!validSave) return;
    setSaving(true);
    setSaveError('');
    setSavedId('');
    try {
      const saved = await apiClient<{ id: string }>('/handover', {
        method: 'POST',
        body: JSON.stringify({
          conversation_id: selectedId, recipient_label: recipient.trim(),
          disposition, exception_type: exceptionType, severity,
          next_action: nextAction.trim(), notes: notes.trim(),
        }),
      });
      setSavedId(saved.id);
      setNotice('Handover submitted to the department review queue. Workflow state is unchanged.');
    } catch (caught) {
      setSaveError(caught instanceof Error ? caught.message : 'Unable to save handover.');
    } finally {
      setSaving(false);
    }
  };

  const copy = async () => {
    if (!canExport) return;
    try {
      await navigator.clipboard.writeText(getText());
      setNotice('Handover draft copied. Review it before sharing.');
    } catch {
      setNotice('Clipboard unavailable. Download the draft instead.');
    }
  };
  const download = () => {
    if (!canExport) return;
    const blob = new Blob([getText()], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'workmate-shift-handover.txt';
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    setNotice('Local handover draft downloaded. It was not sent or stored.');
  };

  return (
    <div className="wm-page max-w-6xl space-y-7 pb-12">
      <header><h1 className="text-3xl font-semibold">Shift handover</h1></header>

      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(18rem,0.82fr)]">
        <section className="wm-panel p-5 sm:p-7" aria-labelledby="compose-handover">
          <h2 id="compose-handover" className="mt-2 text-xl font-semibold tracking-tight">Prepare a handover</h2>

          {error ? <div role="alert" className="mt-4 rounded-xl border border-red-200 bg-red-50 p-3 text-xs text-red-800">{error}</div> : null}
          <div className="mt-6">
            <label className="wm-label" htmlFor="handover-session">Linked work session</label>
            <select id="handover-session" className="wm-input" value={selectedId} onChange={event => setSelectedId(event.target.value)} disabled={listLoading || sessions.length === 0}>
              {sessions.length === 0 ? <option value="">{listLoading ? 'Loading sessions…' : 'No saved sessions yet'}</option> : null}
              {sessions.map(session => <option key={session.id} value={session.id}>{session.title || 'Operational conversation'} · {session.status || 'session'}</option>)}
            </select>
            {!listLoading && sessions.length === 0 ? <Link href="/copilot" className="mt-2 inline-flex items-center gap-1.5 text-xs font-semibold text-emerald-700">Start your first session <ArrowRight className="h-3.5 w-3.5" /></Link> : null}
          </div>
          {detailLoading ? <p role="status" className="mt-3 text-xs text-muted-foreground">Checking saved workflow context…</p> : null}
          {detail && chosen ? (
            <div className="mt-4 grid grid-cols-2 gap-3 rounded-xl border border-emerald-100 bg-emerald-50/50 p-4">
              <div><p className="text-[10px] font-semibold uppercase tracking-wide text-emerald-700">Recorded status</p><p className="mt-1 text-xs font-semibold capitalize">{detail.active_session_status || 'Not recorded'}</p></div>
              <div><p className="text-[10px] font-semibold uppercase tracking-wide text-emerald-700">Current step</p><p className="mt-1 text-xs font-semibold">{detail.active_step_title || 'Not recorded'}</p></div>
            </div>
          ) : null}

          <div className="mt-5 grid gap-4 sm:grid-cols-2">
            <div><label htmlFor="handover-recipient" className="wm-label">Next shift / recipient</label><input id="handover-recipient" maxLength={100} className="wm-input" value={recipient} onChange={event => setRecipient(event.target.value)} placeholder="e.g. Morning warehouse lead" /></div>
            <div><label htmlFor="handover-state" className="wm-label">Your assessment</label><select id="handover-state" value={disposition} onChange={event => setDisposition(event.target.value)} className="wm-input">{HANDOVER_STATES.map(state => <option key={state.value} value={state.value}>{state.label}</option>)}</select></div>
          </div>
          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            <div><label className="wm-label" htmlFor="handover-exception">Exception category</label>
              <select className="wm-input" id="handover-exception" value={exceptionType} onChange={event => setExceptionType(event.target.value)}>{EXCEPTION_TYPES.map(item => <option key={item.value} value={item.value}>{item.label}</option>)}</select>
            </div>
            <div><label className="wm-label" htmlFor="handover-severity">Attention needed</label>
              <select className="wm-input" id="handover-severity" value={severity} onChange={event => setSeverity(event.target.value as typeof severity)}>
                <option value="normal">Normal</option><option value="high">High priority</option><option value="critical">Critical — supervisor required</option>
              </select>
            </div>
          </div>
          {severity === 'critical' || exceptionType === 'safety_concern' ? (
            <div role="status" className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-4 text-xs leading-6 text-amber-950">
              <strong>Escalation attention.</strong> This record is for human review. Do not continue an unsafe operation or treat the handover as permission to bypass the published procedure.
            </div>
          ) : null}
          <div className="mt-4"><label htmlFor="handover-next" className="wm-label">What needs to happen next?</label><textarea id="handover-next" className="wm-input min-h-28 resize-y leading-6" rows={3} maxLength={1500} value={nextAction} onChange={event => setNextAction(event.target.value)} placeholder="Describe the next check, decision, or supervisor follow-up…" /></div>
          <div className="mt-4"><label htmlFor="handover-notes" className="wm-label">Additional context (optional)</label><textarea id="handover-notes" className="wm-input min-h-28 resize-y leading-6" rows={3} maxLength={1500} value={notes} onChange={event => setNotes(event.target.value)} placeholder="Record outstanding issues and observations in your own words…" /></div>
          {saveError ? <p role="alert" className="mt-4 rounded-xl bg-red-50 p-3 text-xs text-red-800">{saveError}</p> : null}
          {savedId ? <p role="status" className="mt-4 rounded-xl bg-emerald-50 p-3 text-xs text-emerald-800">Submitted · {savedId} · awaiting review. <Link className="font-semibold underline" href="/handover/review">Open review queue</Link></p> : null}
          <div className="mt-5 flex flex-wrap gap-2">
            <button type="button" disabled={!validSave || Boolean(savedId)} onClick={() => void saveForReview()} className="inline-flex items-center gap-2 rounded-xl bg-[#165a45] px-5 py-3 text-xs font-semibold text-white hover:bg-[#0c3a2a] disabled:opacity-50">
              <ClipboardCheck className="h-4 w-4" />{saving ? 'Submitting…' : savedId ? 'Submitted' : 'Submit for review'}
            </button>
            <button type="button" disabled={!canExport} onClick={() => void copy()} className="inline-flex items-center gap-2 rounded-xl bg-emerald-700 px-5 py-3 text-xs font-semibold text-white hover:bg-emerald-800 disabled:opacity-50"><ClipboardCopy className="h-4 w-4" />Copy handover</button>
            <button type="button" disabled={!canExport} onClick={download} className="inline-flex items-center gap-2 rounded-xl border border-border px-5 py-3 text-xs font-semibold hover:bg-muted disabled:opacity-50"><Download className="h-4 w-4" />Download .txt</button>
          </div>
          {notice ? <p role="status" className="mt-3 text-xs text-emerald-800">{notice}</p> : null}
          <p className="mt-4 text-[11px] text-muted-foreground">Submitting records a handover for supervisor review; it does not approve or complete work.</p>
        </section>

        <aside className="space-y-4 lg:sticky lg:top-24">
          <div className="wm-panel overflow-hidden">
            <div className="flex items-center gap-2 border-b border-border bg-[#f5faf6] px-5 py-4"><FileText className="h-4 w-4 text-emerald-700" /><h2 className="text-sm font-semibold">Recent context</h2></div>
            <div className="space-y-3 p-5">
              {!detail ? <p className="text-xs leading-6 text-muted-foreground">Select a session to inspect its latest conversation excerpts.</p> : null}
              {detail?.messages.slice(-4).map(message => (
                <div key={message.id} className="rounded-xl border border-border bg-muted/40 p-3.5">
                  <p className="text-[10px] font-bold uppercase tracking-widest text-emerald-700">{message.sender === 'employee' ? 'Employee' : 'WorkMate'}</p>
                  <p className="mt-2 max-h-32 overflow-y-auto whitespace-pre-wrap break-words text-xs leading-6 text-foreground">{message.content}</p>
                </div>
              ))}
              {detail && detail.messages.length === 0 ? <p className="text-xs text-muted-foreground">This session has no messages yet.</p> : null}
              {chosen ? <Link href={'/copilot?session=' + encodeURIComponent(chosen.id)} className="inline-flex items-center gap-2 text-xs font-semibold text-emerald-700 hover:underline">Reopen this session <ArrowRight className="h-3.5 w-3.5" /></Link> : null}
            </div>
          </div>

        </aside>
      </div>
    </div>
  );
}
