'use client';

import { useEffect, useState } from 'react';
import { useRequireRole } from '@/lib/auth';
import { apiClient } from '@/lib/api-client';
import { PageHeader } from '@/components/shared/PageHeader';
import { LoadingState } from '@/components/shared/LoadingState';

interface PilotSummary {
  window_days: number;
  total: number;
  helpful: number;
  needs_review: number;
  counts: Array<{ surface: string; verdict: string; issue: string; count: number }>;
  privacy: string;
}

export default function PilotReviewPage() {
  const { user, loading } = useRequireRole(['admin', 'manager']);
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [summary, setSummary] = useState<PilotSummary | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    if (loading || !user) return;
    let active = true;
    async function load() {
      try {
        const config = await apiClient<{ feedback_enabled: boolean }>('/pilot/config');
        if (!active) return;
        setEnabled(config.feedback_enabled);
        if (!config.feedback_enabled) return;
        const result = await apiClient<PilotSummary>('/pilot/summary?days=14');
        if (active) setSummary(result);
      } catch {
        if (active) setError('Pilot summary is unavailable. Try again later.');
      }
    }
    void load();
    return () => { active = false; };
  }, [loading, user?.sub, user?.department_id]);

  if (loading) return <LoadingState label="Loading pilot review" />;
  return (
    <div className="wm-page space-y-6">
      <PageHeader eyebrow="Controlled pilot" title="Pilot review"
        description="Aggregated operator feedback from your department. This view contains no employee messages or voice transcripts." />
      {enabled === false ? <div className="rounded-2xl border bg-white p-6 text-sm text-slate-600">
        Pilot feedback is not enabled for this department. An administrator must configure an explicit pilot cohort.
      </div> : null}
      {error ? <p role="alert" className="rounded-xl bg-red-50 p-4 text-sm text-red-700">{error}</p> : null}
      {enabled && !summary && !error ? <LoadingState label="Loading pilot signals" /> : null}
      {summary ? (
        <>
          <section className="grid gap-4 sm:grid-cols-3" aria-label="Pilot summary">
            {[
              ['Feedback received', summary.total],
              ['Helpful', summary.helpful],
              ['Needs human review', summary.needs_review],
            ].map(([title, value]) => (
              <div key={title} className="rounded-2xl border border-slate-200 bg-white p-5">
                <p className="text-sm text-slate-500">{title}</p>
                <p className="mt-2 text-3xl font-semibold text-slate-900">{value}</p>
              </div>
            ))}
          </section>
          <section className="rounded-2xl border border-slate-200 bg-white p-5">
            <h2 className="font-semibold text-slate-900">Signals by issue and answer type</h2>
            <p className="mt-1 text-xs text-slate-500">Past {summary.window_days} days · only department-level counts</p>
            {summary.counts.length ? <div className="mt-4 divide-y divide-slate-100">
              {summary.counts.map(item => (
                <div key={item.surface + item.verdict + item.issue}
                  className="flex flex-wrap items-center justify-between gap-3 py-3 text-sm">
                  <span className="capitalize text-slate-700">{item.surface} · {item.issue.replaceAll('_', ' ')}</span>
                  <strong className="text-slate-900">{item.count}</strong>
                </div>
              ))}
            </div> : <p className="mt-4 text-sm text-slate-500">No feedback collected yet. This is not evidence of a passed pilot.</p>}
          </section>
          <p className="text-xs text-slate-500">Pilot feedback is a review signal, not a verified safety incident count or production acceptance decision.</p>
        </>
      ) : null}
    </div>
  );
}
