'use client';

import React, { useEffect, useState } from 'react';
import { AlertCircle, ArrowRight, CircleCheck, HelpCircle, TrendingUp } from 'lucide-react';
import { useRequireRole } from '@/lib/auth';
import { apiClient } from '@/lib/api-client';
import { MetricCard } from '@/components/dashboard/MetricCard';
import { PageHeader } from '@/components/shared/PageHeader';
import { LoadingState } from '@/components/shared/LoadingState';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { ConfirmDialog } from '@/components/shared/ConfirmDialog';

type AnalyticsRow = Record<string, any>;

function EmptyMetric({ children }: { children: React.ReactNode }) {
  return <div className="grid min-h-36 place-items-center rounded-xl border border-dashed bg-muted/25 p-5 text-center text-xs leading-5 text-muted-foreground">{children}</div>;
}

export default function IntelligenceHubPage() {
  const { loading } = useRequireRole(['manager', 'admin']);
  const [sopUsage, setSopUsage] = useState<AnalyticsRow[]>([]);
  const [confusingProcedures, setConfusingProcedures] = useState<AnalyticsRow[]>([]);
  const [departmentAdoption, setDepartmentAdoption] = useState<AnalyticsRow[]>([]);
  const [confidenceTrends, setConfidenceTrends] = useState<AnalyticsRow[]>([]);
  const [faqs, setFaqs] = useState<AnalyticsRow[]>([]);
  const [escalations, setEscalations] = useState<AnalyticsRow[]>([]);
  const [dataLoading, setDataLoading] = useState(true);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [resolutionId, setResolutionId] = useState<string | null>(null);
  const [resolutionNote, setResolutionNote] = useState('');
  const [resolving, setResolving] = useState(false);

  useEffect(() => {
    if (loading) return;
    Promise.all([
      apiClient<AnalyticsRow[]>('/analytics/sop-usage'),
      apiClient<AnalyticsRow[]>('/analytics/confusing-procedures'),
      apiClient<AnalyticsRow[]>('/analytics/department-adoption'),
      apiClient<AnalyticsRow[]>('/analytics/confidence-trends'),
      apiClient<AnalyticsRow[]>('/analytics/faqs'),
      apiClient<AnalyticsRow[]>('/analytics/escalations'),
    ])
      .then(([usage, confusing, adoption, trends, topics, escalationRows]) => {
        setSopUsage(Array.isArray(usage) ? usage : []);
        setConfusingProcedures(Array.isArray(confusing) ? confusing : []);
        setDepartmentAdoption(Array.isArray(adoption) ? adoption : []);
        setConfidenceTrends(Array.isArray(trends) ? trends : []);
        setFaqs(Array.isArray(topics) ? topics : []);
        setEscalations(Array.isArray(escalationRows) ? escalationRows : []);
      })
      .catch((caught) => setFetchError(caught instanceof Error ? caught.message : 'Failed to connect to analytics service.'))
      .finally(() => setDataLoading(false));
  }, [loading]);

  if (loading || dataLoading) return <LoadingState label="Loading intelligence hub" />;

  const totalExecutions = sopUsage.reduce((total, row) => total + (row.total_executions || 0), 0);
  const avgConfidence = confidenceTrends.length ? `${(confidenceTrends.reduce((total, row) => total + (row.avg_confidence_score || 0), 0) / confidenceTrends.length * 100).toFixed(1)}%` : 'No data';
  const avgAdoptionRate = departmentAdoption.length ? `${(departmentAdoption.reduce((total, row) => total + (row.adoption_rate_pct || 0), 0) / departmentAdoption.length).toFixed(0)}%` : 'No data';
  const openEscalations = escalations.filter((row) => row.escalation_status !== 'resolved').length;

  const resolveEscalation = async () => {
    if (!resolutionId || !resolutionNote.trim()) return;
    setResolving(true);
    try {
      await apiClient(`/escalations/${resolutionId}/resolve`, { method: 'POST', body: JSON.stringify({ resolution_note: resolutionNote.trim() }) });
      setEscalations((current) => current.map((item) => item.escalation_id === resolutionId ? { ...item, escalation_status: 'resolved' } : item));
      setResolutionId(null);
      setResolutionNote('');
    } catch (caught) {
      setFetchError(caught instanceof Error ? caught.message : 'Failed to resolve escalation.');
    } finally {
      setResolving(false);
    }
  };

  return (
    <div className="wm-page space-y-7">
      <PageHeader eyebrow="Operational intelligence" title="Manager overview" description="A focused view of SOP adoption, confidence, confusion, and human escalation across active operations." />

      {fetchError ? <div role="alert" className="flex gap-3 rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-700"><AlertCircle className="mt-0.5 h-5 w-5 flex-none" /><div><p className="font-semibold">Some analytics are unavailable</p><p className="mt-1">{fetchError}</p></div></div> : null}

      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4" aria-label="Operational metrics">
        <MetricCard title="SOP executions" value={fetchError ? 'N/A' : totalExecutions || 'No data'} />
        <MetricCard title="Response confidence" value={fetchError ? 'N/A' : avgConfidence} />
        <MetricCard title="Flagged procedures" value={fetchError ? 'N/A' : confusingProcedures.length} />
        <MetricCard title="Department adoption" value={fetchError ? 'N/A' : avgAdoptionRate} />
      </section>

      <section className="grid gap-4 xl:grid-cols-[1.15fr_0.85fr]">
        <Card>
          <CardHeader className="flex-row items-start justify-between"><div><CardTitle>Confidence performance</CardTitle><CardDescription>Latest measured grounded-answer quality</CardDescription></div><span className="grid h-9 w-9 place-items-center rounded-xl bg-emerald-50 text-emerald-700"><TrendingUp className="h-4 w-4" /></span></CardHeader>
          <CardContent>
            {confidenceTrends.length === 0 ? <EmptyMetric>No confidence trends recorded yet.</EmptyMetric> : <div className="space-y-4">{confidenceTrends.slice(0, 7).map((item, index) => { const score = Math.max(0, Math.min(100, (item.avg_confidence_score || 0) * 100)); return <div key={`${item.metric_date}-${index}`}><div className="mb-1.5 flex items-center justify-between text-xs"><span className="text-muted-foreground">{item.metric_date}</span><span className="font-semibold text-foreground">{score.toFixed(1)}%</span></div><div className="h-2 overflow-hidden rounded-full bg-muted"><div className="h-full rounded-full bg-emerald-600" style={{ width: `${score}%` }} /></div></div>; })}</div>}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex-row items-start justify-between"><div><CardTitle>Attention required</CardTitle><CardDescription>Procedures with elevated confusion</CardDescription></div><Badge variant={confusingProcedures.length ? 'danger' : 'default'}>{confusingProcedures.length} flagged</Badge></CardHeader>
          <CardContent>
            {confusingProcedures.length === 0 ? <EmptyMetric>No procedures currently exceed the escalation threshold.</EmptyMetric> : <ul className="divide-y">{confusingProcedures.slice(0, 7).map((procedure, index) => <li key={`${procedure.sop_id}-${index}`} className="flex items-center justify-between gap-4 py-3 first:pt-0"><div className="min-w-0"><p className="truncate text-xs font-semibold">{procedure.sop_title || `SOP ${procedure.sop_id}`}</p><p className="mt-0.5 text-[10px] text-muted-foreground">Needs content review</p></div><Badge variant="danger">{procedure.confusion_rate_pct || 0}%</Badge></li>)}</ul>}
          </CardContent>
        </Card>
      </section>

      <section className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader className="flex-row items-start justify-between"><div><CardTitle>Frequently asked topics</CardTitle><CardDescription>What employees need help with most</CardDescription></div><HelpCircle className="h-4 w-4 text-muted-foreground" /></CardHeader>
          <CardContent>{faqs.length === 0 ? <EmptyMetric>No categorized employee questions yet.</EmptyMetric> : <ul className="divide-y">{faqs.slice(0, 10).map((item, index) => <li key={`${item.department_id}-${item.query_topic}-${index}`} className="flex items-center justify-between gap-4 py-3 first:pt-0"><span className="min-w-0 truncate text-xs font-medium">{item.query_topic}</span><span className="flex-none text-[10px] text-muted-foreground">{item.query_count} · {item.department_id}</span></li>)}</ul>}</CardContent>
        </Card>

        <Card>
          <CardHeader className="flex-row items-start justify-between"><div><CardTitle>Escalation queue</CardTitle><CardDescription>Supervisor review and resolution</CardDescription></div><Badge variant={openEscalations ? 'warning' : 'default'}>{openEscalations} open</Badge></CardHeader>
          <CardContent>{escalations.length === 0 ? <EmptyMetric>No escalation records.</EmptyMetric> : <ul className="divide-y">{escalations.slice(0, 10).map((item) => <li key={item.escalation_id} className="py-3 first:pt-0"><div className="flex items-start justify-between gap-3"><div className="min-w-0"><p className="truncate text-xs font-semibold">{item.sop_title || 'General Copilot request'}</p><p className="mt-1 line-clamp-2 text-[10px] leading-4 text-muted-foreground">{item.escalation_reason}</p></div><Badge variant={item.escalation_status === 'resolved' ? 'default' : 'warning'}>{item.escalation_status}</Badge></div>{item.escalation_status !== 'resolved' ? <Button size="sm" variant="ghost" onClick={() => setResolutionId(item.escalation_id)} className="mt-2 h-7 px-2 text-[10px] text-emerald-700">Resolve <ArrowRight className="h-3 w-3" /></Button> : <span className="mt-2 inline-flex items-center gap-1 text-[10px] font-semibold text-emerald-700"><CircleCheck className="h-3 w-3" />Resolved</span>}</li>)}</ul>}</CardContent>
        </Card>
      </section>
      <ConfirmDialog open={Boolean(resolutionId)} tone="default" title="Resolve this escalation" description="Record what the supervisor confirmed so the resolution remains auditable." confirmLabel="Save resolution" busy={resolving} value={resolutionNote} valueLabel="Resolution note" valuePlaceholder="Describe the verified resolution…" onValueChange={setResolutionNote} onConfirm={resolveEscalation} onClose={() => { if (!resolving) { setResolutionId(null); setResolutionNote(''); } }} />
    </div>
  );
}
