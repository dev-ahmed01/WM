'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import {
  AlertTriangle, ArrowRight, ArrowUpRight, ClipboardList, Clock3, Inbox,
  Layers3, Plus, RefreshCw, ShieldCheck, UsersRound, X,
} from 'lucide-react';
import { useRequireRole } from '@/lib/auth';
import { apiClient } from '@/lib/api-client';
import { LoadingState } from '@/components/shared/LoadingState';
import { WORK_TYPES, workTypeLabel, type WorkItem, type WorkQueueResponse, type WorkType, type WorkPriority } from '@/lib/work-items';

type Handover = { id: string; status: string; severity: 'normal' | 'high' | 'critical'; next_action: string; created_at: string; recipient_label: string };
type Staff = { id: string; label: string };

export default function ControlRoom() {
  const { user, loading } = useRequireRole(['manager', 'admin']);
  const [items, setItems] = useState<WorkItem[]>([]);
  const [handovers, setHandovers] = useState<Handover[]>([]);
  const [staff, setStaff] = useState<Staff[]>([]);
  const [fetching, setFetching] = useState(true);
  const [error, setError] = useState('');
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState('');
  const [title, setTitle] = useState('');
  const [workType, setWorkType] = useState<WorkType>('receiving');
  const [priority, setPriority] = useState<WorkPriority>('standard');
  const [assignee, setAssignee] = useState('');
  const [reference, setReference] = useState('');
  const [instructions, setInstructions] = useState('');

  const load = async () => {
    setFetching(true);
    setError('');
    try {
      const [work, cases, people] = await Promise.all([
        apiClient<WorkQueueResponse>('/work/items'),
        apiClient<{items: Handover[]}>('/handover?limit=100'),
        apiClient<{items: Staff[]}>('/work/items/assignees'),
      ]);
      setItems(work.items || []);
      setHandovers(cases.items || []);
      setStaff(people.items || []);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Control room data is unavailable.');
    } finally {
      setFetching(false);
    }
  };

  useEffect(() => {
    if (loading || !user) return;
    let active = true;
    setFetching(true);
    void Promise.all([
      apiClient<WorkQueueResponse>('/work/items'),
      apiClient<{items: Handover[]}>('/handover?limit=100'),
      apiClient<{items: Staff[]}>('/work/items/assignees'),
    ]).then(([work,cases,people]) => {
      if (active) { setItems(work.items || []); setHandovers(cases.items || []); setStaff(people.items || []); }
    }).catch(caught => { if (active) setError(caught instanceof Error ? caught.message : 'Control room data is unavailable.'); })
      .finally(() => { if (active) setFetching(false); });
    return () => { active = false; };
  }, [loading,user?.sub,user?.department_id]);

  const pending = handovers.filter(item => item.status === 'submitted').length;
  const priorityCount = items.filter(item => item.priority === 'high').length;
  const urgent = handovers.filter(item => item.status === 'submitted' && item.severity !== 'normal').length;
  const assigned = items.filter(item => Boolean(item.assigned_to)).length;
  const ordered = useMemo(() => items.slice().sort((a,b) =>
    Number(b.priority === 'high') - Number(a.priority === 'high') ||
    Date.parse(b.created_at) - Date.parse(a.created_at)
  ).slice(0,12), [items]);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (title.trim().length < 5 || saving) return;
    setSaving(true);
    setFormError('');
    try {
      await apiClient('/work/items',{method:'POST',body:JSON.stringify({
        title: title.trim(),work_type:workType,priority,external_reference:reference.trim(),
        assigned_to:assignee || null,instructions:instructions.trim(),
      })});
      setOpen(false);
      setTitle('');setAssignee('');setReference('');setInstructions('');setPriority('standard');
      await load();
    } catch (caught) {
      setFormError(caught instanceof Error ? caught.message : 'Could not queue this assignment.');
    } finally {
      setSaving(false);
    }
  }
  if (loading) return <LoadingState label="Opening control room" />;

  return (
    <div className="wm-page max-w-[1500px] space-y-7 pb-12">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-[10px] font-bold uppercase tracking-[.18em] text-emerald-700">OPERATIONS / {user?.department_id}</p>
          <h1 className="mt-2 text-3xl font-semibold tracking-[-.05em] text-[#182c22] sm:text-[2.6rem]">Control room</h1>
          <p className="mt-2 text-sm text-[#728078]">Real queued assignments and open shift exceptions.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button onClick={() => void load()} disabled={fetching} className="inline-flex min-h-11 items-center gap-2 rounded-xl border border-[#d9e4db] bg-white px-4 text-xs font-semibold disabled:opacity-50"><RefreshCw className="h-4 w-4" />Refresh</button>
          <button onClick={() => {setFormError('');setOpen(true);}} className="inline-flex min-h-11 items-center gap-2 rounded-xl bg-[#15563f] px-5 text-xs font-semibold text-white hover:bg-[#0e3a2c]"><Plus className="h-4 w-4" />New assignment</button>
        </div>
      </header>
      {error ? <p role="alert" className="rounded-xl border border-red-200 bg-red-50 p-4 text-xs text-red-800">{error}</p> : null}
      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-label="Department metrics">
        {[
          { title: 'Work queued', value: items.length, icon: ClipboardList },
          { title: 'Assigned', value: assigned, icon: UsersRound },
          { title: 'High priority', value: priorityCount, icon: AlertTriangle },
          { title: 'Handover reviews', value: pending, icon: Clock3 },
        ].map(metric => <div key={metric.title} className="rounded-2xl border border-[#dce5dc] bg-white p-5">
          <div className="flex items-center justify-between"><span className="text-xs text-[#708177]">{metric.title}</span><metric.icon className="h-4 w-4 text-emerald-700" /></div>
          <p className="mt-4 text-4xl font-semibold tabular-nums tracking-tight text-[#142e20]">{fetching || error ? '—' : metric.value}</p>
        </div>)}
      </section>
      <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1.5fr)_minmax(18rem,.7fr)]">
        <section className="min-w-0 overflow-hidden rounded-[1.5rem] border border-[#d9e4db] bg-white">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#edf0eb] p-5 sm:px-6">
            <div><h2 className="text-lg font-semibold text-[#1a3325]">Live queue</h2><p className="mt-1 text-xs text-[#708177]">Priority-first · assignments saved in PostgreSQL</p></div>
            <Link href="/workspace" className="inline-flex items-center gap-2 text-xs font-bold text-emerald-700">View all <ArrowRight className="h-4 w-4" /></Link>
          </div>
          {fetching ? <div className="p-8"><LoadingState label="Loading work queue" /></div> : ordered.length ? (
            <div className="divide-y divide-[#edf0eb]">
              {ordered.map(item => <Link key={item.id} href={'/work/' + encodeURIComponent(item.id)} className="group flex min-w-0 items-center gap-4 px-5 py-4 hover:bg-[#f7faf7] sm:px-6">
                <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-[#eff5f0] text-[#22644a]"><Layers3 className="h-[18px] w-[18px]" /></span>
                <div className="min-w-0 flex-1"><p className="truncate text-sm font-semibold text-[#1a3227]">{item.title}</p><p className="mt-1 truncate text-xs text-[#78877e]">{workTypeLabel(item.work_type)} · {item.assigned_to || 'Not assigned'}</p></div>
                <div className="flex items-center gap-2">
                  {item.priority === 'high' ? <span className="rounded-md bg-amber-50 px-2 py-1 text-[10px] font-bold text-amber-800">HIGH</span> : null}
                  <ArrowUpRight className="h-4 w-4 text-[#688878] group-hover:text-emerald-700" />
                </div>
              </Link>)}
            </div>
          ) : <div className="px-6 py-12 text-center"><Inbox className="mx-auto h-7 w-7 text-[#6e9680]" /><p className="mt-3 text-sm font-semibold">The queue is clear</p><p className="mt-2 text-xs text-[#76887c]">Create an assignment to begin tracking work.</p></div>}
        </section>
        <aside className="space-y-4">
          <Link href="/handover/review" className="group block rounded-[1.5rem] border border-[#214b35] bg-[#143c2b] p-6 text-white">
            <span className="inline-flex items-center gap-2 text-[10px] font-bold uppercase tracking-[.13em] text-[#b5e8c9]"><AlertTriangle className="h-4 w-4" />Exception desk</span>
            <p className="mt-5 text-4xl font-semibold tracking-tight">{fetching || error ? '—' : pending}</p>
            <p className="mt-1 text-sm text-[#c7decf]">Awaiting human review</p>
            <div className="mt-5 flex items-center justify-between border-t border-white/15 pt-4 text-xs"><span>{urgent} high or critical priority</span><ArrowUpRight className="h-5 w-5 transition group-hover:translate-x-1" /></div>
          </Link>
          <div className="rounded-[1.4rem] border border-[#dce6dd] bg-white p-5">
            <h3 className="text-sm font-semibold">Management tools</h3>
            {[
              {label:'Review handovers',href:'/handover/review'},
              ...(user?.role === 'admin' ? [{label:'Procedure studio',href:'/procedure-studio'}] : []),
              {label:'Operational insights',href:'/intelligence-hub'},
            ].map(item => <Link href={item.href} key={item.href} className="flex min-h-12 items-center justify-between border-b border-[#edf1ec] text-xs font-semibold text-[#496452] last:border-0 hover:text-emerald-800">{item.label}<ArrowRight className="h-4 w-4" /></Link>)}
          </div>
          <div className="flex gap-3 rounded-xl border border-[#dce5dc] bg-[#f4f8f4] p-4"><ShieldCheck className="h-5 w-5 shrink-0 text-emerald-700" /><p className="text-xs leading-6 text-[#69766e]">Queue metrics show created tasks, not completed work or proven productivity gains.</p></div>
        </aside>
      </div>

      {open ? <div className="fixed inset-0 z-50 flex items-center justify-center bg-[#091a13]/60 px-4 py-8" role="presentation">
        <div role="dialog" aria-modal="true" aria-labelledby="new-work-title" className="max-h-[92vh] w-full max-w-xl overflow-y-auto rounded-[1.7rem] bg-white p-6 shadow-2xl sm:p-8">
          <div className="flex items-start justify-between gap-4"><div><p className="text-[10px] font-bold uppercase tracking-widest text-emerald-700">WORK INTAKE</p><h2 id="new-work-title" className="mt-2 text-2xl font-semibold tracking-tight">Create assignment</h2><p className="mt-1 text-xs leading-5 text-[#77857a]">Queue a task for your department. Execution begins in a later release.</p></div><button type="button" aria-label="Close assignment" onClick={() => setOpen(false)} className="rounded-lg p-2 hover:bg-slate-100"><X className="h-5 w-5" /></button></div>
          <form onSubmit={event => void submit(event)} className="mt-6 space-y-4">
            <div><label htmlFor="wi-title" className="wm-label">Task title</label><input id="wi-title" className="wm-input" required minLength={5} maxLength={180} value={title} onChange={event => setTitle(event.target.value)} placeholder="Inspect inbound shipment 101" /></div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div><label htmlFor="wi-type" className="wm-label">Work type</label><select id="wi-type" className="wm-input" value={workType} onChange={event => setWorkType(event.target.value as WorkType)}>{WORK_TYPES.map(type => <option key={type.value} value={type.value}>{type.label}</option>)}</select></div>
              <div><label htmlFor="wi-priority" className="wm-label">Priority</label><select id="wi-priority" className="wm-input" value={priority} onChange={event => setPriority(event.target.value as WorkPriority)}><option value="standard">Standard</option><option value="high">High priority</option></select></div>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div><label htmlFor="wi-assignee" className="wm-label">Assign employee</label><select id="wi-assignee" className="wm-input" value={assignee} onChange={event => setAssignee(event.target.value)}><option value="">Unassigned</option>{staff.map(person => <option key={person.id} value={person.id}>{person.label}</option>)}</select></div>
              <div><label htmlFor="wi-ref" className="wm-label">External reference (optional)</label><input id="wi-ref" className="wm-input" maxLength={100} value={reference} onChange={event => setReference(event.target.value)} placeholder="GRN-2071" /></div>
            </div>
            <div><label htmlFor="wi-instructions" className="wm-label">Brief (optional)</label><textarea id="wi-instructions" className="wm-input min-h-24" maxLength={1200} value={instructions} onChange={event => setInstructions(event.target.value)} placeholder="What should the assigned employee check?" /></div>
            {formError ? <p role="alert" className="rounded-lg bg-red-50 p-3 text-xs text-red-700">{formError}</p> : null}
            <div className="flex justify-end gap-2 pt-2"><button type="button" onClick={() => setOpen(false)} className="rounded-xl border border-[#dce4dc] px-5 py-3 text-xs font-semibold">Cancel</button><button type="submit" disabled={saving || title.trim().length < 5} className="rounded-xl bg-[#15583e] px-5 py-3 text-xs font-semibold text-white disabled:opacity-50">{saving ? 'Saving…' : 'Queue assignment'}</button></div>
          </form>
        </div>
      </div> : null}
    </div>
  );
}
