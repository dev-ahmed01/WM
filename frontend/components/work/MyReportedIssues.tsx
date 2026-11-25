'use client';

import React, { useEffect, useState } from 'react';
import { ClipboardList } from 'lucide-react';
import { apiClient } from '@/lib/api-client';

interface ReportedCase {
  id: string; status: string; severity: string; reason: string; work_title: string; progress: string;
  created_at: string; updated_at: string;
}

/** Issues the employee reported by blocking work. Shows plain progress only, never internal supervisor notes. */
export function MyReportedIssues() {
  const [items, setItems] = useState<ReportedCase[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    apiClient<{ items: ReportedCase[] }>('/work/exceptions/mine')
      .then((r) => { if (!cancelled) setItems(r.items.slice(0, 5)); })
      .catch(() => { if (!cancelled) setItems([]); }); // optional card: never block the queue
    return () => { cancelled = true; };
  }, []);

  if (!items || items.length === 0) return null;

  return (
    <div className="rounded-[1.35rem] border border-[#dae4dc] bg-white p-5" aria-label="Issues you reported">
      <h3 className="flex items-center gap-2 text-xs font-bold uppercase tracking-wide text-[#597765]"><ClipboardList className="h-4 w-4" />Issues you reported</h3>
      <ul className="mt-3 space-y-3">
        {items.map((c) => (
          <li key={c.id} className="text-sm">
            <p className="font-medium leading-5">{c.work_title}</p>
            <p className="mt-0.5 text-xs text-muted-foreground">“{c.reason}”</p>
            <p className={`mt-1 text-xs font-semibold ${c.status === 'closed' ? 'text-emerald-800' : 'text-amber-800'}`}>{c.progress}</p>
            <p className="mt-0.5 text-[10px] text-muted-foreground">Updated {new Date(c.updated_at).toLocaleString()}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}
