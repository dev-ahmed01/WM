'use client';

import { useEffect, useState } from 'react';
import { AlertTriangle, ClipboardCheck, RefreshCw, ShieldAlert } from 'lucide-react';
import { apiClient } from '@/lib/api-client';

type Alert={
  code:string;severity:'critical'|'high';count:number;
  label:string;source_id:string;
};
type Action={
  id:string;source_id:string;issue_code:string;
  action:string;actor_id:string;created_at:string;
};
type Status={
  decision:'NO_GO';operational_status:string;window_hours:number;
  counts:{
    sources:number;active_sources:number;inbound_24h:number;
    outbound_acks_24h:number;dead_outbound:number;open_alerts:number;
  };
  alerts:Alert[];latest_actions:Action[];
  field_verification:string;
};
const local=(t:string)=>new Date(t).toLocaleString('en-IN',{
  timeZone:'Asia/Kolkata',day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit',
});

export function IntegrationOperationsPanel(){
  const [status,setStatus]=useState<Status|null>(null);
  const [loading,setLoading]=useState(true);
  const [saving,setSaving]=useState(false);
  const [error,setError]=useState('');
  const [message,setMessage]=useState('');
  const [focus,setFocus]=useState<Alert|null>(null);
  const [action,setAction]=useState<'acknowledged'|'remediation_logged'>('acknowledged');
  const [note,setNote]=useState('');

  async function refresh(){
    setLoading(true);
    try{
      const result=await apiClient<Status>('/work/integrations/operations/readiness');
      setStatus(result);setError('');
    }catch(caught){setError(caught instanceof Error?caught.message:'Operational health is unavailable.');}
    finally{setLoading(false);}
  }
  useEffect(()=>{
    let alive=true;
    void apiClient<Status>('/work/integrations/operations/readiness')
      .then(data=>{if(alive){setStatus(data);setLoading(false);}})
      .catch(()=>{if(alive){setError('Operational health is unavailable.');setLoading(false);}});
    return()=>{alive=false;};
  },[]);
  async function record(){
    if(!focus||saving||note.trim().length<16)return;
    setSaving(true);setError('');setMessage('');
    try{
      await apiClient('/work/integrations/operations/actions',{
        method:'POST',
        body:JSON.stringify({
          source_id:focus.source_id,issue_code:focus.code,
          action,justification:note.trim(),
        }),
      });
      setMessage('Operator response recorded. Live health alerts remain until the issue is resolved.');
      setFocus(null);setNote('');
      await refresh();
    }catch(caught){setError(caught instanceof Error?caught.message:'Could not record operational response.');}
    finally{setSaving(false);}
  }

  return <section aria-label="Integration operational readiness"
    className="rounded-[1.5rem] border border-[#dce7dc] bg-white p-5 sm:p-6">
    <header className="flex flex-wrap items-start justify-between gap-3">
      <div><p className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-widest text-[#477852]">
        <ShieldAlert className="h-4 w-4"/> PILOT OPERATIONS</p>
        <h2 className="mt-2 text-lg font-semibold tracking-tight text-[#233f2b]">Integration readiness</h2></div>
      <button type="button" onClick={()=>void refresh()} disabled={loading}
        aria-label="Refresh integration health" className="rounded-lg border border-[#d9e6db] p-2 disabled:opacity-50">
        <RefreshCw className="h-4 w-4"/>
      </button>
    </header>
    {error?<p role="alert" className="mt-3 text-xs text-red-800">{error}</p>:null}
    {message?<p role="status" className="mt-3 text-xs font-medium text-[#28764c]">{message}</p>:null}
    <div className="mt-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
      {[
        ['Release decision',status?.decision||'—'],
        ['Active sources',status?.counts.active_sources ?? '—'],
        ['Alerts',status?.counts.open_alerts ?? '—'],
        ['Partner receipts · 24h',status?.counts.outbound_acks_24h ?? '—'],
      ].map(([label,value])=><div key={String(label)} className="rounded-xl border border-[#e2eae3] bg-[#f9fbf8] px-4 py-4">
        <p className="text-[11px] text-[#788678]">{label}</p>
        <p className={'mt-2 text-2xl font-semibold tabular-nums tracking-tight '+(label==='Release decision'?'text-[#986028]':'text-[#204830]')}>{value}</p>
      </div>)}
    </div>
    <div className="mt-5 grid gap-5 lg:grid-cols-[minmax(0,1.25fr)_minmax(230px,.75fr)]">
      <div className="min-w-0">
        <div className="mb-2 flex justify-between gap-3">
          <h3 className="text-xs font-semibold text-[#2a4f35]">Active findings</h3>
          <span className="text-[11px] text-[#758978]">Last 24 hours / backlog</span>
        </div>
        {status?.alerts.length?<div className="divide-y divide-[#edf2ed] overflow-hidden rounded-xl border border-[#e1e9e2]">
          {status.alerts.map((item,i)=><button key={item.source_id+item.code+i} type="button"
            onClick={()=>{setFocus(item);setNote('');setAction('acknowledged');}}
            aria-pressed={focus?.source_id===item.source_id&&focus.code===item.code}
            className="flex w-full items-center justify-between gap-3 p-3 text-left hover:bg-[#f6faf7]">
            <span className="min-w-0">
              <span className="block truncate text-xs font-semibold text-[#31593c]">{item.label}</span>
              <span className="mt-1 block text-[11px] text-[#778b7a]">{item.source_id} · {item.severity}</span>
            </span>
            <span className="shrink-0 rounded-lg bg-[#f7f0e7] px-3 py-1 text-xs font-bold text-[#875e34]">{item.count}</span>
          </button>)}
        </div>:<div className="flex min-h-28 items-center gap-3 rounded-xl border border-[#e4ebe3] p-4">
          {status?.counts.sources?<ClipboardCheck className="h-5 w-5 text-[#45794e]"/>:<AlertTriangle className="h-5 w-5 text-[#a4753e]"/>}
          <p className="text-xs text-[#687c6c]">{loading?'Checking operational data…':!status?'Unable to establish readiness.':status.counts.sources===0?'No signed connectors configured.':'No current technical alerts. Independent site release review is still required.'}</p>
        </div>}
        {focus?<div className="mt-3 space-y-3 rounded-xl border border-[#dbe8de] bg-[#f7faf7] p-4">
          <h4 className="text-xs font-semibold text-[#2a5839]">Record operator response · {focus.source_id}</h4>
          <select aria-label="Operational response" className="wm-input" value={action}
            onChange={e=>setAction(e.target.value as typeof action)}>
            <option value="acknowledged">Acknowledged</option>
            <option value="remediation_logged">Remediation logged</option>
          </select>
          <label htmlFor="operations-justification" className="wm-label">Operator note</label>
          <textarea id="operations-justification" className="wm-input" rows={2}
            value={note} onChange={e=>setNote(e.target.value)}
            minLength={16} maxLength={1000} placeholder="What was checked, who owns the fix and what happens next?"/>
          <div className="flex flex-wrap gap-2">
            <button type="button" onClick={()=>void record()} disabled={saving||note.trim().length<16}
              className="min-h-10 rounded-lg bg-[#155a40] px-4 text-xs font-semibold text-white disabled:opacity-50">Record response</button>
            <button type="button" onClick={()=>setFocus(null)} className="min-h-10 rounded-lg px-3 text-xs text-[#6b826e]">Cancel</button>
          </div>
        </div>:null}
      </div>
      <div>
        <h3 className="mb-2 text-xs font-semibold text-[#2a4f35]">Recent operator actions</h3>
        <div className="max-h-72 divide-y divide-[#edf2ed] overflow-y-auto rounded-xl border border-[#e1e9e2]">
          {status?.latest_actions.length?status.latest_actions.slice(0,8).map(item=>
            <div key={item.id} className="p-3">
              <p className="truncate text-xs font-semibold text-[#2d5a3e]">{item.issue_code.replaceAll('_',' ')}</p>
              <p className="mt-1 text-[11px] text-[#78897c]">{item.source_id} · {item.action}</p>
              <p className="mt-1 text-[10px] text-[#8a988c]">{local(item.created_at)}</p>
            </div>):<p className="p-4 text-xs text-[#708774]">No operator responses recorded.</p>}
        </div>
      </div>
    </div>
    <p className="mt-4 text-[11px] text-[#788778]">These are database-backed technical checks, not proof of a live warehouse pilot. Release requires independently reviewed field evidence.</p>
  </section>;
}
