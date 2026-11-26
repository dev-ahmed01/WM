'use client';

import React, { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { ArrowLeft } from 'lucide-react';
import { useRequireRole } from '@/lib/auth';
import { apiClient } from '@/lib/api-client';
import { CaseThread, type CaseSummary } from '@/components/cases/CaseThread';
import { MyReportedIssues } from '@/components/work/MyReportedIssues';
import { EmptyState, ErrorNote, PageTitle, StatusPill, buttonQuiet, relativeDate } from '@/components/shared/ui';
import { LoadingState } from '@/components/shared/LoadingState';

export default function EmployeeEscalations() {
  const { loading } = useRequireRole(['employee', 'manager', 'admin']);
  const [items, setItems] = useState<CaseSummary[] | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try { setItems((await apiClient<{ items: CaseSummary[] }>('/my/cases')).items); setError(null); }
    catch { setError('Could not load your requests.'); setItems([]); }
  }, []);
  useEffect(() => { if (!loading) void load(); }, [loading, load]);

  if (loading || items === null) return <LoadingState label="Loading your requests" />;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className={`${selected ? 'hidden lg:block' : ''} px-4 pt-6 sm:px-6 lg:px-8 lg:pt-8`}>
        <PageTitle title="Escalations" hint="Requests you sent to a person, and what came back." />
      </div>

      <div className="mt-5 grid min-h-0 flex-1 lg:grid-cols-[22rem_minmax(0,1fr)]">
        <div className={`${selected ? 'hidden lg:block' : ''} min-h-0 overflow-y-auto border-border px-4 pb-6 sm:px-6 lg:border-r lg:px-4`}>
          {error ? <ErrorNote>{error}</ErrorNote> : null}
          {items.length === 0 && !error ? (
            <EmptyState title="Nothing here yet" hint="When an answer is not enough, choose “Ask a person” under it. Your request and the reply will appear here."
              action={<Link href="/copilot" className={buttonQuiet}>Back to the assistant</Link>} />
          ) : (
            <ul className="divide-y divide-border" aria-label="Your requests">
              {items.map((c) => (
                <li key={c.id}>
                  <button type="button" onClick={() => setSelected(c.id)} aria-current={selected === c.id}
                    className={`block w-full px-3 py-3.5 text-left transition hover:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring ${selected === c.id ? 'bg-accent/50' : ''}`}>
                    <div className="flex items-center justify-between gap-2">
                      <StatusPill status={c.public_status} />
                      <span className="text-xs text-muted-foreground">{relativeDate(c.updated_at)}</span>
                    </div>
                    <p className="mt-2 line-clamp-2 text-sm font-medium">{c.title}</p>
                    <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">
                      {c.latest_reply ? <>Reply: {c.latest_reply}</> : c.assignee_name ? <>With {c.assignee_name}</> : 'Waiting for a reply'}
                    </p>
                  </button>
                </li>
              ))}
            </ul>
          )}
          <div className="mt-6"><MyReportedIssues /></div>
        </div>

        <div className={`${selected ? '' : 'hidden lg:grid'} min-h-0 lg:place-items-stretch`}>
          {selected ? (
            <div className="flex h-full min-h-0 flex-col">
              <button type="button" onClick={() => setSelected(null)} className="flex h-11 items-center gap-2 px-4 text-sm text-muted-foreground lg:hidden">
                <ArrowLeft className="h-4 w-4" /> All requests
              </button>
              <div className="min-h-0 flex-1"><CaseThread key={selected} caseId={selected} mode="employee" onChanged={() => void load()} /></div>
            </div>
          ) : (
            <div className="hidden place-items-center text-sm text-muted-foreground lg:grid">Select a request to read the replies.</div>
          )}
        </div>
      </div>
    </div>
  );
}
