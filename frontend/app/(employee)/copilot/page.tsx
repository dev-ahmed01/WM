'use client';

import React, { useState, useEffect, Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import { useRequireRole } from '@/lib/auth';
import { ChatThread } from '@/components/chat/ChatThread';
import {
  apiClient,
  CopilotConversationDetail,
  CopilotResponse,
  WorkflowAdvanceResponse,
} from '@/lib/api-client';

function CopilotContent() {
  const { user, loading } = useRequireRole(['employee', 'admin', 'manager']);
  const searchParams = useSearchParams();
  const sessionId = searchParams.get('session');

  const [input, setInput] = useState('');
  const [conversationId, setConversationId] = useState<string | undefined>(sessionId || undefined);
  const [workflowSessionId, setWorkflowSessionId] = useState<string | undefined>();
  const [workflowSessionStatus, setWorkflowSessionStatus] = useState<CopilotResponse['active_session_status']>();
  const [workflowDecisionOptions, setWorkflowDecisionOptions] = useState<NonNullable<CopilotResponse['active_decision_options']>>([]);
  const [activeStepNumber, setActiveStepNumber] = useState<number | undefined>();
  const [activeStepTitle, setActiveStepTitle] = useState<string | undefined>();
  const [isSending, setIsSending] = useState(false);
  const [messages, setMessages] = useState<
    Array<{ sender: 'user' | 'assistant'; content: string; copilotData?: CopilotResponse }>
  >([
    {
      sender: 'assistant',
      content: sessionId
        ? `Resuming session ${sessionId}... Fetching active operational context.`
        : 'Welcome to WorkMate Copilot. Ask a question or request guidance on an operational SOP.',
    },
  ]);

  useEffect(() => {
    async function resumeSession() {
      if (!sessionId || loading) return;

      try {
        const history = await apiClient<CopilotConversationDetail>(`/copilot/history/${sessionId}`);
        setConversationId(sessionId);
        setWorkflowSessionId(history.active_session_id ?? undefined);
        setWorkflowSessionStatus(history.active_session_status ?? undefined);
        setWorkflowDecisionOptions(history.active_decision_options || []);
        setActiveStepNumber(history.active_step_number ?? undefined);
        setActiveStepTitle(history.active_step_title ?? undefined);
        setMessages(history.messages.map((message) => ({
          sender: message.sender === 'employee' ? 'user' : 'assistant',
          content: message.content,
        })));
      } catch (err: any) {
        setMessages([{ sender: 'assistant', content: err.message || 'Unable to load the conversation.' }]);
      }
    }

    resumeSession();
  }, [sessionId, loading]);

  if (loading) return <div className="p-8">Loading context...</div>;

  const handleSend = async () => {
    if (!input.trim() || isSending) return;

    const userMsg = input.trim();
    setInput('');
    setIsSending(true);

    // Optimistic user message addition
    setMessages((prev) => [
      ...prev,
      { sender: 'user', content: userMsg },
    ]);

    try {
      const response = await apiClient<CopilotResponse>('/copilot/message', {
        method: 'POST',
        body: JSON.stringify({
          message: userMsg,
          conversation_id: conversationId,
        }),
      });

      if (response.conversation_id) {
        setConversationId(response.conversation_id);
      }
      setWorkflowSessionId(response.active_session_id ?? undefined);
      setWorkflowSessionStatus(response.active_session_status ?? undefined);
      setWorkflowDecisionOptions(response.active_decision_options || []);
      setActiveStepNumber(response.active_step_number ?? undefined);
      setActiveStepTitle(response.active_step_title ?? undefined);

      setMessages((prev) => [
        ...prev,
        {
          sender: 'assistant',
          content: response.answer,
          copilotData: response,
        },
      ]);
    } catch (err: any) {
      setMessages((prev) => [
        ...prev,
        {
          sender: 'assistant',
          content: `Error connecting to Copilot service: ${err.message || 'An unexpected error occurred.'}`,
        },
      ]);
    } finally {
      setIsSending(false);
    }
  };

  const handleWorkflowAction = async (
    action: 'pause' | 'resume' | 'advance' | 'abandon',
    decisionOption?: string,
  ) => {
    if (!workflowSessionId || isSending) return;
    const selectedDecisionLabel = decisionOption
      ? workflowDecisionOptions.find((option) => option.option_code === decisionOption)?.option_label
      : undefined;
    let body: string | undefined;
    if (action === 'abandon') {
      const reason = window.prompt('Why are you abandoning this workflow?');
      if (!reason?.trim()) return;
      body = JSON.stringify({ reason: reason.trim() });
    } else if (action === 'advance') {
      body = JSON.stringify({
        decision_option: decisionOption,
        rule_results: {},
        values: {},
        use_fallback: false,
      });
    }
    if (selectedDecisionLabel) {
      setMessages((previous) => [
        ...previous,
        { sender: 'user', content: `Selected SOP outcome: ${selectedDecisionLabel}` },
      ]);
    }
    setIsSending(true);
    try {
      const updated = await apiClient<WorkflowAdvanceResponse>(
        `/copilot/session/${workflowSessionId}/${action}`,
        { method: 'POST', body },
      );
      setWorkflowSessionStatus(updated.status);
      let statusMessage = `Workflow session ${updated.status}.`;
      if (action === 'advance') {
        setWorkflowDecisionOptions(updated.active_decision_options || []);
        setActiveStepNumber(updated.active_step_number ?? undefined);
        setActiveStepTitle(updated.active_step_title ?? undefined);
        const outcomePrefix = selectedDecisionLabel
          ? `Outcome recorded: ${selectedDecisionLabel}. `
          : '';
        statusMessage = updated.status === 'completed'
          ? `${outcomePrefix}Workflow completed.`
          : updated.active_decision_options?.length
            ? `Step completed. Choose the next outcome from the active SOP below.`
            : updated.active_step_title
              ? `${outcomePrefix}Next step: ${updated.active_step_title}`
              : 'Step completed.';
      }
      setMessages((previous) => [
        ...previous,
        { sender: 'assistant', content: statusMessage },
      ]);
    } catch (err: any) {
      setMessages((previous) => [
        ...previous,
        { sender: 'assistant', content: err.message || `Unable to ${action} the workflow.` },
      ]);
    } finally {
      setIsSending(false);
    }
  };

  return (
    <div className="flex flex-col h-[calc(100vh-4rem)] bg-white">
      <header className="px-6 py-4 border-b border-gray-200 flex justify-between items-center bg-slate-50">
        <div>
          <h1 className="text-xl font-bold text-gray-800 flex items-center gap-2">
            WorkMate Copilot
            {conversationId && (
              <span className="text-xs bg-blue-100 text-blue-800 font-normal px-2 py-0.5 rounded">
                Session: {conversationId}
              </span>
            )}
          </h1>
          <p className="text-xs text-gray-500">Enterprise Operational Guidance Engine</p>
        </div>
        <div className="flex items-center space-x-2">
          {workflowSessionId && workflowSessionStatus === 'active' && (
            <>
              {workflowDecisionOptions.length === 0 && (
                <button onClick={() => handleWorkflowAction('advance')} className="text-xs border border-blue-200 text-blue-700 px-2.5 py-1 rounded bg-white">
                  Complete step
                </button>
              )}
              <button onClick={() => handleWorkflowAction('pause')} className="text-xs border px-2.5 py-1 rounded bg-white">
                Pause workflow
              </button>
            </>
          )}
          {workflowSessionId && workflowSessionStatus === 'paused' && (
            <button onClick={() => handleWorkflowAction('resume')} className="text-xs border px-2.5 py-1 rounded bg-white">
              Resume workflow
            </button>
          )}
          {workflowSessionId && ['active', 'paused'].includes(workflowSessionStatus || '') && (
            <button onClick={() => handleWorkflowAction('abandon')} className="text-xs border border-red-200 text-red-700 px-2.5 py-1 rounded bg-white">
              Abandon
            </button>
          )}
          <span className="text-xs bg-blue-50 text-blue-700 font-semibold px-2.5 py-1 rounded border border-blue-200">
            Role: {user?.role}
          </span>
          <span className="text-xs bg-gray-100 text-gray-700 px-2.5 py-1 rounded border border-gray-200">
            Dept: {user?.department_id || 'GENERAL'}
          </span>
        </div>
      </header>
      {workflowSessionId
        && ['active', 'paused'].includes(workflowSessionStatus || '')
        && activeStepTitle
        && (activeStepNumber != null || workflowDecisionOptions.length > 0) && (
        <section
          aria-label="Current workflow step"
          aria-live="polite"
          className="mx-4 mt-4 flex-none rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 text-blue-950"
        >
          <div className="text-xs font-semibold uppercase tracking-wide text-blue-700">
            {activeStepNumber != null ? `Current step ${activeStepNumber}` : 'Decision required'}
          </div>
          <p className="mt-1 text-sm font-medium">{activeStepTitle}</p>
          {workflowDecisionOptions.length === 0 ? (
            <p className="mt-1 text-xs text-blue-700">
              Complete this step only, then type &quot;done&quot; or select Complete step to continue.
            </p>
          ) : (
            <div className="mt-2">
              <p className="text-xs text-blue-700">
                These outcomes come directly from the active SOP. Select the result you observed:
              </p>
              <div className="mt-2 flex flex-wrap gap-2" aria-label="Verified SOP outcomes">
                {workflowDecisionOptions.map((option) => (
                  <button
                    key={option.option_code}
                    type="button"
                    disabled={isSending}
                    onClick={() => handleWorkflowAction('advance', option.option_code)}
                    className="rounded-md border border-blue-300 bg-white px-3 py-2 text-left text-xs font-medium text-blue-900 hover:bg-blue-100 disabled:opacity-50"
                  >
                    {option.option_label}
                  </button>
                ))}
              </div>
            </div>
          )}
        </section>
      )}
      <main className="min-h-0 flex-1 overflow-hidden p-4">
        <ChatThread messages={messages} />
      </main>
      <footer className="flex-none p-4 border-t border-gray-200 bg-slate-50">
        <div className="flex space-x-2">
          <input
            type="text"
            className="flex-1 border border-gray-300 rounded-lg px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
            placeholder={
              isSending
                ? 'Copilot is processing...'
                : activeStepNumber != null
                  ? 'Ask about this step or type "done"...'
                  : workflowDecisionOptions.length > 0
                    ? 'Ask about the decision or select a verified outcome above...'
                    : 'Type your operational question...'
            }
            value={input}
            disabled={isSending}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSend()}
          />
          <button
            onClick={handleSend}
            disabled={isSending}
            className="bg-blue-600 text-white px-5 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 transition disabled:opacity-50"
          >
            {isSending ? 'Sending...' : 'Send'}
          </button>
        </div>
      </footer>
    </div>
  );
}

export default function CopilotPage() {
  return (
    <Suspense fallback={<div className="p-8">Loading Copilot...</div>}>
      <CopilotContent />
    </Suspense>
  );
}
