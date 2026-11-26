'use client';

import React, { Suspense, useCallback, useEffect, useState } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import { SquarePen, Volume2, VolumeX } from 'lucide-react';
import { useRequireRole } from '@/lib/auth';
import {
  apiClient, type CopilotConversationDetail, type CopilotResponse, type SopSuggestion, type WorkflowAdvanceResponse,
} from '@/lib/api-client';
import { useLanguage } from '@/lib/language';
import { useAudioPlayer } from '@/hooks/useAudioPlayer';
import { Messages, type ChatMessage } from '@/components/assistant/Messages';
import { AssistantComposer } from '@/components/assistant/AssistantComposer';
import { WorkflowRail } from '@/components/chat/WorkflowRail';
import { ConfirmDialog } from '@/components/shared/ConfirmDialog';
import { LoadingState } from '@/components/shared/LoadingState';

const newId = (prefix: string) => `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
const errorText = (error: unknown, fallback: string) => (error instanceof Error && error.message ? error.message : fallback);
const firstName = (sub: string) => sub.replace(/^(demo|usr)_/, '').replace(/[_-]+/g, ' ').split(' ')[0].replace(/^./, (c) => c.toUpperCase());
const greeting = () => { const h = new Date().getHours(); return h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening'; };
const READ_KEY = 'wm_read_aloud';

function Assistant() {
  const { user, loading } = useRequireRole(['employee', 'admin', 'manager']);
  const search = useSearchParams();
  const router = useRouter();
  const sessionId = search.get('session');
  const [language, setLanguage] = useLanguage();
  const player = useAudioPlayer();

  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [conversationId, setConversationId] = useState<string | undefined>(sessionId || undefined);
  const [workflow, setWorkflow] = useState<{ id?: string; status?: CopilotResponse['active_session_status']; options: NonNullable<CopilotResponse['active_decision_options']>; step?: number; title?: string }>({ options: [] });
  const [busy, setBusy] = useState(false);
  const [abandonOpen, setAbandonOpen] = useState(false);
  const [abandonReason, setAbandonReason] = useState('');
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [readAloud, setReadAloud] = useState(true);

  useEffect(() => { try { setReadAloud(window.localStorage.getItem(READ_KEY) !== 'off'); } catch { /* default on */ } }, []);
  const toggleReadAloud = () => {
    const next = !readAloud;
    setReadAloud(next);
    if (!next) player.stop();
    try { window.localStorage.setItem(READ_KEY, next ? 'on' : 'off'); } catch { /* not persisted */ }
  };

  useEffect(() => {
    if (loading) return;
    void apiClient<{ items: { title: string; question: string }[] }>('/copilot/suggestions?limit=4')
      .then((r) => setSuggestions(r.items.map((i) => i.question)))
      .catch(() => setSuggestions([]));
  }, [loading]);

  const applyWorkflow = (r: Partial<CopilotResponse> | CopilotConversationDetail) => setWorkflow({
    id: (('active_session_id' in r ? r.active_session_id : undefined) ?? undefined) || undefined,
    status: ('active_session_status' in r ? r.active_session_status : undefined) ?? undefined,
    options: ('active_decision_options' in r ? r.active_decision_options : undefined) || [],
    step: ('active_step_number' in r ? r.active_step_number : undefined) ?? undefined,
    title: ('active_step_title' in r ? r.active_step_title : undefined) ?? undefined,
  });

  useEffect(() => {
    if (!sessionId || loading) return;
    void apiClient<CopilotConversationDetail>(`/copilot/history/${sessionId}`).then((history) => {
      setConversationId(sessionId);
      applyWorkflow(history);
      setMessages(history.messages.map((m) => ({ id: m.id, sender: m.sender === 'employee' ? 'user' : 'assistant', content: m.content })));
    }).catch((e) => setMessages([{ id: 'resume-error', sender: 'assistant', content: errorText(e, 'I could not open that conversation.') }]));
  }, [sessionId, loading]);

  const submit = useCallback(async (text: string, viaVoice = false, selection?: { workflowCode: string; originalQuery: string; responseLanguage: string; displayMessage: string }) => {
    const message = text.trim();
    if (!message || busy) return;
    setInput('');
    setBusy(true);
    setMessages((cur) => [...cur, { id: newId('user'), sender: 'user', content: selection?.displayMessage || message }]);
    try {
      const r = await apiClient<CopilotResponse>('/copilot/message', {
        method: 'POST',
        body: JSON.stringify({
          message, conversation_id: conversationId, selected_workflow_code: selection?.workflowCode,
          original_query: selection?.originalQuery, response_language: selection?.responseLanguage ?? language,
          // The assistant decides whether this is a quick answer, a procedure or an escalation.
          mode: 'workflow',
        }),
      });
      setConversationId(r.conversation_id || conversationId);
      applyWorkflow(r);
      setMessages((cur) => [...cur, { id: r.message_id || newId('assistant'), sender: 'assistant', content: r.answer, copilotData: r, language: selection?.responseLanguage, speakWhenReady: viaVoice && readAloud }]);
    } catch (e) {
      setMessages((cur) => [...cur, { id: newId('error'), sender: 'assistant', content: errorText(e, 'I could not reach WorkMate. Please try again.') }]);
    } finally {
      setBusy(false);
    }
  }, [busy, conversationId, language, readAloud]);

  const selectSop = useCallback((s: SopSuggestion, lang: string, originalQuery: string) => {
    void submit(s.source_query || originalQuery || s.title, false, {
      workflowCode: s.workflow_code, originalQuery: originalQuery || s.source_query || s.title,
      responseLanguage: lang === 'hi' ? 'hi' : 'en', displayMessage: s.title,
    });
  }, [submit]);

  const workflowAction = async (action: 'pause' | 'resume' | 'advance' | 'abandon', option?: string, reason?: string) => {
    if (!workflow.id || busy) return;
    const label = option ? workflow.options.find((o) => o.option_code === option)?.option_label : undefined;
    let body: string | undefined;
    if (action === 'abandon') { if (!reason?.trim()) return; body = JSON.stringify({ reason: reason.trim() }); }
    else if (action === 'advance') body = JSON.stringify({ decision_option: option, rule_results: {}, values: {}, use_fallback: false });
    if (label) setMessages((cur) => [...cur, { id: newId('decision'), sender: 'user', content: `What I saw: ${label}` }]);
    setBusy(true);
    try {
      const u = await apiClient<WorkflowAdvanceResponse>(`/copilot/session/${workflow.id}/${action}`, { method: 'POST', body });
      setWorkflow((w) => ({ ...w, status: u.status, ...(action === 'advance' ? { options: u.active_decision_options || [], step: u.active_step_number ?? undefined, title: u.active_step_title ?? undefined } : {}) }));
      const prefix = label ? `Recorded: ${label}. ` : '';
      const status = action !== 'advance' ? `Procedure ${u.status}.`
        : u.status === 'completed' ? `${prefix}All steps done.`
        : u.active_decision_options?.length ? 'Step done. Tell me what you saw.'
        : u.active_step_title ? `${prefix}Next: ${u.active_step_title}` : 'Step done.';
      setMessages((cur) => [...cur, { id: newId('workflow'), sender: 'assistant', content: status }]);
      if (action === 'abandon') { setAbandonOpen(false); setAbandonReason(''); }
    } catch (e) {
      setMessages((cur) => [...cur, { id: newId('wf-error'), sender: 'assistant', content: errorText(e, `Could not ${action} the procedure.`) }]);
    } finally {
      setBusy(false);
    }
  };

  const newConversation = () => {
    player.stop();
    setMessages([]); setConversationId(undefined); setWorkflow({ options: [] }); setInput('');
    if (sessionId) router.replace('/copilot');
  };

  if (loading || !user) return <LoadingState label="Opening WorkMate" />;
  const hasWorkflow = Boolean(workflow.id && workflow.status && workflow.status !== 'completed' && workflow.status !== 'abandoned');
  const empty = messages.length === 0;

  return (
    <div className="flex h-full min-h-0 flex-col bg-background">
      <header className="flex h-12 flex-none items-center justify-end gap-1 px-3 sm:px-5">
        <button type="button" onClick={toggleReadAloud} aria-pressed={readAloud} aria-label="Read answers aloud after I speak"
          title={readAloud ? 'Answers to spoken questions are read aloud' : 'Answers are not read aloud'}
          className="grid h-11 w-11 place-items-center rounded-lg text-muted-foreground hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
          {readAloud ? <Volume2 className="h-[18px] w-[18px]" /> : <VolumeX className="h-[18px] w-[18px]" />}
        </button>
        <button type="button" onClick={newConversation} disabled={empty && !conversationId}
          className="inline-flex h-9 items-center gap-2 rounded-lg px-3 text-sm text-muted-foreground hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-40">
          <SquarePen className="h-4 w-4" aria-hidden="true" /><span className="hidden sm:inline">New conversation</span><span className="sr-only sm:hidden">New conversation</span>
        </button>
      </header>

      <div className="min-h-0 flex-1">
        {empty ? (
          <div className="mx-auto flex h-full max-w-2xl flex-col items-center justify-center px-5 pb-10 text-center">
            <p className="text-sm text-muted-foreground">{greeting()}, {firstName(user.sub)}</p>
            <h1 className="mt-1 font-display text-3xl font-semibold tracking-tight sm:text-4xl">How can I help you today?</h1>
            <p className="mt-2 text-[15px] text-muted-foreground">Ask about your work, company procedures or anything you need help with.</p>
            {suggestions.length ? (
              <div className="mt-7 flex flex-wrap justify-center gap-2" aria-label="Suggested questions">
                {suggestions.map((q) => (
                  <button key={q} type="button" onClick={() => setInput(q)}
                    className="rounded-full border border-border bg-card px-4 py-2 text-sm text-foreground transition hover:border-primary hover:bg-accent/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
                    {q}
                  </button>
                ))}
              </div>
            ) : null}
          </div>
        ) : (
          <Messages messages={messages} busy={busy} language={language} player={player} conversationId={conversationId} onSelectSop={selectSop} />
        )}
      </div>

      {hasWorkflow ? (
        <details open className="mx-auto w-full max-w-3xl flex-none px-3 sm:px-6">
          <summary className="cursor-pointer list-none rounded-t-xl border border-b-0 border-border bg-accent/60 px-4 py-2 text-sm font-medium text-accent-foreground">
            Following a procedure{workflow.step != null ? ` · step ${workflow.step}` : ''}{workflow.title ? ` · ${workflow.title}` : ''}
          </summary>
          <div className="max-h-64 overflow-y-auto rounded-b-xl border border-border bg-card">
            <WorkflowRail sessionId={workflow.id} status={workflow.status} stepNumber={workflow.step} stepTitle={workflow.title}
              decisionOptions={workflow.options} busy={busy}
              onAdvance={(o) => workflowAction('advance', o)} onPause={() => workflowAction('pause')}
              onResume={() => workflowAction('resume')} onAbandon={() => setAbandonOpen(true)} />
          </div>
        </details>
      ) : null}

      <AssistantComposer value={input} onChange={setInput} onSend={(v) => void submit(input, v)} busy={busy} language={language} onLanguageChange={setLanguage}
        placeholder={hasWorkflow ? 'Ask about this step, or say done…' : undefined} />

      <ConfirmDialog open={abandonOpen} title="Stop this procedure?" description="It will be closed and cannot be resumed. Add a short reason for the record."
        confirmLabel="Stop procedure" busy={busy} value={abandonReason} valueLabel="Reason" valuePlaceholder="Why are you stopping?"
        onValueChange={setAbandonReason} onConfirm={() => workflowAction('abandon', undefined, abandonReason)} onClose={() => !busy && setAbandonOpen(false)} />
    </div>
  );
}

export default function AssistantPage() {
  return <Suspense fallback={<LoadingState label="Opening WorkMate" />}><Assistant /></Suspense>;
}
