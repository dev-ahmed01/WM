'use client';

import { useEffect, useState } from 'react';
import { ArrowDownRight, LockKeyhole, RefreshCw, ShieldAlert } from 'lucide-react';
import { apiClient } from '@/lib/api-client';

type Source={
  id:string;source_system:'sap'|'oracle'|'odoo'|'custom_wms';
  status:'active'|'disabled';created_by:string;deliveries:number;failures:number;
  last_delivery_at:string|null;
};
type Delivery={
  id:string;status:'staged'|'replayed'|'conflict'|'invalid';reason_code:string;
  content_sha256:string;intake_id:string|null;received_at:string;
};
const fmt=(t:string)=>new Date(t).toLocaleString('en-IN',{
  timeZone:'Asia/Kolkata',day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit',
});
export function IntegrationSourcesPanel(){
  const [sources,setSources]=useState<Source[]>([]);
  const [selected,setSelected]=useState('');
  const [deliveries,setDeliveries]=useState<Delivery[]>([]);
  const [busy,setBusy]=useState(false);
  const [message,setMessage]=useState('');
  const [error,setError]=useState('');
  const [sourceId,setSourceId]=useState('');
  const [system,setSystem]=useState<Source['source_system']>('custom_wms');

  async function load(){
    try{
      const result=await apiClient<{items:Source[]}>('/work/integrations/sources');
      setSources(result.items||[]);
      setError('');
    }catch(caught){setError(caught instanceof Error?caught.message:'Connector health is unavailable.');}
  }
  useEffect(()=>{
    let valid=true;
    void apiClient<{items:Source[]}>('/work/integrations/sources')
      .then(r=>{if(valid)setSources(r.items||[]);})
      .catch(()=>{if(valid)setError('Connector health is unavailable.');});
    return()=>{valid=false;};
  },[]);

  useEffect(()=>{
    if(!selected){setDeliveries([]);return;}
    let valid=true;
    void apiClient<{items:Delivery[]}>('/work/integrations/sources/'+encodeURIComponent(selected)+'/deliveries')
      .then(r=>{if(valid)setDeliveries(r.items||[]);})
      .catch(()=>{if(valid)setError('Delivery history is unavailable.');});
    return()=>{valid=false;};
  },[selected]);

  async function create(){
    if(busy||sourceId.trim().length<6)return;
    setBusy(true);setError('');setMessage('');
    try{
      await apiClient('/work/integrations/sources',{
        method:'POST',body:JSON.stringify({id:sourceId.trim(),source_system:system}),
      });
      setMessage('Source registered. Signed deliveries will enter the independent review queue.');
      setSelected(sourceId.trim());setSourceId('');
      await load();
    }catch(caught){setError(caught instanceof Error?caught.message:'Source registration failed.');}
    finally{setBusy(false);}
  }
  async function control(id:string,enabled:boolean){
    if(busy)return;
    setBusy(true);setError('');setMessage('');
    try{
      await apiClient('/work/integrations/sources/'+encodeURIComponent(id)+'/control',{
        method:'POST',body:JSON.stringify({enabled}),
      });
      setMessage(enabled?'Signed source re-enabled.':'Signed source disabled; further deliveries will be denied.');
      await load();
    }catch(caught){setError(caught instanceof Error?caught.message:'Source control did not save.');}
    finally{setBusy(false);}
  }
  const focused=sources.find(x=>x.id===selected);
  return <section className="rounded-[1.5rem] border border-[#dae6dd] bg-white p-5 sm:p-6" aria-label="Signed connector health">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div><h2 className="flex items-center gap-2 text-sm font-semibold text-[#21402b]">
        <LockKeyhole className="h-4 w-4 text-[#1d7048]"/> Signed connectors</h2>
        <p className="mt-1 text-xs text-[#718174]">HMAC-verified ingress · delivery health · admin controls</p>
      </div>
      <button type="button" onClick={()=>void load()} aria-label="Refresh signed connectors"
        className="rounded-lg border border-[#d8e5da] p-2"><RefreshCw className="h-4 w-4"/></button>
    </div>
    {error?<p role="alert" className="mt-3 text-xs text-red-800">{error}</p>:null}
    {message?<p role="status" className="mt-3 text-xs text-[#26704b]">{message}</p>:null}
    <div className="mt-5 grid gap-5 xl:grid-cols-[minmax(0,.9fr)_minmax(0,1.2fr)]">
      <div className="space-y-3">
        <p className="text-[10px] font-bold uppercase tracking-wider text-[#61836a]">Preconfigured signing key ID</p>
        <div className="grid gap-2 sm:grid-cols-[1fr_auto]">
          <input aria-label="Connector signing key ID" className="wm-input" minLength={6} maxLength={64}
            value={sourceId} onChange={e=>setSourceId(e.target.value)}
            placeholder="registered-warehouse-source"/>
          <select aria-label="Connector source type" className="wm-input" value={system}
            onChange={e=>setSystem(e.target.value as Source['source_system'])}>
            <option value="custom_wms">Custom WMS</option><option value="sap">SAP format</option>
            <option value="oracle">Oracle format</option><option value="odoo">Odoo format</option>
          </select>
        </div>
        <button type="button" disabled={busy||sourceId.length<6} onClick={()=>void create()}
          className="min-h-11 rounded-xl border border-[#accbb3] px-4 text-xs font-semibold text-[#265d3b] disabled:opacity-50">
          Register preconfigured source
        </button>
        <p className="text-[11px] leading-5 text-[#718275]">Keys are provisioned in server secrets and are never displayed or submitted here.</p>
        <div className="divide-y divide-[#eef2ee] overflow-hidden rounded-xl border border-[#e0e8e1]">
          {sources.map(s=><button key={s.id} type="button" onClick={()=>setSelected(s.id)}
            aria-pressed={s.id===selected} className={'flex w-full items-center justify-between gap-2 p-3 text-left hover:bg-[#f6faf6] '+(s.id===selected?'bg-[#eff7ef]':'')}>
            <div><p className="text-xs font-semibold text-[#284c34]">{s.id}</p>
              <p className="mt-1 text-[11px] text-[#758577]">{s.source_system} · {s.status}</p></div>
            <span className="text-[11px] font-bold text-[#447451]">{s.failures} issues</span>
          </button>)}
          {!sources.length?<p className="p-3 text-xs text-[#718275]">No signed sources registered.</p>:null}
        </div>
      </div>
      <div className="space-y-3">
        {focused?<><div className="flex flex-wrap items-center justify-between gap-3">
          <div><p className="text-sm font-semibold text-[#23412c]">{focused.id}</p>
            <p className="mt-1 text-xs text-[#67816a]">{focused.deliveries} deliveries · {focused.failures} rejected or conflicting</p></div>
          <button type="button" disabled={busy} onClick={()=>void control(focused.id,focused.status!=='active')}
            className="min-h-10 rounded-lg border border-[#bcd3c0] px-3 text-xs font-semibold text-[#356546] disabled:opacity-50">
            {focused.status==='active'?'Disable source':'Enable source'}
          </button>
        </div>
        <p className="text-xs text-[#718274]">Last delivery: {focused.last_delivery_at?fmt(focused.last_delivery_at):'None'}</p>
        <div className="max-h-[210px] overflow-y-auto rounded-xl border border-[#e1e9e2]">
          {deliveries.map(x=><div key={x.id} className="flex justify-between gap-2 border-b border-[#eaf0ea] p-3 text-xs last:border-0">
            <div><p className="font-semibold text-[#335b41]">{x.status}</p>
              <p className="mt-1 text-[#748778]">{x.reason_code==='none'?'Received':x.reason_code}</p></div>
            <span className="text-[#829084]">{fmt(x.received_at)}</span></div>)}
          {!deliveries.length?<p className="p-4 text-xs text-[#718275]">No signed deliveries yet.</p>:null}
        </div></>:<div className="flex min-h-40 flex-col items-center justify-center gap-2 text-center text-[#748476]">
          <ShieldAlert className="h-6 w-6"/><p className="text-xs">Select a registered source to inspect delivery health.</p>
        </div>}
      </div>
    </div>
  </section>;
}
