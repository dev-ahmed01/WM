'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { ArrowUpRight } from 'lucide-react';
import { useRequireRole } from '@/lib/auth';
import { apiClient } from '@/lib/api-client';
import { EmptyState, Page, PageTitle, StatusPill, relativeDate } from '@/components/shared/ui';
import { LoadingState } from '@/components/shared/LoadingState';

interface Summary { metrics: Record<string, number | null>; top_questions: { question: string; count: number }[] }
interface CaseRow { id: string; title: string; public_status: string; priority: string; reporter_name?: string; updated_at: string; kind: string }
interface CaseList { items: CaseRow[]; counts: { manager_open: number; unanswered: number } }
interface ExceptionRow { id: string; status: string; severity?: string; reason?: string; work_title?: string }

function Metric({ label, value, note }: { label: string; value: React.ReactNode; note?: string }) {
  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className="mt-2 font-display text-3xl font-semibold tabular-nums tracking-tight">{value}</p>
      {note ? <p className="mt-1 text-xs text-muted-foreground">{note}</p> : null}
    </div>
  );
}

function Section({ title, href, linkLabel, children }: { title: string; href?: string; linkLabel?: string; children: React.ReactNode }) {
  return (
    <section className="rounded-xl border border-border bg-card">
      <div className="flex items-center justify-between px-4 py-3">
        <h2 className="font-display text-base font-semibold">{title}</h2>
        {href ? <Link href={href} className="inline-flex items-center gap-1 text-sm text-primary hover:underline">{linkLabel ?? 'View all'}<ArrowUpRight className="h-3.5 w-3.5" /></Link> : null}
      </div>
      <div className="border-t border-border">{children}</div>
    </section>
  );
}

const pct = (v: number | null | undefined) => (v == null ? '—' : `${v}%`);

export default function ManagerOverview() {
  const { loading } = useRequireRole(['manager', 'admin']);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [cases, setCases] = useState<CaseList | null>(null);
  const [unanswered, setUnanswered] = useState<CaseRow[]>([]);
  const [blocked, setBlocked] = useState<ExceptionRow[]>([]);
  const [approvals, setApprovals] = useState(0);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (loading) return;
    const safe = <T,>(p: Promise<T>) => p.catch(() => { setFailed(true); return null; });
    void Promise.all([
      safe(apiClient<Summary>('/analytics/summary?days=30')),
      safe(apiClient<CaseList>('/cases?managed=true&view=all&limit=6')),
      safe(apiClient<CaseList>('/cases?view=unanswered&limit=5')),
      safe(apiClient<{ items: ExceptionRow[] }>('/work/exceptions?limit=100')),
      safe(apiClient<{ items: unknown[]; uploads: unknown[] }>('/procedure/approvals')),
    ]).then(([s, c, u, e, a]) => {
      setSummary(s); setCases(c); setUnanswered(u?.items ?? []);
      setBlocked((e?.items ?? []).filter((x) => x.status !== 'closed'));
      setApprovals((a?.items?.length ?? 0) + (a?.uploads?.length ?? 0));
    });
  }, [loading]);

  if (loading || !summary) return <LoadingState label="Loading overview" />;
  const m = summary.metrics;
  const openEscalations = (cases?.counts.manager_open ?? 0) + blocked.length;
  const attention = approvals + openEscalations;

  return (
    <Page wide>
      <PageTitle title="Overview" hint="The last 30 days across your department." />
      {failed ? <p role="alert" className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900">Some information could not be loaded, so a number below may be incomplete.</p> : null}

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Metric label="Active employees" value={m.active_employees ?? 0} note="Sent at least one message" />
        <Metric label="Questions received" value={m.questions_received ?? 0} />
        <Metric label="Self-service resolution" value={pct(m.self_service_resolution_pct)}
          note={`${m.conversations_confirmed_resolved ?? 0} of ${m.conversations_total ?? 0} conversations confirmed helpful`} />
        <Metric label="Open escalations" value={openEscalations} note={approvals ? `${approvals} SOP${approvals > 1 ? 's' : ''} waiting for your approval` : undefined} />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Section title="Needs your attention" href="/escalation-centre">
          {attention === 0 ? <div className="p-4"><EmptyState title="Nothing is waiting for you" hint="Requests escalated to you, blocked work and SOP approvals will appear here." /></div> : (
            <ul className="divide-y divide-border">
              {approvals > 0 ? (
                <li><Link href="/approvals" className="flex items-center justify-between gap-3 px-4 py-3 hover:bg-muted/50">
                  <span className="text-sm font-medium">{approvals} SOP{approvals > 1 ? 's' : ''} waiting for approval</span><ArrowUpRight className="h-4 w-4 text-muted-foreground" />
                </Link></li>
              ) : null}
              {blocked.length > 0 ? (
                <li><Link href="/escalation-centre?tab=blocked" className="flex items-center justify-between gap-3 px-4 py-3 hover:bg-muted/50">
                  <span className="text-sm font-medium">{blocked.length} blocked-work case{blocked.length > 1 ? 's' : ''} open</span><ArrowUpRight className="h-4 w-4 text-muted-foreground" />
                </Link></li>
              ) : null}
              {(cases?.items ?? []).filter((c) => !['resolved', 'closed'].includes(c.public_status)).map((c) => (
                <li key={c.id}><Link href="/escalation-centre" className="block px-4 py-3 hover:bg-muted/50">
                  <div className="flex items-center justify-between gap-2"><span className="line-clamp-1 text-sm font-medium">{c.title}</span><StatusPill status={c.public_status} /></div>
                  <p className="mt-0.5 text-xs text-muted-foreground">{c.reporter_name} · {relativeDate(c.updated_at)}</p>
                </Link></li>
              ))}
            </ul>
          )}
        </Section>

        <Section title="Common questions" href="/intelligence-hub" linkLabel="Analytics">
          {(summary.top_questions ?? []).length === 0 ? <div className="p-4"><EmptyState title="No questions yet" hint="Frequently asked questions appear once employees start using the assistant." /></div> : (
            <ol className="divide-y divide-border">
              {(summary.top_questions ?? []).slice(0, 5).map((f, i) => (
                <li key={i} className="flex items-center justify-between gap-3 px-4 py-3 text-sm">
                  <span className="line-clamp-1">{f.question}</span>
                  <span className="flex-none text-xs tabular-nums text-muted-foreground">{f.count}×</span>
                </li>
              ))}
            </ol>
          )}
        </Section>

        <Section title="Knowledge gaps" href="/escalation-centre" linkLabel="Escalations">
          {unanswered.length === 0 ? <div className="p-4"><EmptyState title="No unanswered questions" hint="Questions with no approved procedure are listed here so the gap can be closed." /></div> : (
            <ul className="divide-y divide-border">
              {unanswered.map((c) => (
                <li key={c.id} className="flex items-center justify-between gap-3 px-4 py-3">
                  <span className="line-clamp-1 text-sm">{c.title}</span><span className="flex-none text-xs text-muted-foreground">{relativeDate(c.updated_at)}</span>
                </li>
              ))}
            </ul>
          )}
        </Section>

        <Section title="Recent activity">
          <dl className="grid grid-cols-2 divide-x divide-y divide-border text-sm">
            {[
              ['Workflows completed', `${m.workflows_completed ?? 0} of ${m.workflows_started ?? 0} started`],
              ['Safety stops', m.safety_stops ?? 0],
              ['Requests resolved', `${m.cases_resolved ?? 0} of ${m.cases_opened ?? 0}`],
              ['Shift handovers', m.handovers_submitted ?? 0],
            ].map(([k, v]) => <div key={String(k)} className="px-4 py-3"><dt className="text-xs text-muted-foreground">{k}</dt><dd className="mt-1 font-medium tabular-nums">{v}</dd></div>)}
          </dl>
        </Section>
      </div>
    </Page>
  );
}
