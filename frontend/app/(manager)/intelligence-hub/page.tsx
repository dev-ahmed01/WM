'use client';

import React, { useEffect, useState } from 'react';
import { useRequireRole } from '@/lib/auth';
import { apiClient } from '@/lib/api-client';
import { EmptyState, ErrorNote, Page, PageTitle, inputClass } from '@/components/shared/ui';
import { LoadingState } from '@/components/shared/LoadingState';

interface Summary { top_questions: { question: string; count: number; people: number }[]; metrics: Record<string, number | null>; definitions: Record<string, string>; unavailable: Record<string, string> }
type Row = Record<string, any>;
interface Dept { id: string; name: string }

const pct = (v: number | null | undefined) => (v == null ? '—' : `${v}%`);
const hours = (v: number | null | undefined) => (v == null ? '—' : v < 1 ? `${Math.round(v * 60)} min` : `${v} h`);

function Stat({ label, value, hint }: { label: string; value: React.ReactNode; hint?: string }) {
  return (
    <div className="rounded-xl border border-border bg-card p-4" title={hint}>
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className="mt-1.5 font-display text-2xl font-semibold tabular-nums">{value}</p>
    </div>
  );
}

function Bars({ items, empty }: { items: { label: string; value: number }[]; empty: string }) {
  const max = Math.max(1, ...items.map((i) => i.value));
  if (!items.length) return <p className="px-4 py-6 text-sm text-muted-foreground">{empty}</p>;
  return (
    <ul className="space-y-3 p-4">
      {items.map((i) => (
        <li key={i.label}>
          <div className="flex items-baseline justify-between gap-3 text-sm"><span className="line-clamp-1">{i.label}</span><span className="flex-none tabular-nums text-muted-foreground">{i.value}</span></div>
          <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-muted" role="presentation"><div className="h-full rounded-full bg-primary" style={{ width: `${Math.max(3, (i.value / max) * 100)}%` }} /></div>
        </li>
      ))}
    </ul>
  );
}

function Card({ title, note, children }: { title: string; note?: string; children: React.ReactNode }) {
  return (
    <section className="rounded-xl border border-border bg-card">
      <div className="px-4 pt-4"><h2 className="font-display text-base font-semibold">{title}</h2>{note ? <p className="mt-0.5 text-xs text-muted-foreground">{note}</p> : null}</div>
      {children}
    </section>
  );
}

export default function Analytics() {
  const { user, loading } = useRequireRole(['manager', 'admin']);
  const [days, setDays] = useState(30);
  const [department, setDepartment] = useState('');
  const [departments, setDepartments] = useState<Dept[]>([]);
  const [data, setData] = useState<Summary | null>(null);
  const [sops, setSops] = useState<Row[]>([]);
  const [adoption, setAdoption] = useState<Row[]>([]);
  const [gaps, setGaps] = useState<Row[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { if (!loading && user?.role === 'admin') void apiClient<Dept[]>('/knowledge/departments').then(setDepartments).catch(() => setDepartments([])); }, [loading, user?.role]);

  useEffect(() => {
    if (loading) return;
    let live = true;
    const dep = department ? `&department_id=${encodeURIComponent(department)}` : '';
    const depOnly = department ? `?department_id=${encodeURIComponent(department)}` : '';
    setError(null);
    void Promise.all([
      apiClient<Summary>(`/analytics/summary?days=${days}${dep}`),
      apiClient<Row[]>(`/analytics/sop-usage${depOnly}`).catch(() => []),
      apiClient<Row[]>(`/analytics/department-adoption${depOnly}`).catch(() => []),
      apiClient<{ items: Row[] }>(`/cases?view=unanswered&limit=8${department ? `&department=${encodeURIComponent(department)}` : ''}`).then((r) => r.items).catch(() => []),
    ]).then(([s, u, a, g]) => { if (live) { setData(s); setSops(Array.isArray(u) ? u : []); setAdoption(Array.isArray(a) ? a : []); setGaps(g); } })
      .catch(() => live && setError('Analytics could not be loaded.'));
    return () => { live = false; };
  }, [loading, days, department]);

  if (loading) return <LoadingState label="Loading analytics" />;
  const m = data?.metrics;

  return (
    <Page wide>
      <PageTitle title="Analytics" hint="Counted from what employees actually did. Nothing here is estimated."
        action={<div className="flex gap-2">
          {departments.length > 1 ? <select value={department} onChange={(e) => setDepartment(e.target.value)} aria-label="Department" className={`${inputClass} !w-auto`}><option value="">All departments</option>{departments.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}</select> : null}
          <select value={days} onChange={(e) => setDays(Number(e.target.value))} aria-label="Period" className={`${inputClass} !w-auto`}><option value={7}>Last 7 days</option><option value={30}>Last 30 days</option><option value={90}>Last 90 days</option></select>
        </div>} />
      {error ? <ErrorNote>{error}</ErrorNote> : null}
      {!m ? <LoadingState label="Loading analytics" /> : (
        <>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <Stat label="Employee adoption" value={m.active_employees ?? 0} hint={data?.definitions.active_employees} />
            <Stat label="Question volume" value={m.questions_received ?? 0} hint={data?.definitions.questions_received} />
            <Stat label="Confirmed resolution" value={pct(m.self_service_resolution_pct)} hint={data?.definitions.self_service_resolution_pct} />
            <Stat label="Escalation rate" value={m.conversations_total ? pct(Math.round(((m.cases_opened ?? 0) / (m.conversations_total || 1)) * 1000) / 10) : '—'} hint="Requests for a person, unanswered questions and flagged answers per conversation." />
          </div>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <Stat label="Median response from staff" value={hours(m.median_escalation_resolution_hours ?? null)} hint={data?.definitions.median_escalation_resolution_hours} />
            <Stat label="Median time to resolve a request" value={hours(m.median_case_resolution_hours ?? null)} hint={data?.definitions.median_case_resolution_hours} />
            <Stat label="Answers rated helpful" value={`${m.answers_rated_helpful ?? 0} of ${(m.answers_rated_helpful ?? 0) + (m.answers_rated_not_helpful ?? 0)}`} hint="Only answers employees rated." />
            <Stat label="Procedures completed" value={`${m.workflows_completed ?? 0} of ${m.workflows_started ?? 0}`} hint={data?.definitions.workflow_completion_rate_pct} />
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card title="Common questions"><Bars empty="No questions yet." items={(data?.top_questions ?? []).map((q) => ({ label: q.question, value: q.count }))} /></Card>
            <Card title="Most used procedures"><Bars empty="No procedure has been started yet." items={sops.slice(0, 8).map((s) => ({ label: String(s.sop_title ?? s.title ?? ''), value: Number(s.total_executions ?? s.executions ?? s.sessions ?? 0) })).filter((x) => x.value > 0)} /></Card>
            <Card title="Unanswered topics" note="Questions with no approved procedure.">
              {gaps.length === 0 ? <p className="px-4 py-6 text-sm text-muted-foreground">Nothing is unanswered right now.</p> : <ul className="divide-y divide-border pt-2">{gaps.map((g) => <li key={g.id} className="px-4 py-2.5 text-sm">{g.title}</li>)}</ul>}
            </Card>
            <Card title="Language used" note="Hindi written in English letters cannot be told from English, so it counts as English letters.">
              <Bars empty="No messages yet." items={[{ label: 'Hindi (Devanagari)', value: m.messages_in_devanagari ?? 0 }, { label: 'English letters (English or Hinglish)', value: m.messages_in_latin_script ?? 0 }].filter((x) => x.value > 0)} />
            </Card>
            <Card title="Department adoption" note="Share of the department's people who used WorkMate.">
              {adoption.length === 0 ? <EmptyState title="No department data" /> : <Bars empty="No data." items={adoption.slice(0, 8).map((a) => ({ label: String(a.department_id ?? a.department ?? '').replace(/[_-]+/g, ' '), value: Math.round(Number(a.adoption_rate_pct ?? 0)) }))} />}
            </Card>
            <Card title="Not measured" note="Shown so nobody mistakes a missing number for a good one.">
              <ul className="space-y-2 p-4 text-sm text-muted-foreground">{Object.entries(data?.unavailable ?? {}).map(([k, v]) => <li key={k}><span className="font-medium text-foreground">{k.replace(/_/g, ' ')}:</span> {v}</li>)}</ul>
            </Card>
          </div>
        </>
      )}
    </Page>
  );
}
