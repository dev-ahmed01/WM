'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { ArrowUpRight, Clock3, History, MessageSquareText, Plus } from 'lucide-react';
import { useRequireRole } from '@/lib/auth';
import { apiClient, type CopilotHistoryResponse } from '@/lib/api-client';
import { PageHeader } from '@/components/shared/PageHeader';
import { LoadingState } from '@/components/shared/LoadingState';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';

export default function CopilotHistoryPage() {
  const { loading: authLoading } = useRequireRole(['employee', 'admin', 'manager']);
  const [historyData, setHistoryData] = useState<CopilotHistoryResponse | null>(null);
  const [loadingData, setLoadingData] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (authLoading) return;
    apiClient<CopilotHistoryResponse>('/copilot/history')
      .then(setHistoryData)
      .catch((caught) => setError(caught instanceof Error ? caught.message : 'Failed to load conversation history.'))
      .finally(() => setLoadingData(false));
  }, [authLoading]);

  if (authLoading || loadingData) return <LoadingState label="Loading session history" />;
  const sessions = historyData?.sessions || [];

  return (
    <div className="wm-page space-y-7">
      <PageHeader
        eyebrow="Continuity"
        title="Session history"
        description="Return to earlier operational conversations with their workflow context intact."
        action={<Button asChild><Link href="/copilot"><Plus className="h-4 w-4" />New session</Link></Button>}
      />

      {error ? <div role="alert" className="rounded-2xl border border-red-200 bg-red-50 p-5 text-sm text-red-700"><p className="font-semibold">History unavailable</p><p className="mt-1">{error}</p></div> : null}

      {!error && sessions.length === 0 ? (
        <div className="wm-panel grid min-h-80 place-items-center p-8 text-center">
          <div><span className="mx-auto grid h-12 w-12 place-items-center rounded-2xl bg-emerald-50 text-emerald-700"><History className="h-5 w-5" /></span><h2 className="mt-4 text-lg font-semibold">No sessions yet</h2><p className="mx-auto mt-2 max-w-sm text-sm leading-6 text-muted-foreground">Start with an operational question and WorkMate will keep the conversation here for later.</p><Button asChild className="mt-5"><Link href="/copilot">Open Copilot</Link></Button></div>
        </div>
      ) : null}

      {sessions.length > 0 ? (
        <div className="grid gap-3">
          {sessions.map((session) => {
            const date = session.started_at ? new Date(session.started_at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }) : 'Recently';
            return (
              <Link key={session.id} href={`/copilot?session=${encodeURIComponent(session.id)}`} className="group wm-panel flex flex-col gap-4 p-4 transition hover:-translate-y-0.5 hover:border-emerald-200 hover:shadow-lift sm:flex-row sm:items-center sm:p-5">
                <span className="grid h-11 w-11 flex-none place-items-center rounded-xl bg-muted text-muted-foreground transition group-hover:bg-emerald-50 group-hover:text-emerald-700"><MessageSquareText className="h-5 w-5" /></span>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2"><h2 className="truncate text-sm font-semibold text-foreground">{session.title || 'Operational guidance session'}</h2><Badge variant={session.status === 'active' ? 'default' : 'neutral'}>{session.status || 'active'}</Badge></div>
                  {session.last_message_preview ? <p className="mt-1.5 line-clamp-1 text-xs text-muted-foreground">{session.last_message_preview}</p> : null}
                  <div className="mt-2 flex flex-wrap items-center gap-3 text-[10px] text-muted-foreground"><span className="inline-flex items-center gap-1"><Clock3 className="h-3 w-3" />{date}</span><span className="font-mono">{session.id}</span></div>
                </div>
                <span className="grid h-9 w-9 flex-none place-items-center rounded-xl border bg-white text-muted-foreground transition group-hover:border-emerald-200 group-hover:text-emerald-700"><ArrowUpRight className="h-4 w-4" /></span>
              </Link>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}
