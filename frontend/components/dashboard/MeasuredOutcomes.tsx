'use client';

import React, { useEffect, useState } from 'react';
import { apiClient } from '@/lib/api-client';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';

type Summary = {
  period_days: number;
  metrics: Record<string, number | null>;
  definitions: Record<string, string>;
  unavailable: Record<string, string>;
};
type Roi = {
  kind: string;
  estimated_questions_per_year: number;
  estimated_supervisor_interruptions_avoided: number;
  estimated_supervisor_hours_saved: number;
  estimated_cost_saved: number;
  caveat: string;
};

const LABELS: Record<string, string> = {
  active_employees: 'Active employees',
  questions_received: 'Messages from employees',
  matched_an_approved_sop: 'Matched an approved SOP',
  knowledge_gaps_raised: 'No approved SOP found',
  gap_rate_pct: 'Gap rate (%)',
  safety_stops: 'Safety stops',
  live_data_declined: 'Live-data questions declined',
  actions_confirmed: 'Discrepancy reports confirmed',
  workflows_started: 'Workflows started',
  workflows_completed: 'Workflows completed',
  workflow_completion_rate_pct: 'Completion rate (%)',
  escalations_opened: 'Escalations opened',
  escalations_resolved: 'Escalations resolved',
  median_escalation_resolution_hours: 'Median escalation time (h)',
  exception_cases_opened: 'Blocked-work cases opened',
  exception_cases_closed: 'Cases closed',
  median_exception_closure_hours: 'Median case closure (h)',
  gaps_closed_by_published_sop: 'Gaps closed by a published SOP',
  handovers_submitted: 'Handovers submitted',
};

const field = 'h-10 w-full rounded-lg border bg-background px-3 text-sm';

export function MeasuredOutcomes() {
  const [days, setDays] = useState(30);
  const [data, setData] = useState<Summary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [inputs, setInputs] = useState({ employees: 50, perWeek: 5, minutes: 4, share: 50, cost: 20 });
  const [roi, setRoi] = useState<Roi | null>(null);
  const [roiError, setRoiError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    setError(null);
    apiClient<Summary>(`/analytics/summary?days=${days}`)
      .then((r) => live && setData(r))
      .catch((e) => live && setError(e instanceof Error ? e.message : 'Measured outcomes are unavailable.'));
    return () => { live = false; };
  }, [days]);

  const estimate = async () => {
    setRoiError(null);
    try {
      setRoi(await apiClient<Roi>('/analytics/roi-estimate', {
        method: 'POST',
        body: JSON.stringify({
          employees: inputs.employees, questions_per_employee_per_week: inputs.perWeek,
          minutes_per_supervisor_interruption: inputs.minutes, share_answered_without_supervisor_pct: inputs.share,
          loaded_hourly_cost: inputs.cost,
        }),
      }));
    } catch (e) {
      setRoi(null);
      setRoiError(e instanceof Error ? e.message : 'Could not calculate the estimate.');
    }
  };

  const set = (key: keyof typeof inputs) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setInputs((s) => ({ ...s, [key]: Number(e.target.value) }));

  return (
    <section className="grid gap-4 xl:grid-cols-[1.4fr_0.9fr]" aria-label="Measured outcomes and estimate">
      <Card>
        <CardHeader className="flex-row items-start justify-between gap-3">
          <div>
            <CardTitle>Measured outcomes</CardTitle>
            <CardDescription>Counted from recorded events only. “Matched” means a procedure was found, not that the problem was solved.</CardDescription>
          </div>
          <label className="text-xs text-muted-foreground">
            Period
            <select className="mt-1 block h-9 rounded-lg border bg-background px-2 text-sm text-foreground" value={days} onChange={(e) => setDays(Number(e.target.value))}>
              <option value={7}>Last 7 days</option><option value={30}>Last 30 days</option><option value={90}>Last 90 days</option>
            </select>
          </label>
        </CardHeader>
        <CardContent>
          {error ? <p role="alert" className="text-sm text-red-700">{error}</p> : !data ? <p className="text-sm text-muted-foreground">Loading…</p> : (
            <>
              <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {Object.entries(data.metrics).map(([key, value]) => (
                  <div key={key} className="rounded-xl border p-3" title={data.definitions[key]}>
                    <dt className="text-xs text-muted-foreground">{LABELS[key] ?? key}</dt>
                    <dd className="mt-1 text-xl font-semibold tabular-nums">{value === null ? 'No data' : value}</dd>
                  </div>
                ))}
              </dl>
              <details className="mt-4 text-xs text-muted-foreground">
                <summary className="cursor-pointer font-medium">How each number is defined, and what is not measured</summary>
                <ul className="mt-2 space-y-1">
                  {Object.entries(data.definitions).map(([k, d]) => <li key={k}><span className="font-medium text-foreground">{LABELS[k] ?? k}:</span> {d}</li>)}
                  {Object.entries(data.unavailable).map(([k, d]) => <li key={k}><span className="font-medium text-foreground">Not available — {k.replace(/_/g, ' ')}:</span> {d}</li>)}
                </ul>
              </details>
            </>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Savings estimator</CardTitle>
          <CardDescription>An estimate from your own assumptions — not measured results.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <label className="text-xs">Employees<input className={field} type="number" min={1} value={inputs.employees} onChange={set('employees')} /></label>
            <label className="text-xs">Questions / person / week<input className={field} type="number" min={0} value={inputs.perWeek} onChange={set('perWeek')} /></label>
            <label className="text-xs">Minutes per supervisor interruption<input className={field} type="number" min={0} value={inputs.minutes} onChange={set('minutes')} /></label>
            <label className="text-xs">% answered without a supervisor<input className={field} type="number" min={0} max={100} value={inputs.share} onChange={set('share')} /></label>
            <label className="col-span-2 text-xs">Loaded cost per hour<input className={field} type="number" min={0} value={inputs.cost} onChange={set('cost')} /></label>
          </div>
          <Button type="button" onClick={estimate}>Calculate estimate</Button>
          {roiError ? <p role="alert" className="text-sm text-red-700">{roiError}</p> : null}
          {roi ? (
            <div className="rounded-xl border bg-muted/30 p-3 text-sm" aria-live="polite">
              <p className="font-semibold">Estimate: ~{roi.estimated_supervisor_hours_saved.toLocaleString()} supervisor hours / year · ~{roi.estimated_cost_saved.toLocaleString()} cost</p>
              <p className="mt-1 text-xs text-muted-foreground">{roi.estimated_supervisor_interruptions_avoided.toLocaleString()} interruptions avoided out of {roi.estimated_questions_per_year.toLocaleString()} questions. {roi.caveat}</p>
            </div>
          ) : null}
        </CardContent>
      </Card>
    </section>
  );
}
