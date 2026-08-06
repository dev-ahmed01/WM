'use client';

import React, { useState, useEffect, Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import { useRequireRole } from '@/lib/auth';
import { ChatThread } from '@/components/chat/ChatThread';
import { apiClient, CopilotResponse } from '@/lib/api-client';

function CopilotContent() {
  const { user, loading } = useRequireRole(['employee', 'admin', 'manager']);
  const searchParams = useSearchParams();
  const sessionId = searchParams.get('session');

  const [input, setInput] = useState('');
  const [conversationId, setConversationId] = useState<string | undefined>(sessionId || undefined);
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
        await apiClient(`/copilot/session/${sessionId}/resume`, {
          method: 'POST',
        });

        setConversationId(sessionId);
        setMessages([
          {
            sender: 'assistant',
            content: `Resumed active session context: "${sessionId}". Ready for your operational queries.`,
          },
        ]);
      } catch (err: any) {
        console.error('Failed to resume session:', err);
        // Fall back gracefully if session state endpoint fails
        setConversationId(sessionId);
        setMessages([
          {
            sender: 'assistant',
            content: `Loaded conversation session ID "${sessionId}". You can continue asking questions.`,
          },
        ]);
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
          <span className="text-xs bg-blue-50 text-blue-700 font-semibold px-2.5 py-1 rounded border border-blue-200">
            Role: {user?.role}
          </span>
          <span className="text-xs bg-gray-100 text-gray-700 px-2.5 py-1 rounded border border-gray-200">
            Dept: {user?.department_id || 'GENERAL'}
          </span>
        </div>
      </header>
      <main className="flex-1 overflow-hidden p-4">
        <ChatThread messages={messages} />
      </main>
      <footer className="p-4 border-t border-gray-200 bg-slate-50">
        <div className="flex space-x-2">
          <input
            type="text"
            className="flex-1 border border-gray-300 rounded-lg px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
            placeholder={isSending ? 'Copilot is processing...' : 'Type your operational question...'}
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
