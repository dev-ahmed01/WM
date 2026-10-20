'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { AlertTriangle, ArrowRight, CheckCircle2, Clock3, FileText, RefreshCw, ShieldAlert, UserRoundCheck } from 'lucide-react';
import { useRequireRole } from '@/lib/auth';
import { apiClient } from '@/lib/api-client';
import { LoadingState } from '@/components/shared/LoadingState';

type CaseStatus = 'open' | 'claimed' | 'follow_up_requested' | 'reviewed' | 'closed';
type WorkCase = {
  id: string; department_id: string; work_item_id: string; work_title: string;
  work_status: string; work_assignee: string | null; raised_by: string;
  execution_session_id: string; reviewer_id: string | null;
  trigger: 'worker_report'|'sop_outcome'; severity: 'high'|'critical';
  reason: string; state_id: string | null; decision_option: string | null;
  status: CaseStatus; revision: number; review_note: string | null;
  handover_id?:string|null; handover_status?:string|null;
  corrective_status?:'pending'|'approved'|'rejected'|null;
  corrective_work_status?:'ready'|'active'|'paused'|'blocked'|'completed'|null;
  evidence_reviewed_at?:string|null; site_accepted_at?:string|null;
  created_at: string; updated_at: string; reviewed_at: string | null;
};
type CaseEvent = {id:string;actor_id:string;action:string;note:string;event_seq:number;created_at:string};
type WorkEvent = {id:string;actor_id:string;action:string;event_payload:Record<string,unknown>;created_at:string};
type CorrectivePlan={id:string;status:'pending'|'approved'|'rejected';proposed_by:string;
  proposed_at:string;workflow_version_id:string;assigned_to:string;
  procedure_title:string;plan_note:string;decided_by:string|null;
  decision_note:string|null;decided_at:string|null;corrective_work_id:string|null};
type PublishedProcedure={workflow_version_id:string;title:string;version_number:number};
type WorkerOption={id:string;label:string};
type CaseClosure={id:string;corrective_work_id:string;corrective_session_id:string;
  evidence_reviewed_by:string;evidence_review_note:string;evidence_reviewed_at:string;
  evidence_snapshot:{recorded_step_count:number;received_evidence:Array<{submission_id:string;sha256:string;bytes:number;verification:string}>};
  site_accepted_by:string|null;site_record_reference:string|null;site_acceptance_note:string|null;site_accepted_at:string|null};
type CaseDetail = WorkCase & {events:CaseEvent[];work_events:WorkEvent[];
  corrective_request:CorrectivePlan|null;closure:CaseClosure|null};

const formatTime=(value:string)=>new Date(value).toLocaleString('en-IN',{
  timeZone:'Asia/Kolkata',day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit',hour12:true,
});
const statusText=(status:CaseStatus)=>status.replaceAll('_',' ');
const active=(value:CaseStatus)=>value==='open'||value==='claimed'||value==='follow_up_requested';
const unresolved=(item:WorkCase)=>item.status!=='closed';
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
  const [correctionNote,setCorrectionNote]=useState('');
  const [decisionNote,setDecisionNote]=useState('');
  const [evidenceNote,setEvidenceNote]=useState('');
  const [siteReference,setSiteReference]=useState('');
  const [siteNote,setSiteNote]=useState('');
  const [siteAttested,setSiteAttested]=useState(false);
  const [correctionVersion,setCorrectionVersion]=useState('');
  const [correctionAssignee,setCorrectionAssignee]=useState('');
  const [procedures,setProcedures]=useState<PublishedProcedure[]>([]);
  const [assignees,setAssignees]=useState<WorkerOption[]>([]);

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
  useEffect(()=>{
    if(loading||!user)return;
    let mounted=true;
    void Promise.all([
      apiClient<{items:PublishedProcedure[]}>('/work/execution/procedures'),
      apiClient<{items:WorkerOption[]}>('/work/items/assignees'),
    ]).then(([p,a])=>{
      if(mounted){setProcedures(p.items||[]);setAssignees(a.items||[]);}
    }).catch(()=>{if(mounted)setActionError('Approved procedures or worker directory could not be loaded.');});
    return()=>{mounted=false;};
  },[loading,user?.sub,user?.department_id]);

  const visible=useMemo(()=>items.filter(item=>showAll||unresolved(item)),[items,showAll]);
  const openCount=items.filter(unresolved).length;
  const criticalCount=items.filter(x=>unresolved(x)&&x.severity==='critical').length;
  const canClaim=selected?.status==='open'&&!selected.reviewer_id&&selected.raised_by!==user?.sub;
  const canRecord=Boolean(selected&&selected.reviewer_id===user?.sub&&selected.raised_by!==user?.sub&&selected.work_status==='blocked'&&selected.status!=='closed');
  const hasContainment=selected?.events.some(event=>event.action==='containment_recorded')||false;
  const hasRemediation=selected?.events.some(event=>event.action==='remediation_proposed')||false;
  const canPropose=Boolean(canRecord&&hasContainment&&hasRemediation
    &&(selected?.status==='reviewed'||selected?.status==='follow_up_requested')
    &&!selected?.corrective_request);
  const canIndependentlyApprove=Boolean(selected?.corrective_request?.status==='pending'
    &&user?.role==='admin'
    &&user?.sub!==selected.corrective_request.proposed_by
    &&user?.sub!==selected.reviewer_id
    &&user?.sub!==selected.raised_by
    &&user?.sub!==selected.corrective_request.assigned_to);
  const canReviewEvidence=Boolean(selected&&selected.status!=='closed'
    &&selected.reviewer_id===user?.sub
    &&selected.corrective_request?.status==='approved'
    &&selected.corrective_work_status==='completed'
    &&!selected.closure);
  const canAcceptSite=Boolean(selected&&selected.status!=='closed'&&selected.closure
    &&!selected.closure.site_accepted_at&&user?.role==='admin'
    &&user?.sub!==selected.raised_by&&user?.sub!==selected.reviewer_id
    &&user?.sub!==selected.corrective_request?.proposed_by
    &&user?.sub!==selected.corrective_request?.decided_by
    &&user?.sub!==selected.corrective_request?.assigned_to
    &&user?.sub!==selected.closure.evidence_reviewed_by);
  const canReview=Boolean(selected&&(selected.status==='open'||selected.status==='claimed')&&selected.raised_by!==user?.sub&&
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

  async function saveCorrectivePlan(){
    if(!selected||!canPropose||working||!correctionVersion||!correctionAssignee
      ||correctionNote.trim().length<20)return;
    setWorking(true);setActionError('');
    try{
      await apiClient('/work/exceptions/'+encodeURIComponent(selected.id)+'/corrective',{
        method:'POST',body:JSON.stringify({
          expected_revision:selected.revision,
          workflow_version_id:correctionVersion,
          assigned_to:correctionAssignee,plan_note:correctionNote.trim(),
        }),
      });
      const details=await apiClient<CaseDetail>('/work/exceptions/'+encodeURIComponent(selected.id));
      setSelected(details);setCorrectionNote('');
    }catch(err){setActionError(err instanceof Error?err.message:'Corrective request not saved.');}
    finally{setWorking(false);}
  }

  async function decideCorrective(decision:'approved'|'rejected'){
    if(!selected?.corrective_request||!canIndependentlyApprove||working||decisionNote.trim().length<16)return;
    setWorking(true);setActionError('');
    try{
      await apiClient(
        '/work/exceptions/'+encodeURIComponent(selected.id)+'/corrective/'
          +encodeURIComponent(selected.corrective_request.id)+'/decision',{
          method:'POST',body:JSON.stringify({decision,decision_note:decisionNote.trim()}),
        });
      const [detail,list]=await Promise.all([
        apiClient<CaseDetail>('/work/exceptions/'+encodeURIComponent(selected.id)),
        apiClient<{items:WorkCase[]}>('/work/exceptions?limit=100'),
      ]);
      setSelected(detail);setItems(list.items||[]);setDecisionNote('');
    }catch(err){setActionError(err instanceof Error?err.message:'Independent decision not recorded.');}
    finally{setWorking(false);}
  }


  async function reviewCorrectiveEvidence(){
    if(!selected||!canReviewEvidence||working||evidenceNote.trim().length<20)return;
    setWorking(true);setActionError('');
    try{
      await apiClient('/work/exceptions/'+encodeURIComponent(selected.id)+'/closure/evidence',{
        method:'POST',body:JSON.stringify({
          expected_revision:selected.revision,review_note:evidenceNote.trim(),
        }),
      });
      const [detail,list]=await Promise.all([
        apiClient<CaseDetail>('/work/exceptions/'+encodeURIComponent(selected.id)),
        apiClient<{items:WorkCase[]}>('/work/exceptions?limit=100'),
      ]);
      setSelected(detail);setItems(list.items||[]);setEvidenceNote('');
    }catch(caught){setActionError(caught instanceof Error?caught.message:'Evidence review was not recorded.');}
    finally{setWorking(false);}
  }

  async function acceptSite(){
    if(!selected||!canAcceptSite||working||!siteAttested
      ||siteReference.trim().length<8||siteNote.trim().length<30)return;
    setWorking(true);setActionError('');
    try{
      await apiClient('/work/exceptions/'+encodeURIComponent(selected.id)+'/closure/site',{
        method:'POST',body:JSON.stringify({
          expected_revision:selected.revision,site_record_reference:siteReference.trim(),
          site_acceptance_note:siteNote.trim(),
          independent_site_inspection_attested:true,
        }),
      });
      const [detail,list]=await Promise.all([
        apiClient<CaseDetail>('/work/exceptions/'+encodeURIComponent(selected.id)),
        apiClient<{items:WorkCase[]}>('/work/exceptions?limit=100'),
      ]);
      setSelected(detail);setItems(list.items||[]);
      setSiteReference('');setSiteNote('');setSiteAttested(false);
    }catch(caught){setActionError(caught instanceof Error?caught.message:'Site acceptance was not recorded.');}
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
        {label:'Longest open',value:openCount?elapsed(items.filter(unresolved).reduce((old,x)=>Date.parse(x.created_at)<Date.parse(old)?x.created_at:old,items.find(unresolved)!.created_at),now):'—',icon:Clock3},
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
            <p className="mt-2 text-[10px] font-semibold text-[#708672]">{item.severity.toUpperCase()} · {item.corrective_status==='pending'?'Authorization pending':statusText(item.status)} · {elapsed(item.created_at,now)} since report</p>
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
          <div className="space-y-3 border-t border-[#e6eee6] pt-5">
            <h3 className="text-sm font-semibold">Independent corrective work</h3>
            <p className="text-xs leading-5 text-[#6c806f]">A second administrator must authorize any new task. Approval does not release the original blocked assignment.</p>
            {selected.corrective_request ? <div className="space-y-2 rounded-xl bg-[#f3f8f3] p-4">
              <p className="text-xs font-bold capitalize text-[#254b32]">Request {selected.corrective_request.status}</p>
              <p className="text-xs text-[#4b6553]">{selected.corrective_request.procedure_title} · {selected.corrective_request.workflow_version_id}</p>
              <p className="text-xs leading-5 text-[#526c59]">{selected.corrective_request.plan_note}</p>
              <p className="text-xs text-[#778678]">Proposed by {selected.corrective_request.proposed_by}</p>
              {selected.corrective_request.decision_note?<p className="text-xs font-semibold text-[#41604a]">Decision: {selected.corrective_request.decision_note}</p>:null}
              {selected.corrective_request.corrective_work_id?<Link className="inline-flex items-center gap-1 text-xs font-bold text-emerald-900"
                href={'/work/'+encodeURIComponent(selected.corrective_request.corrective_work_id)}>Open new corrective assignment <ArrowRight className="h-4 w-4"/></Link>:null}
              {canIndependentlyApprove?<div className="mt-4 space-y-3 border-t border-[#dbe7df] pt-4">
                <label htmlFor="independent-approval-note" className="wm-label">Independent decision and controls</label>
                <textarea id="independent-approval-note" rows={3} minLength={16} maxLength={1000}
                  className="wm-input" value={decisionNote} onChange={e=>setDecisionNote(e.target.value)}
                  placeholder="Confirm this published SOP is appropriate for corrective verification. Site clearance remains separate."/>
                <div className="flex flex-wrap gap-2">
                  <button type="button" disabled={working||decisionNote.trim().length<16}
                    onClick={()=>void decideCorrective('approved')}
                    className="min-h-11 rounded-xl bg-[#155a40] px-4 text-xs font-semibold text-white disabled:opacity-50">Authorize new task</button>
                  <button type="button" disabled={working||decisionNote.trim().length<16}
                    onClick={()=>void decideCorrective('rejected')}
                    className="min-h-11 rounded-xl border border-[#bdcdbd] px-4 text-xs font-semibold text-[#325a3b] disabled:opacity-50">Reject proposal</button>
                </div>
              </div>:null}
            </div> : canPropose?<div className="space-y-3 rounded-xl border border-[#e3eae2] p-4">
              <div><label htmlFor="corrective-procedure" className="wm-label">Published corrective SOP</label>
                <select id="corrective-procedure" value={correctionVersion} onChange={e=>setCorrectionVersion(e.target.value)} className="wm-input">
                  <option value="">Choose approved procedure</option>
                  {procedures.map(p=><option key={p.workflow_version_id} value={p.workflow_version_id}>{p.title} · v{p.version_number}</option>)}
                </select></div>
              <div><label htmlFor="corrective-assignee" className="wm-label">Corrective worker</label>
                <select id="corrective-assignee" value={correctionAssignee} onChange={e=>setCorrectionAssignee(e.target.value)} className="wm-input">
                  <option value="">Choose active worker</option>
                  {assignees.map(worker=><option key={worker.id} value={worker.id}>{worker.label}</option>)}
                </select></div>
              <div><label htmlFor="corrective-plan-note" className="wm-label">Scope and verification plan</label>
                <textarea id="corrective-plan-note" rows={3} minLength={20} maxLength={1000} className="wm-input"
                  value={correctionNote} onChange={e=>setCorrectionNote(e.target.value)}
                  placeholder="Inspect quarantined goods using approved SOP and record fresh evidence."/>
              </div>
              <button type="button" disabled={working||!correctionVersion||!correctionAssignee||correctionNote.trim().length<20}
                onClick={()=>void saveCorrectivePlan()}
                className="min-h-11 rounded-xl border border-[#bcd9c4] bg-[#eaf5ed] px-4 text-xs font-bold text-[#235737] disabled:opacity-50">
                Submit for independent authorization
              </button>
            </div>:<p className="text-xs text-[#75877a]">A reviewed incident with recorded containment and remediation is required before requesting corrective work.</p>}
          </div>

          <div className="space-y-3 border-t border-[#e6eee6] pt-5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h3 className="text-sm font-semibold text-[#1c3527]">Closure controls</h3>
              <span className="text-[10px] font-semibold uppercase tracking-wider text-[#66826b]">
                {selected.status==='closed'?'Closed · original work held':selected.closure?'Evidence reviewed · site acceptance pending':'Separate verification required'}
              </span>
            </div>
            {selected.corrective_request?.status==='approved'?
              <p className="text-xs text-[#526c59]">
                Corrective SOP task: {selected.corrective_work_status||'not started'}.
                A completed task with retained attachments and independent site inspection are required.
              </p>:<p className="text-xs text-[#718574]">An authorized corrective SOP must be completed first.</p>}
            {canReviewEvidence?<div className="space-y-2 rounded-xl border border-[#dce9de] bg-[#f8fbf8] p-4">
              <label htmlFor="closure-evidence-note" className="wm-label">Corrective evidence review</label>
              <textarea id="closure-evidence-note" rows={3} minLength={20} maxLength={1000}
                className="wm-input" value={evidenceNote} onChange={event=>setEvidenceNote(event.target.value)}
                placeholder="Record which submitted corrective evidence was inspected and what remains to verify on site."/>
              <button type="button" disabled={working||evidenceNote.trim().length<20}
                onClick={()=>void reviewCorrectiveEvidence()} className="min-h-11 rounded-xl bg-[#155a40] px-4 text-xs font-semibold text-white disabled:opacity-50">
                Record independent evidence review
              </button>
            </div>:null}
            {selected.closure?<div className="space-y-2 rounded-xl border border-[#dce9de] bg-[#f8fbf8] p-4">
              <p className="text-xs font-semibold text-[#28593c]">Evidence review recorded · {formatTime(selected.closure.evidence_reviewed_at)}</p>
              <p className="text-xs text-[#54705c]">Reviewer: {selected.closure.evidence_reviewed_by} · {selected.closure.evidence_snapshot.recorded_step_count} steps · {selected.closure.evidence_snapshot.received_evidence.length} received files</p>
              <p className="whitespace-pre-wrap text-xs leading-5 text-[#526c59]">{selected.closure.evidence_review_note}</p>
              {selected.closure.site_accepted_at?<div className="space-y-1 border-t border-[#d9e6da] pt-3">
                <p className="text-xs font-bold text-[#1d603f]">Site acceptance recorded · {formatTime(selected.closure.site_accepted_at)}</p>
                <p className="text-xs text-[#526c59]">Reference: {selected.closure.site_record_reference} · Signed by {selected.closure.site_accepted_by}</p>
                <p className="whitespace-pre-wrap text-xs text-[#526c59]">{selected.closure.site_acceptance_note}</p>
                <p className="text-xs font-semibold text-amber-800">The original task remains blocked. Closure is a recorded human decision, not automated physical verification.</p>
              </div>:null}
            </div>:null}
            {canAcceptSite?<div className="space-y-3 rounded-xl border border-[#bcd9c4] bg-white p-4">
              <p className="text-xs font-semibold text-[#28593c]">Independent site acceptance</p>
              <div>
                <label htmlFor="closure-site-reference" className="wm-label">External inspection record ID</label>
                <input id="closure-site-reference" className="wm-input" maxLength={128}
                  value={siteReference} onChange={event=>setSiteReference(event.target.value)}
                  placeholder="SITE-QA-INSPECTION-2071"/>
              </div>
              <div>
                <label htmlFor="closure-site-note" className="wm-label">Actual site inspection findings</label>
                <textarea id="closure-site-note" className="wm-input" rows={3} maxLength={1000}
                  value={siteNote} onChange={event=>setSiteNote(event.target.value)}
                  placeholder="Identify inspected location, corrective findings and remaining site controls."/>
              </div>
              <label className="flex items-start gap-2 text-xs leading-5 text-[#3f6349]">
                <input type="checkbox" className="mt-1" checked={siteAttested}
                  onChange={event=>setSiteAttested(event.target.checked)}/>
                I independently inspected the site and accept responsibility for the referenced inspection record. This is not an automated verification.
              </label>
              <button type="button" disabled={working||!siteAttested||siteReference.trim().length<8||siteNote.trim().length<30}
                onClick={()=>void acceptSite()} className="min-h-11 rounded-xl bg-[#155a40] px-4 text-xs font-semibold text-white disabled:opacity-50">
                Record site acceptance and close case
              </button>
            </div>:null}
          </div>
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
