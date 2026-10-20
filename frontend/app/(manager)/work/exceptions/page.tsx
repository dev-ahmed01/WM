'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { AlertTriangle, ArrowRight, CheckCircle2, Clock3, FileText, RefreshCw, ShieldAlert, UserRoundCheck } from 'lucide-react';
import { useRequireRole } from '@/lib/auth';
import { apiClient } from '@/lib/api-client';
import { LoadingState } from '@/components/shared/LoadingState';

type CaseStatus = 'open' | 'claimed' | 'follow_up_requested' | 'reviewed';
type WorkCase = {
  id: string; department_id: string; work_item_id: string; work_title: string;
  work_status: string; work_assignee: string | null; raised_by: string;
  execution_session_id: string; reviewer_id: string | null;
  trigger: 'worker_report'|'sop_outcome'; severity: 'high'|'critical';
  reason: string; state_id: string | null; decision_option: string | null;
  status: CaseStatus; revision: number; review_note: string | null;
  handover_id?:string|null; handover_status?:string|null;
  created_at: string; updated_at: string; reviewed_at: string | null;
};
type CaseEvent = {id:string;actor_id:string;action:string;note:string;event_seq:number;created_at:string};
type WorkEvent = {id:string;actor_id:string;action:string;event_payload:Record<string,unknown>;created_at:string};
type CaseDetail = WorkCase & {events:CaseEvent[];work_events:WorkEvent[]};

const formatTime=(value:string)=>new Date(value).toLocaleString('en-IN',{
  timeZone:'Asia/Kolkata',day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit',hour12:true,
});
const statusText=(status:CaseStatus)=>status.replaceAll('_',' ');
const active=(value:CaseStatus)=>value==='open'||value==='claimed';
const elapsed=(value:string,now:number)=>{
  const minutes=Math.max(0,Math.floor((now-Date.parse(value))/60000));
  if(minutes<60)return minutes+'m';
  if(minutes<1440)return Math.floor(minutes/60)+'h '+(minutes%60)+'m';
  return Math.floor(minutes/1440)+'d '+Math.floor(minutes%1440/60)+'h';
};

export default function SupervisorExceptionDesk() {
  const { user, loading }=useRequireRole(['admin','manager']);
  const [items,setItems]=useState<WorkCase[]>([]);
  const [selected,setSelected]=useState<CaseDetail|null>(null);
  const [selectedId,setSelectedId]=useState<string|null>(null);
  const [fetching,setFetching]=useState(true);
  const [working,setWorking]=useState(false);
  const [error,setError]=useState('');
  const [actionError,setActionError]=useState('');
  const [note,setNote]=useState('');
  const [showAll,setShowAll]=useState(false);
  const [now,setNow]=useState(()=>Date.now());
  const [actionNote,setActionNote]=useState('');

  const refresh=useCallback(async()=>{
    setFetching(true);setError('');
    try {
      const response=await apiClient<{items:WorkCase[]}>('/work/exceptions?limit=100');
      setItems(response.items||[]);
    } catch (caught) {setError(caught instanceof Error?caught.message:'Exception records unavailable.');}
    finally {setFetching(false);}
  },[]);

  useEffect(()=>{
    if(loading||!user)return;
    let current=true;
    void apiClient<{items:WorkCase[]}>('/work/exceptions?limit=100')
      .then(res=>{if(current)setItems(res.items||[]);})
      .catch(err=>{if(current)setError(err instanceof Error?err.message:'Exception records unavailable.');})
      .finally(()=>{if(current)setFetching(false);});
    return()=>{current=false;};
  },[loading,user?.sub,user?.department_id]);

  useEffect(()=>{
    if(!selectedId){setSelected(null);return;}
    let current=true;
    void apiClient<CaseDetail>('/work/exceptions/'+encodeURIComponent(selectedId))
      .then(res=>{if(current){setSelected(res);setActionError('');}})
      .catch(err=>{if(current){setSelected(null);setActionError(err instanceof Error?err.message:'Could not open this case.');}});
    return()=>{current=false;};
  },[selectedId]);

  useEffect(()=>{
    const interval=setInterval(()=>setNow(Date.now()),60000);
    return()=>clearInterval(interval);
  },[]);
  const visible=useMemo(()=>items.filter(item=>showAll||active(item.status)),[items,showAll]);
  const openCount=items.filter(x=>active(x.status)).length;
  const criticalCount=items.filter(x=>active(x.status)&&x.severity==='critical').length;
  const canClaim=selected?.status==='open'&&!selected.reviewer_id&&selected.raised_by!==user?.sub;
  const canRecord=Boolean(selected&&selected.reviewer_id===user?.sub&&selected.raised_by!==user?.sub&&selected.work_status==='blocked');
  const hasContainment=selected?.events.some(event=>event.action==='containment_recorded')||false;
  const canReview=Boolean(selected&&active(selected.status)&&selected.raised_by!==user?.sub&&
    (!selected.reviewer_id||selected.reviewer_id===user?.sub));

  async function updateCase(action:'claim'|'reviewed'|'follow_up_requested'){
    if(!selected||working)return;
    if(action!=='claim'&&note.trim().length<8)return;
    setWorking(true);setActionError('');
    try{
      const route='/work/exceptions/'+encodeURIComponent(selected.id)+'/'+(action==='claim'?'claim':'review');
      await apiClient(route,{method:'POST',body:JSON.stringify(
        action==='claim'?{expected_revision:selected.revision}:
        {expected_revision:selected.revision,decision:action,review_note:note.trim()}
      )});
      const [detail,list]=await Promise.all([
        apiClient<CaseDetail>('/work/exceptions/'+encodeURIComponent(selected.id)),
        apiClient<{items:WorkCase[]}>('/work/exceptions?limit=100'),
      ]);
      setSelected(detail);setItems(list.items||[]);setNote('');
    }catch(caught){setActionError(caught instanceof Error?caught.message:'Review was not recorded.');}
    finally{setWorking(false);}
  }


  async function recordAction(kind:'containment_recorded'|'remediation_proposed'){
    if(!selected||working||actionNote.trim().length<12||!canRecord)return;
    setWorking(true);setActionError('');
    try{
      await apiClient('/work/exceptions/'+encodeURIComponent(selected.id)+'/action',{
        method:'POST',body:JSON.stringify({
          expected_revision:selected.revision,kind,note:actionNote.trim(),
        }),
      });
      const [detail,list]=await Promise.all([
        apiClient<CaseDetail>('/work/exceptions/'+encodeURIComponent(selected.id)),
        apiClient<{items:WorkCase[]}>('/work/exceptions?limit=100'),
      ]);
      setSelected(detail);setItems(list.items||[]);setActionNote('');
    }catch(caught){setActionError(caught instanceof Error?caught.message:'Containment action was not recorded.');}
    finally{setWorking(false);}
  }

  if(loading)return <LoadingState label="Opening supervisor exception desk"/>;
  return <div className="wm-page max-w-[1500px] space-y-6 pb-12">
    <header className="flex flex-wrap items-end justify-between gap-4">
      <div>
        <p className="text-[10px] font-bold uppercase tracking-[.17em] text-emerald-700">OPERATIONS / SUPERVISOR</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-[-.045em] text-[#1c3527] sm:text-[2.5rem]">Task exceptions</h1>
        <p className="mt-2 text-sm text-[#6c8071]">Blocked assignments and published SOP escalations, with their execution records.</p>
      </div>
      <div className="flex items-center gap-2">
        <Link href="/control-room" className="rounded-xl border border-[#dce7dd] bg-white px-4 py-3 text-xs font-semibold text-emerald-900">Control room</Link>
        <button type="button" disabled={fetching} onClick={()=>void refresh()} aria-label="Refresh exceptions" className="rounded-xl border border-[#dce7dd] bg-white p-3 disabled:opacity-50"><RefreshCw className="h-4 w-4 text-emerald-800"/></button>
      </div>
    </header>
    {error?<p role="alert" className="rounded-xl border border-red-200 bg-red-50 p-4 text-xs text-red-700">{error}</p>:null}
    <div className="grid gap-3 sm:grid-cols-3">
      {[
        {label:'Awaiting action',value:openCount,icon:Clock3},
        {label:'Critical holds',value:criticalCount,icon:ShieldAlert},
        {label:'Longest open',value:openCount?elapsed(items.filter(x=>active(x.status)).reduce((old,x)=>Date.parse(x.created_at)<Date.parse(old)?x.created_at:old,items.find(x=>active(x.status))!.created_at),now):'—',icon:Clock3},
      ].map(metric=><div key={metric.label} className="rounded-[1.2rem] border border-[#dce7de] bg-white p-5">
        <div className="flex items-center justify-between text-xs text-[#708276]"><span>{metric.label}</span><metric.icon className="h-4 w-4 text-emerald-700"/></div>
        <p className="mt-3 text-3xl font-semibold tabular-nums text-[#173824]">{fetching?'—':metric.value}</p>
      </div>)}
    </div>
    <div className="grid items-start gap-5 xl:grid-cols-[minmax(17rem,.9fr)_minmax(0,1.2fr)]">
      <section className="overflow-hidden rounded-[1.5rem] border border-[#dce5de] bg-white">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#eaf0eb] p-5">
          <div><h2 className="text-lg font-semibold">Review queue</h2><p className="mt-1 text-xs text-[#738375]">Critical and oldest unresolved first</p></div>
          <label className="flex items-center gap-2 text-[11px] font-semibold text-[#506e58]"><input type="checkbox" checked={showAll} onChange={e=>setShowAll(e.target.checked)} className="h-4 w-4 accent-emerald-700"/>Include reviewed</label>
        </div>
        {fetching?<div className="p-5"><LoadingState label="Reading incidents"/></div>:
        visible.length?<div className="divide-y divide-[#edf1ed]">{visible.map(item=><button type="button"
          key={item.id} onClick={()=>{setSelectedId(item.id);setNote('');}}
          aria-pressed={selectedId===item.id} className={'flex w-full items-start gap-3 p-5 text-left transition hover:bg-[#f6faf6] '+(selectedId===item.id?'bg-[#edf6ef]':'')}>
          <div className={'grid h-10 w-10 shrink-0 place-items-center rounded-xl '+(item.severity==='critical'?'bg-red-50 text-red-700':'bg-amber-50 text-amber-700')}><AlertTriangle className="h-5 w-5"/></div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-semibold text-[#20392a]">{item.work_title}</p>
            <p className="mt-1 line-clamp-2 text-xs leading-5 text-[#6d7c71]">{item.reason}</p>
            <p className="mt-2 text-[10px] font-semibold text-[#708672]">{item.severity.toUpperCase()} · {statusText(item.status)} · {elapsed(item.created_at,now)} since report</p>
          </div><ArrowRight className="mt-1 h-4 w-4 text-[#66856c]"/>
        </button>)}</div>:
        <div className="p-10 text-center"><CheckCircle2 className="mx-auto h-7 w-7 text-emerald-700"/><p className="mt-3 text-sm font-semibold">No outstanding cases</p><p className="mt-1 text-xs text-[#718473]">Exceptions appear when a work item is blocked.</p></div>}
      </section>
      <section className="rounded-[1.5rem] border border-[#dce5de] bg-white p-5 sm:p-7">
        {!selected?<div className="grid min-h-64 place-content-center text-center"><FileText className="mx-auto h-8 w-8 text-[#92b19b]"/><h2 className="mt-3 text-base font-semibold">Select an exception</h2><p className="mt-2 text-xs text-[#748276]">Review the linked work, recorded events and next action.</p></div>:
        <div className="space-y-5">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div><p className="text-[10px] font-bold uppercase tracking-[.13em] text-emerald-800">CASE / {selected.id.slice(-8).toUpperCase()}</p><h2 className="mt-2 text-xl font-semibold tracking-tight">{selected.work_title}</h2><p className="mt-2 text-xs text-[#708174]">{formatTime(selected.created_at)} · Reported by {selected.raised_by}</p></div>
            <span className={'rounded-lg px-3 py-2 text-xs font-semibold '+(selected.severity==='critical'?'bg-red-50 text-red-800':'bg-amber-50 text-amber-800')}>{selected.severity.toUpperCase()}</span>
          </div>
          <div className="rounded-xl border border-amber-200 bg-amber-50 p-4">
            <p className="text-xs font-semibold text-amber-950">Execution remains blocked</p>
            <p className="mt-1 text-xs leading-6 text-amber-900">A review or acknowledgment does not release safety controls or independently verify physical evidence.</p>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="rounded-xl bg-[#f4f8f4] p-4"><p className="text-[10px] font-semibold uppercase text-[#67816b]">Task state</p><p className="mt-2 text-sm font-semibold capitalize">{selected.work_status}</p><p className="mt-1 text-[11px] text-[#738576]">{elapsed(selected.created_at,now)} since report</p></div>
            <div className="rounded-xl bg-[#f4f8f4] p-4"><p className="text-[10px] font-semibold uppercase text-[#67816b]">Review owner</p><p className="mt-2 truncate text-sm font-semibold">{selected.reviewer_id||'Unassigned'}</p></div>
          </div>
          <div><p className="text-[10px] font-bold uppercase tracking-[.12em] text-[#66826b]">Incident</p><p className="mt-2 whitespace-pre-wrap break-words text-sm leading-6">{selected.reason}</p>
            {selected.decision_option?<p className="mt-2 text-xs text-[#7b857c]">Published decision: {selected.decision_option}</p>:null}
          </div>
          <Link href={'/work/'+encodeURIComponent(selected.work_item_id)} className="inline-flex items-center gap-2 text-xs font-bold text-emerald-800">Open linked work and evidence timeline <ArrowRight className="h-4 w-4"/></Link>
          <div className="rounded-xl border border-[#e2e9e1] bg-[#f7faf6] p-4">
            <p className="text-xs font-bold text-[#305b3c]">Shift continuity</p>
            {selected.handover_id?<div className="mt-2 space-y-2">
              <p className="text-xs text-[#53735c]">Linked handover: {selected.handover_id} · {selected.handover_status}</p>
              <Link href="/handover/review" className="inline-flex items-center gap-1 text-xs font-semibold text-emerald-800">Open shift handover reviews <ArrowRight className="h-4 w-4"/></Link>
            </div>:<p className="mt-2 text-xs text-[#7b8d7d]">No linked shift handover yet. The originating worker can submit one from the blocked assignment.</p>}
          </div>
          <div className="border-t border-[#e6eee6] pt-5">
            <h3 className="text-sm font-semibold">Audit trail</h3>
            <div className="mt-3 space-y-3">{selected.events.map(event=><div key={event.id} className="flex gap-3 rounded-lg bg-[#f8faf7] p-3">
              <span className="mt-1 h-2 w-2 shrink-0 rounded-full bg-emerald-500"/>
              <div className="min-w-0"><p className="text-xs font-semibold capitalize">{event.action.replaceAll('_',' ')}</p><p className="mt-1 text-[11px] text-[#788678]">{event.actor_id} · {formatTime(event.created_at)}</p>
                {event.note?<p className="mt-1 whitespace-pre-wrap break-words text-xs leading-5 text-[#4d6553]">{event.note}</p>:null}
              </div>
            </div>)}</div>
          </div>
          {canRecord?<div className="space-y-3 border-t border-[#e6eee6] pt-5">
            <h3 className="text-sm font-semibold">Containment and remediation</h3>
            <p className="text-xs leading-5 text-[#6c806f]">Record what was actually done, then propose a separately approved remediation. Neither action unblocks work.</p>
            <label htmlFor="case-containment-note" className="wm-label">Operational action note</label>
            <textarea id="case-containment-note" rows={3} minLength={12} maxLength={1000}
              className="wm-input min-h-24" value={actionNote}
              onChange={e=>setActionNote(e.target.value)}
              placeholder="Goods isolated in bay 4, awaiting on-site verification."/>
            <div className="flex flex-wrap gap-2">
              <button type="button" disabled={working||actionNote.trim().length<12}
                onClick={()=>void recordAction('containment_recorded')}
                className="min-h-11 rounded-xl bg-[#165b3e] px-4 text-xs font-semibold text-white disabled:opacity-50">Record containment</button>
              <button type="button" disabled={working||!hasContainment||actionNote.trim().length<12}
                onClick={()=>void recordAction('remediation_proposed')}
                className="min-h-11 rounded-xl border border-[#bcd9c4] px-4 text-xs font-semibold text-[#28593c] disabled:opacity-50">Propose remediation</button>
            </div>
          </div>:null}
          {actionError?<p role="alert" className="rounded-xl bg-red-50 p-3 text-xs text-red-800">{actionError}</p>:null}
          {canClaim?<button type="button" disabled={working} onClick={()=>void updateCase('claim')} className="inline-flex min-h-11 items-center gap-2 rounded-xl border border-[#bad6c0] bg-[#f0f8f1] px-4 text-xs font-semibold text-emerald-900 disabled:opacity-50"><UserRoundCheck className="h-4 w-4"/>Take ownership</button>:null}
          {canReview?<div className="border-t border-[#e6eee6] pt-5">
            <label htmlFor="case-review-note" className="wm-label">Supervisor review note</label>
            <textarea id="case-review-note" rows={3} maxLength={1000} className="wm-input min-h-24" value={note} onChange={e=>setNote(e.target.value)} placeholder="Record containment actions, follow-up owner or acknowledged observations."/>
            <div className="mt-3 flex flex-wrap gap-2">
              <button type="button" disabled={working||note.trim().length<8} onClick={()=>void updateCase('reviewed')} className="min-h-11 rounded-xl bg-[#165b3e] px-4 text-xs font-semibold text-white disabled:opacity-50">Record review</button>
              <button type="button" disabled={working||note.trim().length<8} onClick={()=>void updateCase('follow_up_requested')} className="min-h-11 rounded-xl border border-[#dbe8dd] px-4 text-xs font-semibold text-[#28593c] disabled:opacity-50">Request follow-up</button>
            </div>
          </div>:selected.review_note?<p className="rounded-xl bg-[#f4f8f4] p-4 text-xs leading-6 text-[#4d6e54]">Supervisor record: {selected.review_note}</p>:null}
        </div>}
      </section>
    </div>
  </div>;
}
