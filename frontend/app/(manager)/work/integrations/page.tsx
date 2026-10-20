'use client';

import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react';
import Link from 'next/link';
import { ArrowRight, CheckCircle2, FileInput, RefreshCw, ShieldCheck } from 'lucide-react';
import { useRequireRole } from '@/lib/auth';
import { apiClient } from '@/lib/api-client';
import { LoadingState } from '@/components/shared/LoadingState';
import { IntegrationSourcesPanel } from '@/components/work/IntegrationSourcesPanel';

type System = 'sap'|'oracle'|'odoo'|'custom_wms';
type Type = 'receiving'|'putaway'|'stock_count'|'picking'|'dispatch'|'other';
type WorkIntake = {
  id:string;source_system:System;external_event_id:string;external_work_id:string;
  normalized_payload:{title:string;work_type:Type;priority:'standard'|'high';instructions:string;assigned_to:string|null};
  status:'pending'|'accepted'|'rejected';submitted_by:string;decided_by:string|null;
  decision_note:string|null;work_item_id:string|null;created_at:string;replayed?:boolean;
};
type Person={id:string;label:string};

const sources:{value:System;label:string}[]=[
  {value:'custom_wms',label:'Warehouse management system'},
  {value:'sap',label:'SAP source format'},
  {value:'oracle',label:'Oracle source format'},
  {value:'odoo',label:'Odoo source format'},
];
const types:Type[]=['receiving','putaway','stock_count','picking','dispatch','other'];
const time=(iso:string)=>new Date(iso).toLocaleString('en-IN',{
  timeZone:'Asia/Kolkata',day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit',
});

export default function IntegrationInbox(){
  const {user,loading}=useRequireRole(['admin','manager']);
  const [items,setItems]=useState<WorkIntake[]>([]);
  const [people,setPeople]=useState<Person[]>([]);
  const [fetching,setFetching]=useState(true);
  const [working,setWorking]=useState(false);
  const [error,setError]=useState('');
  const [info,setInfo]=useState('');
  const [source,setSource]=useState<System>('custom_wms');
  const [eventId,setEventId]=useState('');
  const [externalWorkId,setExternalWorkId]=useState('');
  const [title,setTitle]=useState('');
  const [workType,setWorkType]=useState<Type>('receiving');
  const [priority,setPriority]=useState<'standard'|'high'>('standard');
  const [instructions,setInstructions]=useState('');
  const [assignee,setAssignee]=useState('');
  const [selected,setSelected]=useState<string|null>(null);
  const [reviewNote,setReviewNote]=useState('');

  const load=useCallback(async()=>{
    setFetching(true);
    try{
      const [intake,workers]=await Promise.all([
        apiClient<{items:WorkIntake[]}>('/work/integrations/intake?limit=100'),
        apiClient<{items:Person[]}>('/work/items/assignees'),
      ]);
      setItems(intake.items||[]);setPeople(workers.items||[]);setError('');
    }catch(caught){setError(caught instanceof Error?caught.message:'Integration records unavailable.');}
    finally{setFetching(false);}
  },[]);

  useEffect(()=>{
    if(loading||!user)return;
    let alive=true;
    void Promise.all([
      apiClient<{items:WorkIntake[]}>('/work/integrations/intake?limit=100'),
      apiClient<{items:Person[]}>('/work/items/assignees'),
    ]).then(([a,b])=>{if(alive){setItems(a.items||[]);setPeople(b.items||[]);setFetching(false);}})
      .catch(err=>{if(alive){setError(err instanceof Error?err.message:'Integration inbox is unavailable.');setFetching(false);}});
    return()=>{alive=false;};
  },[loading,user?.sub,user?.department_id]);

  const pending=useMemo(()=>items.filter(item=>item.status==='pending'),[items]);
  const accepted=useMemo(()=>items.filter(item=>item.status==='accepted').length,[items]);
  const focus=items.find(item=>item.id===selected)||null;
  const canReview=Boolean(focus?.status==='pending'&&focus.submitted_by!==user?.sub);

  async function submit(event:FormEvent<HTMLFormElement>){
    event.preventDefault();
    if(working||title.trim().length<5||eventId.trim().length<6||externalWorkId.trim().length<4)return;
    setWorking(true);setError('');setInfo('');
    try{
      const result=await apiClient<WorkIntake>('/work/integrations/intake',{
        method:'POST',body:JSON.stringify({
          source_system:source,external_event_id:eventId.trim(),
          external_work_id:externalWorkId.trim(),title:title.trim(),
          work_type:workType,priority,instructions:instructions.trim(),assigned_to:assignee||null,
        }),
      });
      setInfo(result.replayed?'Existing source event retained; no new task created.':'Source event staged for independent review.');
      setSelected(result.id);
      if(!result.replayed){setEventId('');setExternalWorkId('');setTitle('');setInstructions('');setAssignee('');}
      await load();
    }catch(caught){setError(caught instanceof Error?caught.message:'Import could not be staged.');}
    finally{setWorking(false);}
  }

  async function decide(decision:'accepted'|'rejected'){
    if(!canReview||!focus||working||reviewNote.trim().length<16)return;
    setWorking(true);setError('');setInfo('');
    try{
      await apiClient('/work/integrations/intake/'+encodeURIComponent(focus.id)+'/decision',{
        method:'POST',body:JSON.stringify({decision,decision_note:reviewNote.trim()}),
      });
      setReviewNote('');
      setInfo(decision==='accepted'?'Reviewed source work was queued; bind a published SOP before execution.':'Source work was rejected and no task was created.');
      await load();
    }catch(caught){setError(caught instanceof Error?caught.message:'Decision was not recorded.');}
    finally{setWorking(false);}
  }

  if(loading)return <LoadingState label="Opening integration inbox"/>;
  return <div className="wm-page max-w-[1420px] space-y-6 pb-12">
    <header className="flex flex-wrap items-end justify-between gap-4">
      <div>
        <p className="text-[10px] font-bold uppercase tracking-[.16em] text-emerald-800">OPERATIONS / CONNECTIONS</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-[-.045em] text-[#183527] sm:text-[2.5rem]">Integration inbox</h1>
        <p className="mt-2 text-sm text-[#687d6e]">Source work, independently reviewed before assignment.</p>
      </div>
      <div className="flex items-center gap-2">
        <Link href="/control-room" className="min-h-11 rounded-xl border border-[#d6e4d9] bg-white px-4 py-3 text-xs font-semibold text-[#285b3c]">Control room</Link>
        <button onClick={()=>void load()} disabled={fetching} aria-label="Refresh integration inbox"
          className="grid h-11 w-11 place-items-center rounded-xl border border-[#d6e4d9] bg-white disabled:opacity-50">
          <RefreshCw className="h-4 w-4"/></button>
      </div>
    </header>
    {error?<p role="alert" className="rounded-xl bg-red-50 p-4 text-xs text-red-800">{error}</p>:null}
    {info?<p role="status" className="rounded-xl border border-[#d8e8db] bg-[#f3faf4] p-4 text-xs font-medium text-[#295f41]">{info}</p>:null}
    <div className="grid grid-cols-2 gap-3 sm:max-w-lg">
      <div className="rounded-2xl border border-[#dae6dd] bg-white p-5"><p className="text-xs text-[#687e6f]">Awaiting review</p><p className="mt-3 text-3xl font-semibold tabular-nums text-[#193f2a]">{pending.length}</p></div>
      <div className="rounded-2xl border border-[#dae6dd] bg-white p-5"><p className="text-xs text-[#687e6f]">Queued after review</p><p className="mt-3 text-3xl font-semibold tabular-nums text-[#193f2a]">{accepted}</p></div>
    </div>
    <div className="grid items-start gap-5 xl:grid-cols-[minmax(300px,.85fr)_minmax(0,1.45fr)]">
      <section className="rounded-[1.5rem] border border-[#dae6dd] bg-white p-5 sm:p-6">
        <div className="mb-5 flex items-center gap-3"><FileInput className="h-5 w-5 text-emerald-800"/><h2 className="text-base font-semibold">Stage source work</h2></div>
        <form onSubmit={event=>void submit(event)} className="space-y-3">
          <div><label htmlFor="int-source" className="wm-label">Source format</label>
            <select id="int-source" className="wm-input" value={source} onChange={e=>setSource(e.target.value as System)}>
              {sources.map(s=><option key={s.value} value={s.value}>{s.label}</option>)}
            </select></div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div><label htmlFor="int-event" className="wm-label">External event ID</label>
              <input id="int-event" className="wm-input" required minLength={6} maxLength={100} value={eventId} onChange={e=>setEventId(e.target.value)} placeholder="receipt.received.1024"/></div>
            <div><label htmlFor="int-work" className="wm-label">External work ID</label>
              <input id="int-work" className="wm-input" required minLength={4} maxLength={80} value={externalWorkId} onChange={e=>setExternalWorkId(e.target.value)} placeholder="RECEIPT-1024"/></div>
          </div>
          <div><label htmlFor="int-title" className="wm-label">Work title</label>
            <input id="int-title" className="wm-input" required minLength={5} maxLength={180} value={title} onChange={e=>setTitle(e.target.value)} placeholder="Inspect incoming cartons"/></div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div><label htmlFor="int-type" className="wm-label">Work type</label>
              <select id="int-type" className="wm-input" value={workType} onChange={e=>setWorkType(e.target.value as Type)}>
                {types.map(t=><option key={t} value={t}>{t.replaceAll('_',' ')}</option>)}
              </select></div>
            <div><label htmlFor="int-priority" className="wm-label">Priority</label>
              <select id="int-priority" className="wm-input" value={priority} onChange={e=>setPriority(e.target.value as 'standard'|'high')}>
                <option value="standard">Standard</option><option value="high">High</option>
              </select></div>
          </div>
          <div><label htmlFor="int-assignee" className="wm-label">Intended worker</label>
            <select id="int-assignee" className="wm-input" value={assignee} onChange={e=>setAssignee(e.target.value)}>
              <option value="">Not assigned</option>{people.map(p=><option key={p.id} value={p.id}>{p.label}</option>)}
            </select></div>
          <div><label htmlFor="int-instructions" className="wm-label">Source instructions</label>
            <textarea id="int-instructions" rows={2} maxLength={1200} className="wm-input" value={instructions} onChange={e=>setInstructions(e.target.value)} placeholder="Source order context; never an SOP override."/></div>
          <button type="submit" disabled={working||title.trim().length<5||eventId.trim().length<6||externalWorkId.trim().length<4}
            className="min-h-11 w-full rounded-xl bg-[#155a40] px-4 text-xs font-semibold text-white disabled:opacity-50">Stage for review</button>
        </form>
      </section>
      <section className="min-w-0 overflow-hidden rounded-[1.5rem] border border-[#dae6dd] bg-white">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#ebf0eb] px-5 py-5 sm:px-6">
          <h2 className="text-base font-semibold">Review source records</h2>
          <span className="text-xs text-[#718172]">Current department only</span>
        </div>
        <div className="grid lg:grid-cols-[minmax(15rem,.85fr)_minmax(0,1fr)]">
          <div className="max-h-[520px] overflow-y-auto border-b border-[#edf1ed] lg:border-b-0 lg:border-r">
            {items.length?items.map(entry=><button type="button" key={entry.id} onClick={()=>{setSelected(entry.id);setReviewNote('');}}
              aria-pressed={selected===entry.id} className={'w-full border-b border-[#edf1ed] px-5 py-4 text-left hover:bg-[#f5f9f5] '+(selected===entry.id?'bg-[#eff7ef]':'')}>
              <p className="truncate text-xs font-semibold text-[#1b3c28]">{entry.normalized_payload.title}</p>
              <p className="mt-1 truncate text-[11px] text-[#728275]">{entry.source_system.toUpperCase()} · {entry.external_work_id}</p>
              <p className="mt-2 text-[10px] font-semibold uppercase tracking-wider text-[#547d61]">{entry.status} · {time(entry.created_at)}</p>
            </button>):<p className="p-6 text-xs text-[#718477]">No integration records yet.</p>}
          </div>
          <div className="min-h-[310px] p-5 sm:p-6">
            {focus?<div className="space-y-4">
              <div><p className="text-[10px] font-bold uppercase tracking-widest text-emerald-800">{focus.source_system} / {focus.status}</p>
                <h3 className="mt-2 text-lg font-semibold text-[#1b3929]">{focus.normalized_payload.title}</h3>
                <p className="mt-2 text-xs text-[#758675]">{focus.external_event_id}</p></div>
              <div className="rounded-xl bg-[#f5f9f5] p-4 text-xs leading-6 text-[#42624d]">
                <p>Work ID: {focus.external_work_id}</p><p>Assigned: {focus.normalized_payload.assigned_to||'Unassigned'}</p>
                <p>Type: {focus.normalized_payload.work_type.replaceAll('_',' ')} · {focus.normalized_payload.priority}</p>
              </div>
              {focus.normalized_payload.instructions?<p className="whitespace-pre-wrap text-xs leading-6 text-[#4c6855]">{focus.normalized_payload.instructions}</p>:null}
              {focus.work_item_id?<Link href={'/work/'+encodeURIComponent(focus.work_item_id)} className="inline-flex items-center gap-2 text-xs font-bold text-emerald-800"><CheckCircle2 className="h-4 w-4"/>Open queued task <ArrowRight className="h-4 w-4"/></Link>:null}
              {focus.decision_note?<p className="text-xs text-[#516c59]">Decision by {focus.decided_by}: {focus.decision_note}</p>:null}
              {canReview?<div className="space-y-3 border-t border-[#dce8de] pt-4">
                <label htmlFor="int-review" className="wm-label">Independent review note</label>
                <textarea id="int-review" className="wm-input" rows={3} minLength={16} maxLength={1000} value={reviewNote} onChange={e=>setReviewNote(e.target.value)}
                  placeholder="Confirm the external order and intended routing; published SOP remains separate."/>
                <div className="flex flex-wrap gap-2">
                  <button type="button" disabled={working||reviewNote.trim().length<16} onClick={()=>void decide('accepted')} className="min-h-11 rounded-xl bg-[#155a40] px-4 text-xs font-semibold text-white disabled:opacity-50">Accept into queue</button>
                  <button type="button" disabled={working||reviewNote.trim().length<16} onClick={()=>void decide('rejected')} className="min-h-11 rounded-xl border border-[#b9d2bd] px-4 text-xs font-semibold text-[#316645] disabled:opacity-50">Reject import</button>
                </div>
              </div>:focus.status==='pending'?<p className="flex gap-2 text-xs text-[#58775f]"><ShieldCheck className="h-4 w-4 shrink-0"/>A different manager must review this import.</p>:null}
            </div>:<div className="grid min-h-64 place-content-center text-center"><ShieldCheck className="mx-auto h-7 w-7 text-[#719c7b]"/><p className="mt-3 text-xs text-[#788b7a]">Select a source record to review.</p></div>}
          </div>
        </div>
      </section>
    </div>
    {user?.role==='admin'?<IntegrationSourcesPanel/>:null}
    <p className="text-xs text-[#738275]">Signed custom connectors require separately configured secrets. Native vendor SDKs, bidirectional synchronization and automatic SOP execution remain disabled.</p>
  </div>;
}
