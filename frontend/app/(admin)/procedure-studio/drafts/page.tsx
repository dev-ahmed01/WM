'use client';

import { useEffect, useState, type FormEvent } from 'react';
import Link from 'next/link';
import { ArrowRight, BookOpenText, CheckCircle2, Clock3, FilePlus2, FileText, RefreshCw, ShieldCheck } from 'lucide-react';
import { apiClient } from '@/lib/api-client';
import { useRequireRole } from '@/lib/auth';
import { LoadingState } from '@/components/shared/LoadingState';

type DraftRow = {id:string;title:string;source_filename:string;step_count:number;status:'draft'|'reviewed';revision:number;updated_at:string};

export default function ProcedureDraftsPage() {
  const { user, loading } = useRequireRole(['admin']);
  const [items,setItems] = useState<DraftRow[]>([]);
  const [fetching,setFetching] = useState(true);
  const [file,setFile] = useState<File|null>(null);
  const [title,setTitle] = useState('');
  const [error,setError] = useState('');
  const [saving,setSaving] = useState(false);

  const load = async () => {
    setError('');
    setFetching(true);
    try {
      const res=await apiClient<{items:DraftRow[]}>('/procedure/drafts');
      setItems(res.items || []);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not load procedure drafts.');
    } finally { setFetching(false); }
  };

  useEffect(() => {
    if (loading || !user) return;
    let active = true;
    void apiClient<{items:DraftRow[]}>('/procedure/drafts')
      .then(res => { if(active) setItems(res.items || []); })
      .catch(e => { if(active) setError(e instanceof Error ? e.message : 'Could not load drafts.'); })
      .finally(() => { if(active) setFetching(false); });
    return () => { active=false; };
  }, [loading,user?.sub,user?.department_id]);

  const submit = async (event:FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!file || title.trim().length<5) return;
    setError('');setSaving(true);
    try {
      const payload = new FormData();
      payload.append('file',file);
      payload.append('title',title.trim());
      const result = await apiClient<{id:string}>('/procedure/drafts/import',{method:'POST',body:payload});
      window.location.href='/procedure-studio/drafts/'+encodeURIComponent(result.id);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not prepare this document.');
      setSaving(false);
    }
  };
  if (loading) return <LoadingState label="Opening Procedure Studio" />;

  return <div className="wm-page max-w-[1350px] space-y-7 pb-12">
    <div className="flex flex-wrap items-center justify-between gap-4">
      <div>
        <p className="text-[10px] font-bold uppercase tracking-[.18em] text-emerald-700">PROCEDURE STUDIO / DRAFTS</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-[-.05em] text-[#182f22] sm:text-[2.5rem]">Build from a document</h1>
        <p className="mt-2 max-w-xl text-sm leading-6 text-[#64786a]">Import an existing SOP, review suggested steps, and build a source-backed procedure draft.</p>
      </div>
      <Link href="/procedure-studio" className="inline-flex min-h-11 items-center gap-2 rounded-xl border border-[#dce6de] px-4 text-xs font-semibold text-emerald-900">Procedure Studio <ArrowRight className="h-4 w-4" /></Link>
    </div>

    <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(22rem,.9fr)]">
      <section className="rounded-[1.6rem] border border-[#d7e3d9] bg-white p-6 sm:p-8">
        <span className="inline-flex h-12 w-12 items-center justify-center rounded-2xl bg-[#e9f5ed]"><FilePlus2 className="h-6 w-6 text-emerald-800" /></span>
        <h2 className="mt-5 text-xl font-semibold tracking-tight">Import company SOP</h2>
        <p className="mt-2 text-xs leading-6 text-[#748477]">PDF, Word, spreadsheets, slides and text documents. Files and extraction remain scoped to your department.</p>
        <form onSubmit={event=>void submit(event)} className="mt-6 space-y-5">
          <div><label htmlFor="procedure-document" className="wm-label">Procedure document</label>
            <input id="procedure-document" type="file" required accept=".pdf,.docx,.xlsx,.pptx,.txt,.md,.csv,.tsv,.json,.html,.htm,.rtf,.png,.jpg,.jpeg"
              onChange={e=>{const next=e.target.files?.[0]||null;setFile(next);if(next&&!title)setTitle(next.name.replace(/\.[^.]+$/,'').replace(/[_-]/g,' ').slice(0,180));}}
              className="block w-full max-w-full rounded-xl border border-dashed border-[#bcd4bf] bg-[#f8fbf8] p-4 text-xs text-[#54725d] file:mr-4 file:rounded-lg file:border-0 file:bg-[#dbf0e1] file:px-4 file:py-2 file:font-semibold file:text-[#145b3d]" />
          </div>
          <div><label htmlFor="procedure-title" className="wm-label">Procedure title</label>
            <input id="procedure-title" className="wm-input" required minLength={5} maxLength={180}
              value={title} onChange={e=>setTitle(e.target.value)} placeholder="Inbound receiving procedure" />
          </div>
          <button type="submit" disabled={saving || !file || title.trim().length<5}
            className="inline-flex min-h-12 w-full items-center justify-center gap-2 rounded-xl bg-[#16593f] px-5 text-sm font-semibold text-white disabled:opacity-50">
            {saving ? 'Preparing source-backed draft…' : 'Create editable procedure draft'} <ArrowRight className="h-4 w-4" />
          </button>
        </form>
        <div className="mt-6 flex items-start gap-3 rounded-xl bg-[#edf6ef] p-4">
          <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-emerald-700"/>
          <p className="text-xs leading-6 text-[#4f6e58]">Suggested steps are not published procedures. Every step must be checked against the source before review. Publishing remains restricted to the established validated workflow compiler.</p>
        </div>
      </section>
      <section className="overflow-hidden rounded-[1.6rem] border border-[#d9e4db] bg-white">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#eef2ed] p-6">
          <div><h2 className="text-lg font-semibold">Draft library</h2><p className="mt-1 text-xs text-[#748476]">Saved document conversions and revisions</p></div>
          <button type="button" onClick={()=>void load()} disabled={fetching} className="rounded-lg border border-[#e0e9e1] p-2"><RefreshCw className="h-4 w-4 text-emerald-800" /></button>
        </div>
        {error?<p role="alert" className="m-4 rounded-xl border border-red-200 bg-red-50 p-4 text-xs text-red-800">{error}</p>:null}
        {fetching?<div className="p-6"><LoadingState label="Reading your drafts"/></div>:
        !items.length?<div className="px-6 py-14 text-center"><BookOpenText className="mx-auto h-8 w-8 text-[#749c7b]"/><h3 className="mt-3 text-sm font-semibold">No drafts yet</h3><p className="mt-2 text-xs text-[#748477]">Import an SOP to begin the review process.</p></div>:
        <div className="divide-y divide-[#edf1ed]">{items.map(item=>
          <Link key={item.id} href={'/procedure-studio/drafts/'+encodeURIComponent(item.id)} className="group flex items-center gap-3 px-6 py-5 hover:bg-[#f6f9f5]">
            <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-[#eff5ef]">{item.status==='reviewed'?<CheckCircle2 className="h-5 w-5 text-emerald-700"/>:<FileText className="h-5 w-5 text-emerald-800"/>}</span>
            <div className="min-w-0 flex-1"><p className="truncate text-sm font-semibold">{item.title}</p>
              <p className="mt-1 truncate text-xs text-[#758678]">{item.step_count} suggested steps · {item.source_filename}</p>
            </div>
            <div className="shrink-0 text-right"><p className="text-[10px] font-bold uppercase tracking-wide text-[#507c5e]">{item.status}</p><p className="mt-1 text-[10px] text-[#859285]">Rev {item.revision}</p></div>
            <ArrowRight className="h-4 w-4 text-[#648875]"/>
          </Link>
        )}</div>}
      </section>
    </div>
  </div>;
}
