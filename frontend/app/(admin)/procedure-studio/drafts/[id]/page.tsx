'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { AlertTriangle, ArrowLeft, Check, CheckCircle2, FileText, Plus, Save, ShieldCheck, Trash2, GitBranchPlus, Play, LockKeyhole } from 'lucide-react';
import { apiClient } from '@/lib/api-client';
import { useRequireRole } from '@/lib/auth';
import { LoadingState } from '@/components/shared/LoadingState';

type DraftStep={id:string;instruction:string;source_line:number|null;reviewed:boolean;output_type?:'CONFIRMATION'|'TEXT_INPUT'|'NUMERIC_INPUT'|'DOCUMENT_UPLOAD';evidence_type?:'NONE'|'PHOTO_JPEG'|'DOCUMENT_PDF'};
type DraftDecision={question:string;options:{code:string;label:string;requires_supervisor_review?:boolean}[]};
type CompilePreview={valid:boolean;can_publish:boolean;validation_errors:string[];warnings:string[];states:number;steps:number;decisions:number;review_revision:number;workflow_code:string};
type Draft={id:string;title:string;source_filename:string;source_sha256:string;source_excerpt:string;
  steps:DraftStep[];warnings:string[];decision?:DraftDecision;published_version_id?:string|null;status:'draft'|'reviewed'|'published';revision:number;updated_at:string};

export default function ProcedureDraftEditor() {
  const { user, loading }=useRequireRole(['admin']);
  const params=useParams<{id:string}>();
  const [draft,setDraft]=useState<Draft|null>(null);
  const [steps,setSteps]=useState<DraftStep[]>([]);
  const [decision,setDecision]=useState<DraftDecision>({question:'',options:[]});
  const [preview,setPreview]=useState<CompilePreview|null>(null);
  const [confirmedPublish,setConfirmedPublish]=useState(false);
  const [title,setTitle]=useState('');
  const [pending,setPending]=useState(true);
  const [saving,setSaving]=useState(false);
  const [error,setError]=useState('');
  const [message,setMessage]=useState('');
  const [dirty,setDirty]=useState(false);
  const canReview=useMemo(()=>steps.length>0&&steps.every(step=>step.reviewed&&step.instruction.trim().length>=10),[steps]);

  const applyDraft=(fresh:Draft)=>{
    setDraft(fresh);setSteps(fresh.steps||[]);setTitle(fresh.title);
    setDecision(fresh.decision||{question:'',options:[]});setPreview(null);setConfirmedPublish(false);
    setDirty(false);
  };
  const load=async()=>{
    setError('');setPending(true);
    try {
      const current=await apiClient<Draft>('/procedure/drafts/'+encodeURIComponent(params.id));
      applyDraft(current);
    } catch(e) {setError(e instanceof Error?e.message:'This source-backed draft is unavailable.');}
    finally {setPending(false);}
  };
  useEffect(()=>{
    if(loading||!user||!params.id)return;
    let active=true;
    void apiClient<Draft>('/procedure/drafts/'+encodeURIComponent(params.id))
      .then(result=>{if(active)applyDraft(result);})
      .catch(e=>{if(active)setError(e instanceof Error?e.message:'This procedure draft was not found.');})
      .finally(()=>{if(active)setPending(false);});
    return()=>{active=false;};
  },[loading,user?.sub,params.id]);

  const change=(i:number,patch:Partial<DraftStep>)=>{
    setSteps(items=>items.map((step,j)=>j===i?{...step,...patch}:step));
    setDirty(true);setMessage('');setPreview(null);
  };
  const editDecision=(patch:Partial<DraftDecision>)=>{setDecision(v=>({...v,...patch}));setDirty(true);setMessage('');setPreview(null);};
  const published=draft?.status==='published';
  const save=async()=>{
    if(!draft||!steps.length||saving)return;
    setSaving(true);setError('');setMessage('');
    try{
      const fresh=await apiClient<Draft>('/procedure/drafts/'+encodeURIComponent(draft.id),{
        method:'PUT',body:JSON.stringify({expected_revision:draft.revision,title:title.trim(),steps,decision}),
      });
      applyDraft(fresh);setMessage('Changes saved. Review all steps before approving the draft.');
    }catch(e){setError(e instanceof Error?e.message:'This draft could not be saved.');}
    finally{setSaving(false);}
  };
  const approve=async()=>{
    if(!draft||dirty||!canReview||saving)return;
    setSaving(true);setError('');setMessage('');
    try{
      const fresh=await apiClient<Draft>('/procedure/drafts/'+encodeURIComponent(draft.id)+'/review',{
        method:'POST',body:JSON.stringify({expected_revision:draft.revision}),
      });
      applyDraft(fresh);setMessage('Draft reviewed. No workflow was published.');
    }catch(e){setError(e instanceof Error?e.message:'Review could not be recorded.');}
    finally{setSaving(false);}
  };

  const compile=async()=>{
    if(!draft||saving||dirty)return;
    setSaving(true);setError('');setMessage('');
    try{
      const report=await apiClient<CompilePreview>('/procedure/drafts/'+encodeURIComponent(draft.id)+'/compile-preview');
      setPreview(report);
      if(!report.valid)setError('The existing compiler rejected this procedure. Check its validation results below.');
    }catch(e){setError(e instanceof Error?e.message:'Could not validate this procedure.');}
    finally{setSaving(false);}
  };
  const publish=async()=>{
    if(!draft||!preview?.can_publish||!confirmedPublish||dirty||saving)return;
    setSaving(true);setError('');setMessage('');
    try{
      const result=await apiClient<{version_id:string;version_number:number}>(
        '/procedure/drafts/'+encodeURIComponent(draft.id)+'/publish',
        {method:'POST',body:JSON.stringify({expected_revision:draft.revision,approval:'PUBLISH_REVIEWED_SOP'})}
      );
      const fresh=await apiClient<Draft>('/procedure/drafts/'+encodeURIComponent(draft.id));
      applyDraft(fresh);
      setMessage('Published version '+result.version_number+'. The compiled SOP can now be linked to department work.');
    }catch(e){setError(e instanceof Error?e.message:'Publication failed. No successful publish was confirmed.');}
    finally{setSaving(false);}
  };

  if(loading||pending)return <LoadingState label="Loading procedure draft"/>;
  if(!draft)return <div className="wm-page"><Link href="/procedure-studio/drafts">Back to draft library</Link><p role="alert" className="mt-4 text-red-700">{error||'Draft not found'}</p></div>;

  return <div className="wm-page max-w-[1450px] space-y-6 pb-12">
    <Link href="/procedure-studio/drafts" className="inline-flex items-center gap-2 text-xs font-semibold text-emerald-800"><ArrowLeft className="h-4 w-4"/>Draft library</Link>
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div><p className="text-[10px] font-bold uppercase tracking-[.17em] text-emerald-700">SOURCE-REVIEWED PROCEDURE / REVISION {draft.revision}</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-[-.04em] text-[#1a3324] sm:text-[2.5rem]">Procedure editor</h1>
        <p className="mt-2 text-sm text-[#718176]">{draft.source_filename} · {draft.status==='published'?'Published workflow':draft.status==='reviewed'?'Reviewed draft':'Draft · requires human validation'}</p>
      </div>
      <div className="flex flex-wrap gap-2">
        <button type="button" disabled={saving||published||!dirty||!steps.length||title.trim().length<5}
          onClick={()=>void save()} className="inline-flex min-h-11 items-center gap-2 rounded-xl border border-[#bdd5c3] bg-white px-4 text-xs font-semibold text-[#22533a] disabled:opacity-50">
          <Save className="h-4 w-4"/>Save revision
        </button>
        <button type="button" disabled={saving||dirty||!canReview||draft.status!=='draft'}
          onClick={()=>void approve()} className="inline-flex min-h-11 items-center gap-2 rounded-xl bg-[#155a40] px-4 text-xs font-semibold text-white disabled:opacity-50">
          <CheckCircle2 className="h-4 w-4"/>Mark draft reviewed
        </button>
      </div>
    </div>

    <div className="flex flex-wrap items-center gap-3 rounded-xl border border-[#dbe8dd] bg-[#f3faf5] p-4">
      <ShieldCheck className="h-5 w-5 shrink-0 text-emerald-700"/>
      <div className="min-w-0 flex-1"><p className="text-sm font-semibold text-[#245239]">Source-linked, not automatically approved</p>
        <p className="mt-1 text-xs leading-5 text-[#64796a]">The extracted candidates are suggestions. Check every action against the source document, then explicitly review the final draft. Published execution is a separate governed workflow.</p>
      </div>
    </div>
    {error?<p role="alert" className="rounded-xl border border-red-200 bg-red-50 p-4 text-xs text-red-800">{error}</p>:null}
    {message?<p role="status" className="rounded-xl border border-[#cce4d0] bg-[#edf8ef] p-4 text-xs font-semibold text-[#286344]">{message}</p>:null}
    <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1.3fr)_minmax(20rem,.85fr)]">
      <section className="min-w-0 rounded-[1.5rem] border border-[#d7e3d8] bg-white p-5 sm:p-7">
        <div className="flex items-center justify-between gap-2">
          <div><h2 className="text-xl font-semibold">Editable work steps</h2><p className="mt-1 text-xs text-[#708075]">{steps.filter(s=>s.reviewed).length} of {steps.length} reviewed · changes require saving</p></div>
          <span className="rounded-lg bg-[#e9f3eb] px-3 py-1.5 text-xs font-bold text-[#266046]">{draft.status}</span>
        </div>
        <div className="mt-6"><label htmlFor="draft-title" className="wm-label">Procedure title</label>
          <input id="draft-title" value={title} maxLength={180} minLength={5} className="wm-input"
            onChange={e=>{setTitle(e.target.value);setDirty(true);setMessage('');setPreview(null);}} disabled={published}/>
        </div>
        <div className="mt-6 space-y-3">
          {steps.map((step,i)=><div key={step.id} className="rounded-[1.25rem] border border-[#dce8de] bg-[#fbfdfb] p-4 sm:p-5">
            <div className="flex items-center justify-between gap-3">
              <p className="text-[10px] font-bold uppercase tracking-[.13em] text-emerald-800">STEP {i+1}{step.source_line?' · SOURCE LINE '+step.source_line:' · MANUALLY ADDED'}</p>
              <button type="button" aria-label={'Remove step '+(i+1)} onClick={()=>{
                if(steps.length===1)return;
                setSteps(prev=>prev.filter(s=>s.id!==step.id));setDirty(true);setMessage('');
              }} disabled={steps.length===1||published} className="rounded-lg p-2 text-[#8b9990] hover:bg-red-50 hover:text-red-700 disabled:opacity-40"><Trash2 className="h-4 w-4"/></button>
            </div>
            <textarea aria-label={'Step '+(i+1)+' instruction'} className="wm-input mt-3 min-h-24" maxLength={700} value={step.instruction}
              onChange={e=>change(i,{instruction:e.target.value,reviewed:false})} disabled={published}/>
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              <div><label htmlFor={'output-'+step.id} className="wm-label">Worker must provide</label>
                <select id={'output-'+step.id} className="wm-input" disabled={published}
                  value={step.output_type||'CONFIRMATION'}
                  onChange={e=>change(i,{output_type:e.target.value as DraftStep['output_type'],reviewed:false})}>
                  <option value="CONFIRMATION">Checkpoint confirmation</option>
                  <option value="TEXT_INPUT">Written observation</option>
                  <option value="NUMERIC_INPUT">Numeric reading</option>
                  <option value="DOCUMENT_UPLOAD">Evidence file upload</option>
                </select>
              </div>
              <div><label htmlFor={'evidence-'+step.id} className="wm-label">Mandatory supporting evidence</label>
                <select id={'evidence-'+step.id} className="wm-input" disabled={published}
                  value={step.evidence_type||'NONE'}
                  onChange={e=>change(i,{evidence_type:e.target.value as DraftStep['evidence_type'],reviewed:false})}>
                  <option value="NONE">No attachment</option>
                  <option value="PHOTO_JPEG">JPEG photograph</option>
                  <option value="DOCUMENT_PDF">PDF document</option>
                </select>
              </div>
            </div>
            <label className="mt-3 flex cursor-pointer items-center gap-2 text-xs font-semibold text-[#506c59]">
              <input type="checkbox" checked={step.reviewed} onChange={e=>change(i,{reviewed:e.target.checked})} disabled={published}
                className="h-4 w-4 accent-emerald-700"/>Checked against original source
            </label>
          </div>)}
          {!steps.length?<div className="rounded-xl border border-dashed border-[#d9e4db] p-8 text-center text-sm text-[#718176]">No numbered steps extracted. Add steps from the original SOP.</div>:null}
        </div>
        <button type="button" disabled={steps.length>=50||published} onClick={()=>{
          setSteps(prev=>[...prev,{id:'step_'+crypto.randomUUID().replaceAll('-','').slice(0,16),
            instruction:'',source_line:null,reviewed:false,output_type:'CONFIRMATION',evidence_type:'NONE'}]);setDirty(true);setMessage('');
        }} className="mt-5 inline-flex min-h-11 items-center gap-2 rounded-xl border border-dashed border-[#97c2a0] px-5 text-xs font-semibold text-emerald-800 disabled:opacity-50"><Plus className="h-4 w-4"/>Add operational step</button>
        <div className="mt-7 border-t border-[#e7efe7] pt-6">
          <div className="flex items-center gap-2"><GitBranchPlus className="h-4 w-4 text-emerald-700"/><h3 className="text-base font-semibold">Final outcome</h3></div>
          <p className="mt-2 text-xs leading-6 text-[#778678]">Record an observed result after the final checkpoint. This branches the procedure record; it does not authorize safety release or supervisor approval.</p>
          <label className="mt-3 flex items-center gap-3 text-xs font-semibold text-[#456950]">
            <input type="checkbox" checked={decision.options.length>0} disabled={published}
              className="h-4 w-4 accent-emerald-700"
              onChange={e=>editDecision(e.target.checked?{
                question:'What outcome was observed at the end of this procedure?',
                options:[{code:'OPT_ACCEPT',label:'Expected outcome recorded',requires_supervisor_review:false},{code:'OPT_EXCEPTION',label:'An exception was documented',requires_supervisor_review:true}]
              }:{question:'',options:[]})}/>
            Require final outcome selection
          </label>
          {decision.options.length>0?<div className="mt-4 space-y-3">
            <div><label htmlFor="decision-question" className="wm-label">Decision prompt</label>
              <input id="decision-question" className="wm-input" maxLength={220}
                disabled={published} value={decision.question}
                onChange={e=>editDecision({question:e.target.value})}/>
            </div>
            {decision.options.map((option,i)=><div key={option.code} className="flex items-center gap-3">
              <span className="w-12 shrink-0 text-[10px] font-bold text-[#65866d]">{i+1<10?'0'+(i+1):i+1}</span>
              <div className="min-w-0 flex-1 space-y-2">
                <input aria-label={'Outcome '+(i+1)+' label'} disabled={published} className="wm-input" maxLength={120}
                  value={option.label} onChange={e=>editDecision({options:decision.options.map((opt,j)=>j===i?{...opt,label:e.target.value}:opt)})}/>
                <label className="flex items-center gap-2 text-[11px] font-semibold text-[#7c674c]">
                  <input type="checkbox" disabled={published} checked={Boolean(option.requires_supervisor_review)}
                    onChange={e=>editDecision({options:decision.options.map((opt,j)=>j===i?{...opt,requires_supervisor_review:e.target.checked}:opt)})}
                    className="h-4 w-4 accent-amber-700"/>
                  Hold for supervisor review (cannot complete automatically)
                </label>
              </div>
            </div>)}
          </div>:null}
        </div>
        <p className="mt-4 text-[11px] leading-5 text-[#78867b]">Maximum 50 steps per draft. Each step must have at least 10 characters before saving. Source line numbers are references to extracted text, not proof of real-world execution.</p>
      </section>
      <aside className="space-y-4">
        <div className="overflow-hidden rounded-[1.5rem] border border-[#d9e3dc] bg-white">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#e8eee9] p-5"><div className="flex items-center gap-2"><FileText className="h-5 w-5 text-emerald-700"/><h2 className="text-base font-semibold">Original source excerpt</h2></div><a href={"/api/backend/procedure/drafts/"+encodeURIComponent(draft.id)+"/source"} download className="inline-flex min-h-9 items-center rounded-lg border border-[#d6e5d9] px-3 text-[11px] font-bold text-emerald-800 hover:bg-[#f3f8f3]">Download original</a></div>
          <div className="max-h-[600px] overflow-y-auto px-5 py-4"><pre className="whitespace-pre-wrap break-words font-mono text-[11px] leading-7 text-[#53665a]">{draft.source_excerpt}</pre></div>
          <p className="border-t border-[#edf1eb] px-5 py-3 text-[11px] text-[#859184]">Shows the first 8,000 extracted characters. For long documents, verify the original file beyond this excerpt.</p>
        </div>
        {draft.warnings.length?<div className="rounded-[1.5rem] border border-[#efdfc6] bg-[#fffbf4] p-5">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-[#886038]"><AlertTriangle className="h-4 w-4"/>Extraction notes</h2>
          <div className="mt-3 space-y-2">{draft.warnings.map((warning,i)=><p key={i} className="text-xs leading-6 text-[#806b4b]">{warning}</p>)}</div>
        </div>:null}
        <div className="rounded-[1.5rem] border border-[#dbe7de] bg-white p-5">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-[#244c36]"><Play className="h-4 w-4"/>Compile and publish</h2>
          <p className="mt-2 text-xs leading-6 text-[#6e8272]">The real OWD compiler checks the authored plan before anything is published. Only an unchanged reviewed revision can be released.</p>
          <button type="button" onClick={()=>void compile()} disabled={saving||dirty||!canReview||published}
            className="mt-4 inline-flex min-h-10 items-center gap-2 rounded-xl border border-[#bcd8c5] px-4 text-xs font-semibold text-emerald-900 disabled:opacity-50">
            Validate compiled workflow
          </button>
          {preview?<div className="mt-4 rounded-xl bg-[#f2f8f3] p-4">
            <p className="text-xs font-bold text-[#28563a]">{preview.valid?'Compiler validation passed':'Compiler validation failed'}</p>
            <p className="mt-2 text-[11px] text-[#617e69]">{preview.states} states · {preview.steps} worker steps · {preview.decisions} decisions</p>
            {preview.validation_errors.map((e,i)=><p key={i} className="mt-2 text-xs text-red-700">{e}</p>)}
            {preview.warnings.map((e,i)=><p key={i} className="mt-2 text-xs text-amber-800">{e}</p>)}
            {preview.can_publish&&!published?<div className="mt-4 space-y-3 border-t border-[#dae8dd] pt-3">
              <label className="flex items-start gap-2 text-xs leading-5 text-[#446f50]">
                <input type="checkbox" checked={confirmedPublish}
                  onChange={e=>setConfirmedPublish(e.target.checked)} className="mt-1 h-4 w-4 accent-emerald-700"/>
                I confirm this reviewed workflow is approved for my department's controlled use.
              </label>
              <button type="button" disabled={!confirmedPublish||saving} onClick={()=>void publish()}
                className="inline-flex min-h-11 w-full items-center justify-center gap-2 rounded-xl bg-[#155a40] px-4 text-xs font-bold text-white disabled:opacity-50">
                <LockKeyhole className="h-4 w-4"/>Publish reviewed workflow
              </button>
            </div>:null}
          </div>:null}
          {published?<p className="mt-4 break-all rounded-xl bg-[#ecf7ed] px-4 py-3 text-xs font-semibold text-[#285c3a]">Published version: {draft.published_version_id}</p>:null}
        </div>
        <div className="rounded-[1.5rem] border border-[#dce7df] bg-[#eff7f1] p-5">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-[#244b35]"><Check className="h-4 w-4"/>Next publishing gate</h2>
          <p className="mt-2 text-xs leading-6 text-[#677d6a]">Reviewing a draft does not make it executable. The approved OWD compiler and its separate validation process remain the only publishing authority.</p>
          <Link href="/knowledge-studio" className="mt-4 inline-flex items-center gap-2 text-xs font-bold text-emerald-800">Published workflow library <ArrowLeft className="h-4 w-4 rotate-180"/></Link>
        </div>
      </aside>
    </div>
  </div>;
}
