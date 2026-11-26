'use client';

import React, { useEffect, useState } from 'react';
import { MessageCircleQuestion } from 'lucide-react';
import { apiClient } from '@/lib/api-client';

interface MyQuestion {
  id: string; question: string; status: 'open' | 'answered' | 'drafting' | 'resolved' | 'dismissed';
  employee_reply: string | null; updated_at: string;
}

const LABEL: Record<MyQuestion['status'], string> = {
  open: 'Sent to your supervisor',
  answered: 'Your supervisor replied',
  drafting: 'Being written up as an SOP',
  resolved: 'Now covered by an SOP — ask again',
  dismissed: 'Closed',
};

/** Questions WorkMate could not answer, with any human reply. Replies are not approved procedures. */
export function MyQuestions() {
  const [items, setItems] = useState<MyQuestion[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    apiClient<{ items: MyQuestion[] }>('/knowledge-gaps/mine')
      .then((r) => { if (!cancelled) setItems(r.items.slice(0, 5)); })
      .catch(() => { if (!cancelled) setFailed(true); });
    return () => { cancelled = true; };
  }, []);

  if (failed) return null; // optional card: never block the work queue
  if (!items || items.length === 0) return null;

  return (
    <div className="rounded-[1.35rem] border border-[#dae4dc] bg-white p-5" aria-label="Your questions to supervisors">
      <h3 className="flex items-center gap-2 text-xs font-bold uppercase tracking-wide text-[#506b5b]"><MessageCircleQuestion className="h-4 w-4" />Your questions</h3>
      <ul className="mt-3 space-y-3">
        {items.map((q) => (
          <li key={q.id} className="text-sm">
            <p className="font-medium leading-5">“{q.question}”</p>
            <p className="mt-1 text-xs font-semibold text-emerald-800">{LABEL[q.status]}</p>
            {q.employee_reply ? <p className="mt-1 rounded-lg bg-[#f2f8f3] p-2.5 text-xs leading-5"><span className="font-semibold">Supervisor reply (not an approved procedure):</span> {q.employee_reply}</p> : null}
          </li>
        ))}
      </ul>
    </div>
  );
}
