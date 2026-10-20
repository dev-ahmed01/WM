'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { AlertCircle, ArrowLeft, ArrowRight, ClipboardList, ShieldCheck, UserRound } from 'lucide-react';
import { useRequireRole } from '@/lib/auth';
import { apiClient } from '@/lib/api-client';
import { guidanceUrl, workTypeLabel, type WorkItem } from '@/lib/work-items';
import { LoadingState } from '@/components/shared/LoadingState';
import { WorkExecutionPanel } from '@/components/work/WorkExecutionPanel';
import { workStatusLabel } from '@/lib/work-items';

export default function WorkItemDetail() {
  const { user, loading } = useRequireRole(['employee', 'manager', 'admin']);
  const params = useParams<{ id: string }>();
  const [item, setItem] = useState<WorkItem | null>(null);
  const [fetching, setFetching] = useState(true);
  const [error, setError] = useState('');
  useEffect(() => {
    if (loading || !user || !params.id) return;
    let active = true;
    void apiClient<WorkItem>('/work/items/' + encodeURIComponent(params.id))
      .then(result => { if (active) setItem(result); })
      .catch(caught => { if (active) setError(caught instanceof Error ? caught.message : 'This work item is unavailable.'); })
      .finally(() => { if (active) setFetching(false); });
    return () => { active = false; };
  }, [loading,user?.sub,user?.department_id,params.id]);

  if (loading || fetching) return <LoadingState label="Opening assigned work" />;
  if (error || !item) return (
    <div className="wm-page max-w-4xl">
      <Link href="/workspace" className="inline-flex items-center gap-2 text-sm font-semibold text-emerald-700"><ArrowLeft className="h-4 w-4" />Work queue</Link>
      <div role="alert" className="mt-6 rounded-2xl border border-red-200 bg-red-50 p-6 text-sm text-red-800">{error || 'Work item unavailable.'}</div>
    </div>
  );

  return (
    <div className="wm-page max-w-[1250px] space-y-7 pb-12">
      <Link href="/workspace" className="inline-flex items-center gap-2 text-xs font-semibold text-[#577262] hover:text-emerald-700"><ArrowLeft className="h-4 w-4" />All work</Link>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-lg bg-emerald-50 px-3 py-1.5 text-[10px] font-bold uppercase tracking-widest text-emerald-800">{workTypeLabel(item.work_type)}</span>
            {item.priority === 'high' ? <span className="rounded-lg bg-amber-50 px-3 py-1.5 text-[10px] font-bold uppercase tracking-wider text-amber-800">High priority</span> : null}
            <span className="rounded-lg bg-slate-100 px-3 py-1.5 text-[10px] font-bold uppercase tracking-wider text-slate-600">{workStatusLabel(item.status)}</span>
          </div>
          <h1 className="mt-4 max-w-3xl text-3xl font-semibold tracking-[-.04em] text-[#142b20] sm:text-[2.6rem]">{item.title}</h1>
          <p className="mt-2 text-xs text-[#6a776f]">{item.external_reference || item.id} · {item.department_id}</p>
        </div>
        <Link href={guidanceUrl(item)} className="inline-flex min-h-12 items-center gap-2 rounded-xl bg-[#15583e] px-5 text-sm font-semibold text-white hover:bg-[#0d3828]">Check published SOP <ArrowRight className="h-4 w-4" /></Link>
      </div>
      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1.4fr)_minmax(16rem,.7fr)]">
        <div className="min-w-0 space-y-5">
          <WorkExecutionPanel
            item={item}
            isAssignee={Boolean(user && item.assigned_to === user.sub)}
            canManage={user?.role === 'manager' || user?.role === 'admin'}
            onTaskChanged={() => {
              void apiClient<WorkItem>('/work/items/' + encodeURIComponent(item.id))
                .then(updated => setItem(updated))
                .catch(() => undefined);
            }}
          />
        <section className="overflow-hidden rounded-[1.6rem] border border-[#d8e2da] bg-white">
          <div className="flex items-center gap-3 border-b border-[#e9efe9] px-6 py-5">
            <ClipboardList className="h-5 w-5 text-emerald-700" />
            <div><h2 className="text-lg font-semibold">Work brief</h2><p className="text-xs text-[#748077]">Recorded by the supervisor</p></div>
          </div>
          <div className="space-y-6 p-6">
            <div><p className="text-[10px] font-bold uppercase tracking-[.12em] text-[#7d887f]">Instructions</p><p className="mt-2 whitespace-pre-wrap break-words text-sm leading-7 text-[#243a2c]">{item.instructions || 'No additional instructions supplied. Check the applicable published procedure before acting.'}</p></div>
            <div className="rounded-xl border border-[#d7e9db] bg-[#f1f8f2] p-4">
              <div className="flex items-center gap-2"><ShieldCheck className="h-4 w-4 text-emerald-700" /><p className="text-sm font-semibold text-[#234735]">Procedure-first execution</p></div>
              <p className="mt-2 text-xs leading-6 text-[#5d7564]">This assignment is executed against the linked, published SOP. WorkMate records worker attestations and received evidence, but does not independently verify physical conditions.</p>
              <Link href={guidanceUrl(item)} className="mt-3 inline-flex items-center gap-2 text-xs font-bold text-emerald-800 hover:underline">Open task-aware guidance <ArrowRight className="h-4 w-4" /></Link>
            </div>
          </div>
        </section>
        </div>
        <aside className="space-y-4">
          <div className="rounded-[1.4rem] border border-[#d8e2da] bg-white p-5">
            <h2 className="text-sm font-semibold">Assignment details</h2>
            <div className="mt-4 space-y-4">
              <div className="flex items-start gap-3"><UserRound className="mt-0.5 h-4 w-4 text-[#69907a]" /><div className="min-w-0"><p className="text-[10px] uppercase tracking-wide text-[#87958a]">Assigned to</p><p className="mt-1 break-words text-sm font-semibold">{item.assigned_to || 'Unassigned'}</p></div></div>
              <div className="flex items-start gap-3"><ClipboardList className="mt-0.5 h-4 w-4 text-[#69907a]" /><div><p className="text-[10px] uppercase tracking-wide text-[#87958a]">Created by</p><p className="mt-1 break-words text-sm font-semibold">{item.created_by}</p></div></div>
            </div>
          </div>
          <div className="rounded-[1.4rem] border border-[#efe2cc] bg-[#fffbf4] p-5">
            <div className="flex items-center gap-2 text-amber-900"><AlertCircle className="h-4 w-4" /><p className="text-sm font-semibold">Unexpected condition?</p></div>
            <p className="mt-2 text-xs leading-6 text-[#8d7652]">Block the task in the execution panel when a physical safety condition is uncertain. Contact the responsible supervisor before continuing.</p>
            <Link href={guidanceUrl(item)} className="mt-4 inline-flex items-center gap-2 text-xs font-bold text-amber-900 hover:underline">Get guidance <ArrowRight className="h-4 w-4" /></Link>
          </div>
        </aside>
      </div>
    </div>
  );
}
