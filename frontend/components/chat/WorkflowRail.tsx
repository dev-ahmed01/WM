import React from 'react';
import { Check, CirclePause, CirclePlay, ClipboardCheck, ShieldCheck, StopCircle } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import type { CopilotResponse, WorkflowDecisionOption } from '@/lib/api-client';

interface WorkflowRailProps {
  sessionId?: string;
  status?: CopilotResponse['active_session_status'];
  stepNumber?: number;
  stepTitle?: string;
  decisionOptions: WorkflowDecisionOption[];
  busy: boolean;
  onAdvance: (decisionOption?: string) => void;
  onPause: () => void;
  onResume: () => void;
  onAbandon: () => void;
}

export function WorkflowRail({
  sessionId,
  status,
  stepNumber,
  stepTitle,
  decisionOptions,
  busy,
  onAdvance,
  onPause,
  onResume,
  onAbandon,
}: WorkflowRailProps) {
  const active = status === 'active';
  const paused = status === 'paused';
  const hasWorkflow = Boolean(sessionId && status);

  return (
    <aside className="h-full min-h-0 overflow-y-auto border-b border-border/80 bg-[#f6f9f7] p-4 lg:border-b-0 lg:border-l lg:p-5" aria-label="Active workflow">
      <div className="mx-auto max-w-xl space-y-4 lg:max-w-none">
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="wm-eyebrow">Workflow</p>
            <h2 className="mt-1 text-sm font-semibold text-foreground">Shift guidance</h2>
          </div>
          {status ? (
            <Badge variant={active ? 'default' : paused ? 'warning' : 'neutral'}>
              <span className="h-1.5 w-1.5 rounded-full bg-current opacity-70" />
              {status}
            </Badge>
          ) : null}
        </div>

        {!hasWorkflow ? (
          <div className="rounded-2xl border border-dashed border-emerald-200 bg-white/70 p-5">
            <div className="grid h-9 w-9 place-items-center rounded-xl bg-emerald-50 text-emerald-700"><ClipboardCheck className="h-4 w-4" /></div>
            <p className="mt-3 text-sm font-semibold text-foreground">No workflow active</p>
            <p className="mt-1 text-xs leading-5 text-muted-foreground">Ask for an SOP by name or describe the operational situation you are handling.</p>
          </div>
        ) : stepTitle && (stepNumber != null || decisionOptions.length > 0) ? (
          <div className="overflow-hidden rounded-2xl border border-emerald-200 bg-white shadow-panel">
            <div className="border-b border-emerald-100 bg-emerald-50/80 px-4 py-3">
              <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-emerald-800">
                <span className="grid h-5 w-5 place-items-center rounded-full bg-emerald-700 text-[10px] text-white">{stepNumber ?? '!'}</span>
                {stepNumber != null ? `Current step ${stepNumber}` : 'Decision required'}
              </div>
            </div>
            <div className="p-4">
              <p className="text-[15px] font-semibold leading-6 text-foreground">{stepTitle}</p>
              {decisionOptions.length === 0 ? (
                <>
                  <p className="mt-2 text-xs leading-5 text-muted-foreground">Complete only this instruction before moving forward.</p>
                  <Button className="mt-4 w-full" disabled={busy || !active} onClick={() => onAdvance()}>
                    <Check className="h-4 w-4" /> Complete step
                  </Button>
                </>
              ) : (
                <div className="mt-4 space-y-2" aria-label="Verified SOP outcomes">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.1em] text-muted-foreground">Select what you observed</p>
                  {decisionOptions.map((option) => (
                    <button
                      key={option.option_code}
                      type="button"
                      disabled={busy || !active}
                      onClick={() => onAdvance(option.option_code)}
                      className="group flex w-full items-start gap-3 rounded-xl border border-border bg-white p-3 text-left text-xs font-semibold leading-5 text-foreground transition hover:border-emerald-300 hover:bg-emerald-50 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      <span className="mt-0.5 h-3.5 w-3.5 flex-none rounded-full border-2 border-slate-300 transition group-hover:border-emerald-600" />
                      {option.option_label}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        ) : (
          <div className="rounded-2xl border bg-white p-4 text-sm text-muted-foreground">Workflow status: <span className="font-semibold capitalize text-foreground">{status}</span></div>
        )}

        {hasWorkflow && ['active', 'paused'].includes(status || '') ? (
          <div className="rounded-2xl border bg-white p-3">
            <p className="px-1 pb-2 text-[10px] font-semibold uppercase tracking-[0.13em] text-muted-foreground">Session controls</p>
            <div className="grid grid-cols-2 gap-2">
              {active ? (
                <Button variant="outline" size="sm" disabled={busy} onClick={onPause}><CirclePause className="h-3.5 w-3.5" />Pause</Button>
              ) : (
                <Button variant="outline" size="sm" disabled={busy} onClick={onResume}><CirclePlay className="h-3.5 w-3.5" />Resume</Button>
              )}
              <Button variant="ghost" size="sm" disabled={busy} onClick={onAbandon} className="text-red-600 hover:bg-red-50 hover:text-red-700"><StopCircle className="h-3.5 w-3.5" />Abandon</Button>
            </div>
          </div>
        ) : null}

        <div className="flex items-start gap-3 rounded-xl border border-emerald-100 bg-emerald-50/60 p-3 text-[11px] leading-4 text-emerald-900">
          <ShieldCheck className="mt-0.5 h-4 w-4 flex-none text-emerald-700" />
          <span><strong className="font-semibold">Verified mode.</strong> WorkMate will not skip steps or invent organizational guidance.</span>
        </div>
      </div>
    </aside>
  );
}
