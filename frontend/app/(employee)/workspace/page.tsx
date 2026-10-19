'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import {
  AlertCircle, ArrowRight, ArrowUpRight, Boxes, CheckCircle2, Clock3,
  ClipboardList, FileSearch2, Headphones, Layers3, PackageCheck, RefreshCw,
  SearchCheck, ShieldCheck, Sparkles,
} from 'lucide-react';
import { apiClient } from '@/lib/api-client';
import { useRequireRole } from '@/lib/auth';
import { LoadingState } from '@/components/shared/LoadingState';
import { guidanceUrl, workTypeLabel, type WorkItem, type WorkQueueResponse } from '@/lib/work-items';

type Filter = 'all' | 'high' | 'receiving';

function WorkTile({ item }: { item: WorkItem }) {
  return (
    <Link href={'/work/' + encodeURIComponent(item.id)}
      className="group flex min-w-0 flex-col gap-5 rounded-[1.35rem] border border-[#dce4df] bg-white p-5 transition hover:-translate-y-0.5 hover:border-[#8ac7ae] hover:shadow-[0_18px_42px_-25px_rgba(13,51,38,.25)] focus-visible:ring-2 focus-visible:ring-emerald-600">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="rounded-lg bg-[#f1f6f2] px-2.5 py-1.5 text-[10px] font-bold uppercase tracking-[0.1em] text-[#366453]">{workTypeLabel(item.work_type)}</span>
        {item.priority === 'high'
          ? <span className="inline-flex items-center gap-1 rounded-lg bg-amber-50 px-2.5 py-1.5 text-[11px] font-semibold text-amber-800"><AlertCircle className="h-3.5 w-3.5" />High priority</span>
          : <span className="text-[11px] font-medium text-[#6c7771]">Standard</span>}
      </div>
      <div className="min-w-0">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-[#849087]">{item.external_reference || item.id.slice(0, 16)}</p>
        <h3 className="mt-2 break-words text-xl font-semibold leading-snug tracking-tight text-[#172a23]">{item.title}</h3>
        {item.instructions ? <p className="mt-2 line-clamp-2 text-sm leading-6 text-[#65726b]">{item.instructions}</p> : null}
      </div>
      <div className="mt-auto flex items-center justify-between border-t border-[#edf1ed] pt-4">
        <span className="inline-flex items-center gap-2 text-xs font-semibold text-[#5b6961]"><Clock3 className="h-4 w-4" />Queued</span>
        <span className="inline-flex items-center gap-1.5 text-xs font-bold text-[#15563e]">Open work <ArrowUpRight className="h-4 w-4 transition group-hover:translate-x-0.5" /></span>
      </div>
    </Link>
  );
}

export default function WorkDesk() {
  const { user, loading } = useRequireRole(['employee', 'manager', 'admin']);
  const [queue, setQueue] = useState<WorkItem[]>([]);
  const [dataLoading, setDataLoading] = useState(true);
  const [error, setError] = useState('');
  const [filter, setFilter] = useState<Filter>('all');

  const reload = async () => {
    setDataLoading(true);
    setError('');
    try {
      const result = await apiClient<WorkQueueResponse>('/work/items');
      setQueue(result.items || []);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Work queue is unavailable.');
    } finally {
      setDataLoading(false);
    }
  };

  useEffect(() => {
    if (loading || !user) return;
    let active = true;
    setDataLoading(true);
    void apiClient<WorkQueueResponse>('/work/items')
      .then(result => { if (active) setQueue(result.items || []); })
      .catch(caught => { if (active) setError(caught instanceof Error ? caught.message : 'Work queue is unavailable.'); })
      .finally(() => { if (active) setDataLoading(false); });
    return () => { active = false; };
  }, [loading, user?.sub, user?.department_id]);

  const visible = useMemo(() => queue.filter(item =>
    filter === 'all' || (filter === 'high' ? item.priority === 'high' : item.work_type === 'receiving')
  ), [filter, queue]);
  if (loading) return <LoadingState label="Opening your work" />;

  const highCount = queue.filter(item => item.priority === 'high').length;
  const manager = user?.role === 'manager' || user?.role === 'admin';

  return (
    <div className="wm-page max-w-[1480px] space-y-7 pb-12">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          <p className="text-[11px] font-bold uppercase tracking-[0.19em] text-emerald-800">WORKMATE / {user?.department_id || 'WORKSPACE'}</p>
          <h1 className="mt-2 text-3xl font-semibold tracking-[-0.045em] text-[#152c22] sm:text-[2.6rem]">Today's work</h1>
          <p className="mt-2 text-sm text-[#718078]">{manager ? 'Department queue' : 'Assigned to you'} · Current work only</p>
        </div>
        <div className="flex gap-2">
          {manager ? <Link href="/control-room" className="inline-flex min-h-11 items-center gap-2 rounded-xl border border-[#dbe4dd] bg-white px-4 text-xs font-semibold text-[#233b30] hover:bg-[#f1f6f3]"><Layers3 className="h-4 w-4" />Control room</Link> : null}
          <button type="button" onClick={() => void reload()} disabled={dataLoading} className="inline-flex min-h-11 items-center gap-2 rounded-xl border border-[#dbe4dd] bg-white px-4 text-xs font-semibold text-[#233b30] hover:bg-[#f1f6f3] disabled:opacity-50"><RefreshCw className="h-4 w-4" />Refresh</button>
        </div>
      </div>

      <section className="grid gap-3 sm:grid-cols-3" aria-label="Queue overview">
        <div className="rounded-2xl border border-[#dce4df] bg-white p-5">
          <div className="flex items-center justify-between"><span className="text-xs font-medium text-[#738177]">Queued work</span><ClipboardList className="h-4 w-4 text-emerald-700" /></div>
          <div className="mt-4 text-4xl font-semibold tabular-nums tracking-tight text-[#1b3328]">{dataLoading || error ? '—' : queue.length}</div>
        </div>
        <div className="rounded-2xl border border-[#e9dfd0] bg-[#fdfaf4] p-5">
          <div className="flex items-center justify-between"><span className="text-xs font-medium text-[#877258]">High priority</span><AlertCircle className="h-4 w-4 text-amber-700" /></div>
          <div className="mt-4 text-4xl font-semibold tabular-nums tracking-tight text-[#553e21]">{dataLoading || error ? '—' : highCount}</div>
        </div>
        <Link href="/copilot/handover" className="group flex flex-col justify-between rounded-2xl border border-[#c7dcd0] bg-[#e9f3ed] p-5 transition hover:bg-[#ddecdf]">
          <div className="flex items-center justify-between"><span className="text-xs font-semibold text-[#38634d]">Shift continuity</span><PackageCheck className="h-4 w-4 text-[#216449]" /></div>
          <div className="mt-6 flex items-end justify-between gap-3"><span className="text-xl font-semibold tracking-tight text-[#183c2b]">Prepare handover</span><ArrowUpRight className="h-5 w-5 text-[#176146] transition group-hover:translate-x-1" /></div>
        </Link>
      </section>

      <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1.75fr)_minmax(18rem,.8fr)]">
        <section className="min-w-0" aria-label="Your task queue">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div><h2 className="text-xl font-semibold tracking-tight text-[#172d23]">Work queue</h2><p className="mt-1 text-xs text-[#718078]">Open a task to see the assigned context and approved guidance.</p></div>
            <div className="flex rounded-xl bg-[#e9efeb] p-1" role="group" aria-label="Filter work items">
              {([['all','All'],['high','High priority'],['receiving','Receiving']] as const).map(([key,label]) =>
                <button key={key} type="button" aria-pressed={filter === key} onClick={() => setFilter(key)}
                  className={filter === key ? 'rounded-lg bg-white px-3 py-2 text-[11px] font-semibold text-[#123e2b] shadow-sm' : 'rounded-lg px-3 py-2 text-[11px] font-medium text-[#66776c] hover:text-[#123e2b]'}>{label}</button>)}
            </div>
          </div>
          {error ? <div role="alert" className="mt-5 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">{error}</div> : null}
          {dataLoading ? <div className="mt-5 rounded-2xl border border-[#dce4df] bg-white p-12"><LoadingState label="Loading assigned work" /></div> : !error && visible.length ? (
            <div className="mt-5 grid gap-3 sm:grid-cols-2">{visible.map(item => <WorkTile key={item.id} item={item} />)}</div>
          ) : !error ? (
            <div className="mt-5 rounded-[1.4rem] border border-dashed border-[#cddacf] bg-white px-6 py-12 text-center">
              <span className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-[#edf5ef]"><Boxes className="h-7 w-7 text-emerald-700" /></span>
              <h3 className="mt-4 text-lg font-semibold">{filter === 'all' ? 'No work assigned yet' : 'No matching work'}</h3>
              <p className="mx-auto mt-2 max-w-sm text-sm leading-6 text-[#718078]">{filter === 'all' ? (manager ? 'Create your first assignment in Control room.' : 'New assignments will appear here when your supervisor queues them.') : 'Change the filter to see the full queue.'}</p>
              {manager && filter === 'all' ? <Link href="/control-room" className="mt-5 inline-flex items-center gap-2 rounded-xl bg-[#15583f] px-5 py-3 text-xs font-semibold text-white">Create assignment <ArrowRight className="h-4 w-4" /></Link> : null}
            </div>
          ) : null}
        </section>

        <aside className="space-y-4">
          <section className="overflow-hidden rounded-[1.4rem] border border-[#1b4334] bg-[#14382b] p-6 text-white">
            <span className="inline-flex items-center gap-2 text-[10px] font-bold uppercase tracking-[0.17em] text-[#a5dfc0]"><Sparkles className="h-4 w-4" />WORKMATE ASSIST</span>
            <h2 className="mt-4 text-2xl font-semibold leading-tight tracking-tight">Guidance at the point of work.</h2>
            <p className="mt-3 text-xs leading-6 text-[#c1d9ca]">Find published procedures and review cited evidence before taking action.</p>
            <Link href="/copilot" className="mt-6 inline-flex min-h-11 w-full items-center justify-center gap-2 rounded-xl bg-[#c1efd3] px-4 text-sm font-semibold text-[#123728] transition hover:bg-white">Ask about your work <ArrowRight className="h-4 w-4" /></Link>
          </section>
          <div className="rounded-[1.35rem] border border-[#dae4dc] bg-white p-5">
            <h3 className="text-xs font-bold uppercase tracking-wide text-[#597765]">Quick access</h3>
            <div className="mt-3 divide-y divide-[#edf1ed]">
              {[
                { icon: SearchCheck, title: 'Approved sources', href: '/copilot/sources' },
                { icon: FileSearch2, title: 'Previous sessions', href: '/copilot/history' },
                { icon: Headphones, title: 'SOP guidance', href: '/copilot' },
              ].map(link => <Link key={link.href} href={link.href} className="flex min-h-12 items-center justify-between gap-3 text-sm font-semibold text-[#304739] hover:text-emerald-700"><span className="flex items-center gap-3"><link.icon className="h-4 w-4 text-[#729281]" />{link.title}</span><ArrowRight className="h-4 w-4" /></Link>)}
            </div>
          </div>
          <div className="flex items-start gap-3 rounded-2xl border border-[#dce6de] bg-[#f5f8f5] p-4"><ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-emerald-700" /><p className="text-xs leading-5 text-[#62756b]">Queued assignments are not completed workflows. Step execution and evidence capture are added in Phase 2.</p></div>
        </aside>
      </div>
    </div>
  );
}
