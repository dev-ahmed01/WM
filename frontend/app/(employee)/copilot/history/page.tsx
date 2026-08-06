'use client';

import React, { useEffect, useState } from 'react';
import { useRequireRole } from '@/lib/auth';
import { apiClient, CopilotHistoryResponse, CopilotSessionSummary } from '@/lib/api-client';
import Link from 'next/link';
import { ArrowRight, History } from 'lucide-react';

export default function CopilotHistoryPage() {
  const { loading: authLoading } = useRequireRole(['employee', 'admin', 'manager']);
  const [historyData, setHistoryData] = useState<CopilotHistoryResponse | null>(null);
  const [loadingData, setLoadingData] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchHistory() {
      try {
        setLoadingData(true);
        setError(null);
        const res = await apiClient<CopilotHistoryResponse>('/copilot/history');
        setHistoryData(res);
      } catch (err: any) {
        console.error('Failed to load copilot session history:', err);
        setError(err?.message || 'Failed to load conversation history.');
      } finally {
        setLoadingData(false);
      }
    }

    if (!authLoading) {
      fetchHistory();
    }
  }, [authLoading]);

  if (authLoading || loadingData) {
    return <div className="p-8">Loading session history...</div>;
  }

  if (error) {
    return (
      <div className="p-8 max-w-4xl mx-auto">
        <h1 className="text-2xl font-bold text-gray-900 mb-6">Copilot Conversation History</h1>
        <div className="bg-red-50 border border-red-200 text-red-700 p-4 rounded-md">
          <p className="font-semibold">Error Loading History</p>
          <p className="text-sm">{error}</p>
        </div>
      </div>
    );
  }

  const sessions = historyData?.sessions || [];

  return (
    <div className="p-8 max-w-4xl mx-auto">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
            <History className="h-6 w-6 text-blue-600" />
            Copilot Session History
          </h1>
          <p className="text-sm text-gray-500 mt-1">Select a past session card to resume context and operational guidance.</p>
        </div>
        <Link
          href="/copilot"
          className="bg-blue-600 text-white px-4 py-2 rounded text-sm font-medium hover:bg-blue-700 transition"
        >
          New Chat
        </Link>
      </div>

      {sessions.length === 0 ? (
        <div className="bg-white border border-gray-200 rounded-lg p-12 text-center text-gray-500">
          <p className="text-lg font-medium mb-2">No Past Conversations</p>
          <p className="text-sm mb-4">You have not started any Copilot operational guidance sessions yet.</p>
          <Link
            href="/copilot"
            className="inline-block bg-blue-600 text-white px-4 py-2 rounded text-sm font-medium hover:bg-blue-700 transition"
          >
            Start Copilot Session
          </Link>
        </div>
      ) : (
        <div className="space-y-4">
          {sessions.map((sess: CopilotSessionSummary) => {
            const formattedDate = sess.started_at
              ? new Date(sess.started_at).toLocaleString()
              : 'Recently';
            const statusUpper = sess.status ? sess.status.charAt(0).toUpperCase() + sess.status.slice(1) : 'Active';

            return (
              <Link
                key={sess.id}
                href={`/copilot?session=${encodeURIComponent(sess.id)}`}
                className="block p-5 bg-white border border-gray-200 rounded-xl hover:border-blue-500 hover:shadow-md transition group"
              >
                <div className="flex justify-between items-center mb-1">
                  <span className="font-semibold text-gray-900 group-hover:text-blue-600 transition flex items-center gap-2">
                    {sess.title || `Session #${sess.id}`}
                    <ArrowRight className="h-4 w-4 opacity-0 group-hover:opacity-100 transition-opacity text-blue-600" />
                  </span>
                  <span className="text-xs text-gray-400">{formattedDate}</span>
                </div>
                <p className="text-sm text-gray-600">
                  Session ID: <code className="bg-slate-100 px-1 py-0.5 rounded text-xs">{sess.id}</code> • Status:{' '}
                  <span className="font-medium text-slate-800">{statusUpper}</span>
                </p>
                {sess.last_message_preview && (
                  <p className="text-xs text-gray-500 italic mt-2 border-t pt-2 border-gray-100">
                    &quot;{sess.last_message_preview}&quot;
                  </p>
                )}
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
