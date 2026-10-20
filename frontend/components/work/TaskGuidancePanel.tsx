'use client';

import { useState } from 'react';
import { BookOpenText, ChevronDown, MessageSquareText, Send, ShieldAlert } from 'lucide-react';
import { apiClient } from '@/lib/api-client';

type Answer={
  answer:string;status:string;read_only:boolean;requires_supervisor:boolean;
  reference_grounded?:boolean;
  workflow_version_id:string|null;
  citations:Array<{source_type:'published_sop'|'approved_reference';
    workflow_version_id?:string;state_id?:string;step_id?:string;
    document_id?:string;document_title?:string;chunk_id?:string;excerpt:string}>;
};
type Intent='current_step'|'evidence'|'exception'|'ask';
type Props={workId:string;status:string;workflowVersionId:string|null;stepId:string|null};

const actions:{intent:Intent;label:string}[]=[
  {intent:'current_step',label:'Explain this step'},
  {intent:'evidence',label:'What evidence is required?'},
  {intent:'exception',label:'Something is wrong'},
];

export function TaskGuidancePanel({workId,status,workflowVersionId,stepId}:Props){
  const [open,setOpen]=useState(false);
  const [question,setQuestion]=useState('');
  const [result,setResult]=useState<Answer|null>(null);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');

  async function ask(intent:Intent){
    if(busy || (intent==='ask'&&question.trim().length<4))return;
    setBusy(true);setError('');setResult(null);
    try{
      const response=await apiClient<Answer>(
        '/work/guidance/'+encodeURIComponent(workId),{
        method:'POST',
        body:JSON.stringify({intent,question:intent==='ask'?question.trim():''}),
      });
      if(response.workflow_version_id!==workflowVersionId){
        throw new Error('The published procedure has changed. Refresh this task before relying on guidance.');
      }
      setResult(response);
    }catch(caught){setError(caught instanceof Error?caught.message:'No verified guidance could be retrieved.');}
    finally{setBusy(false);}
  }

  return <section className="overflow-hidden rounded-[1.4rem] border border-[#d5e5d7] bg-[#f6faf6]">
    <button type="button" aria-expanded={open} aria-controls={'task-guidance-'+workId}
      className="flex w-full items-center justify-between gap-3 p-4 text-left sm:p-5"
      onClick={()=>setOpen(prev=>!prev)}>
      <div className="flex items-center gap-3">
        <span className="grid h-10 w-10 place-items-center rounded-xl bg-[#e5f2e7] text-emerald-900">
          <MessageSquareText className="h-5 w-5"/>
        </span>
        <div>
          <h3 className="text-sm font-semibold text-[#245036]">Ask about this task</h3>
          <p className="mt-0.5 text-[11px] text-[#657d6a]">Published SOP context · verified sources only</p>
        </div>
      </div>
      <ChevronDown className={'h-4 w-4 text-[#61816b] transition-transform '+(open?'rotate-180':'')}/>
    </button>
    {open?<div id={'task-guidance-'+workId} className="space-y-4 border-t border-[#e0ebdf] p-4 sm:p-5">
      <div className="flex flex-wrap gap-2">
        {actions.map(action=><button type="button" key={action.intent} disabled={busy}
          onClick={()=>void ask(action.intent)}
          className="min-h-9 rounded-xl border border-[#cce0d0] bg-white px-3 text-[11px] font-semibold text-[#305b3b] disabled:opacity-50">{action.label}</button>)}
      </div>
      <form className="flex items-end gap-2" onSubmit={e=>{e.preventDefault();void ask('ask');}}>
        <div className="min-w-0 flex-1">
          <label htmlFor={'task-question-'+workId} className="wm-label">Question about company guidance</label>
          <textarea id={'task-question-'+workId} maxLength={500} rows={2}
            className="wm-input mt-1 min-h-16 bg-white"
            value={question} onChange={e=>setQuestion(e.target.value)}
            placeholder="How should damaged cartons be documented?"/>
        </div>
        <button type="submit" aria-label="Ask task question" disabled={busy||question.trim().length<4}
          className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-[#155a40] text-white disabled:opacity-50"><Send className="h-4 w-4"/></button>
      </form>
      {busy?<p role="status" className="text-xs text-[#68806b]">Checking the current procedure and approved references…</p>:null}
      {error?<p role="alert" className="rounded-xl bg-red-50 p-3 text-xs text-red-800">{error}</p>:null}
      {result?<article aria-live="polite" className="rounded-xl border border-[#d3e5d6] bg-white p-4">
        <div className="flex items-center gap-2">
          {result.requires_supervisor?<ShieldAlert className="h-4 w-4 text-amber-700"/>:<BookOpenText className="h-4 w-4 text-emerald-700"/>}
          <p className="text-[10px] font-bold uppercase tracking-[.12em] text-[#52775d]">{result.requires_supervisor?'Supervisor guidance required':'Source-linked guidance'}</p>
        </div>
        <p className="mt-3 whitespace-pre-wrap break-words text-sm leading-6 text-[#304a36]">{result.answer}</p>
        {result.citations.length?<div className="mt-4 space-y-2 border-t border-[#edf2ec] pt-3">
          <p className="text-[10px] font-bold uppercase tracking-wider text-[#67826b]">Verified source</p>
          {result.citations.map((citation,i)=><div key={citation.chunk_id||citation.step_id||i}
            className="rounded-lg bg-[#f5f9f5] px-3 py-2">
            <p className="text-[11px] font-semibold text-[#316142]">{citation.source_type==='published_sop'
              ? 'Current SOP · state '+(citation.state_id||'') : citation.document_title}</p>
            <p className="mt-1 whitespace-pre-wrap break-words text-xs leading-5 text-[#67806d]">{citation.excerpt}</p>
          </div>)}
        </div>:null}
        <p className="mt-3 text-[11px] leading-5 text-[#788c79]">
          Read-only guidance. No step, evidence requirement, decision or approval was recorded.
        </p>
      </article>:null}
      <p className="text-[11px] leading-5 text-[#7b8d7d]">For uncertainty or unsafe conditions, stop and report through the actual work controls. Answers cannot override SOP gates. Hindi/English voice confirmation is a separate release.</p>
    </div>:null}
  </section>;
}
