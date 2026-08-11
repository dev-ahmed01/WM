import React from 'react';

export function LoadingState({ label = 'Loading workspace' }: { label?: string }) {
  return (
    <div className="wm-page" aria-live="polite" aria-busy="true">
      <span className="sr-only">{label}</span>
      <div className="space-y-5 animate-pulse">
        <div className="h-3 w-28 rounded-full bg-emerald-100" />
        <div className="h-8 w-72 max-w-full rounded-lg bg-slate-200" />
        <div className="h-4 w-[32rem] max-w-full rounded bg-slate-100" />
        <div className="grid gap-4 pt-4 md:grid-cols-3">
          {[0, 1, 2].map((item) => <div key={item} className="h-32 rounded-2xl border bg-white" />)}
        </div>
      </div>
    </div>
  );
}
