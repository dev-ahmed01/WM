'use client';

import { useEffect, useMemo, useState, type FormEvent } from 'react';
import Link from 'next/link';
import { AlertCircle, ArrowRight, Plus, RefreshCw, X } from 'lucide-react';
import { apiClient } from '@/lib/api-client';
import { useRequireRole } from '@/lib/auth';
import { LoadingState } from '@/components/shared/LoadingState';
import { WORK_TYPES, workTypeLabel, workStatusLabel, type WorkItem, type WorkQueueResponse, type WorkType, type WorkPriority } from '@/lib/work-items';

type Filter = 'all' | 'high' | 'receiving';
type Staff = { id: string; label: string };

export default function WorkDesk() {
  const { user, loading } = useRequireRole(['employee', 'manager', 'admin']);
  const manager = user?.role === 'admin' || user?.role === 'manager';
  const [queue, setQueue] = useState<WorkItem[]>([]);
  const [staff, setStaff] = useState<Staff[]>([]);
  const [dataLoading, setDataLoading] = useState(true);
  const [error, setError] = useState('');
  const [filter, setFilter] = useState<Filter>('all');
  const [formOpen, setFormOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [title, setTitle] = useState('');
  const [type, setType] = useState<WorkType>('receiving');
  const [priority, setPriority] = useState<WorkPriority>('standard');
  const [assignee, setAssignee] = useState('');

  async function reload() {
    setDataLoading(true);
    setError('');
    try {
      const work = await apiClient<WorkQueueResponse>('/work/items');
      setQueue(work.items ?? []);
      if (manager) {
        const people = await apiClient<{ items: Staff[] }>('/work/items/assignees');
        setStaff(people.items ?? []);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load work.');
    } finally {
      setDataLoading(false);
    }
  }

  useEffect(() => {
    if (loading || !user) return;
    void reload();
  // Reload when identity or scope changes.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading, user?.sub, user?.department_id, user?.role]);

  const open = queue.filter(item => item.status !== 'completed');
  const high = open.filter(item => item.priority === 'high').length;
  const visible = useMemo(() => open.filter(item =>
    filter === 'all' || (filter === 'high' && item.priority === 'high') ||
    (filter === 'receiving' && item.work_type === 'receiving')
  ).sort((a,b) => Number(b.priority === 'high') - Number(a.priority === 'high')), [queue,filter]);
  const assigned = open.filter(item => Boolean(item.assigned_to)).length;

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!manager || saving) return;
    setSaving(true);
    setError('');
    try {
      await apiClient('/work/items', { method: 'POST', body: JSON.stringify({
        title: title.trim(), work_type: type, priority,
        assigned_to: assignee || null, instructions: '', external_reference: '',
      }) });
      setTitle('');
      setAssignee('');
      setPriority('standard');
      setFormOpen(false);
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to create assignment.');
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <LoadingState label="Opening work" />;
  return (
    <div className="wm-page max-w-[1400px] space-y-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div><h1 className="text-3xl font-semibold">Today's work</h1>
          <p className="mt-1 text-sm text-muted-foreground">{manager ? 'Department queue' : 'Assigned to you'}</p></div>
        <div className="flex items-center gap-2">
          <button type="button" onClick={() => void reload()} disabled={dataLoading} aria-label="Refresh queue" className="rounded-xl border bg-white p-3 disabled:opacity-50"><RefreshCw className="h-4 w-4" /></button>
          {manager ? <button type="button" onClick={() => setFormOpen(v=>!v)} className="inline-flex items-center gap-2 rounded-xl bg-[#17583d] px-4 py-3 text-sm font-semibold text-white"><Plus className="h-4 w-4" /> New assignment</button> : null}
        </div>
      </header>
      {error ? <div role="alert" className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{error}</div> : null}
      {manager && formOpen ? (
        <form onSubmit={event => void create(event)} className="rounded-2xl border bg-white p-5">
          <div className="mb-4 flex items-center justify-between"><h2 className="text-lg font-semibold">New assignment</h2><button type="button" onClick={() => setFormOpen(false)} aria-label="Close"><X className="h-4 w-4" /></button></div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="sm:col-span-2"><label className="wm-label" htmlFor="new-title">Task</label><input className="wm-input" id="new-title" required minLength={5} maxLength={180} placeholder="Inspect incoming pallets" value={title} onChange={e=>setTitle(e.target.value)} /></div>
            <div><label className="wm-label" htmlFor="new-type">Work type</label><select id="new-type" className="wm-input" value={type} onChange={e=>setType(e.target.value as WorkType)}>{WORK_TYPES.map(t=><option key={t.value} value={t.value}>{t.label}</option>)}</select></div>
            <div><label className="wm-label" htmlFor="new-priority">Priority</label><select id="new-priority" className="wm-input" value={priority} onChange={e=>setPriority(e.target.value as WorkPriority)}><option value="standard">Standard</option><option value="high">High</option></select></div>
            <div className="sm:col-span-2"><label className="wm-label" htmlFor="new-assignee">Employee</label><select id="new-assignee" className="wm-input" value={assignee} onChange={e=>setAssignee(e.target.value)}><option value="">Unassigned</option>{staff.map(person=><option key={person.id} value={person.id}>{person.label}</option>)}</select></div>
          </div>
          <div className="mt-4 flex justify-end"><button type="submit" disabled={saving || title.trim().length < 5} className="rounded-xl bg-emerald-800 px-5 py-2.5 text-sm font-semibold text-white disabled:opacity-50">{saving ? 'Creating…' : 'Create task'}</button></div>
        </form>
      ) : null}
      <section className="grid grid-cols-3 gap-3" aria-label="Queue overview">
        {[{label:'Open',value:open.length},{label:'Assigned',value:assigned},{label:'High priority',value:high}].map(x=>(
          <div key={x.label} className="rounded-2xl border bg-white p-5"><p className="text-xs text-muted-foreground">{x.label}</p><p className="mt-2 text-3xl font-semibold tabular-nums">{dataLoading ? '—' : x.value}</p></div>
        ))}
      </section>
      <section>
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-xl font-semibold">Queue</h2>
          <div className="flex rounded-xl bg-emerald-50 p-1" aria-label="Filter work">
            {([['all','All'],['high','High priority'],['receiving','Receiving']] as const).map(([value,label])=>(
              <button key={value} type="button" aria-pressed={filter===value} onClick={()=>setFilter(value)} className={`rounded-lg px-3 py-2 text-xs font-semibold ${filter===value ? 'bg-white text-emerald-900 shadow-sm' : 'text-muted-foreground'}`}>{label}</button>
            ))}
          </div>
        </div>
        {dataLoading ? <LoadingState label="Loading queue" /> : visible.length ? (
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {visible.map(item=>(
              <Link key={item.id} href={'/work/'+encodeURIComponent(item.id)} className="group flex min-h-40 flex-col rounded-2xl border bg-white p-5 transition hover:border-emerald-400 hover:shadow-panel">
                <div className="flex items-center justify-between gap-2"><span className="text-xs font-semibold text-emerald-800">{workTypeLabel(item.work_type)}</span>{item.priority==='high' ? <AlertCircle className="h-4 w-4 text-amber-700" />:null}</div>
                <h3 className="mt-3 line-clamp-2 text-lg font-semibold">{item.title}</h3>
                <div className="mt-auto flex items-center justify-between pt-4 text-xs text-muted-foreground"><span>{workStatusLabel(item.status)}</span><ArrowRight className="h-4 w-4 text-emerald-700" /></div>
              </Link>
            ))}
          </div>
        ) : <div className="rounded-2xl border border-dashed bg-white px-5 py-12 text-center text-sm text-muted-foreground">{filter === 'all' ? 'No assignments yet.' : 'No matching tasks.'}</div>}
      </section>
    </div>
  );
}
