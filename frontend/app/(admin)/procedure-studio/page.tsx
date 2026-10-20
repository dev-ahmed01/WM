'use client';
import Link from 'next/link';
import { ArrowRight, BookOpenText, ClipboardCheck, FileSearch2, FilePlus2, GitBranchPlus, LockKeyhole, ShieldCheck } from 'lucide-react';
import { useRequireRole } from '@/lib/auth';
import { LoadingState } from '@/components/shared/LoadingState';

export default function ProcedureStudioHome() {
  const { loading } = useRequireRole(['admin']);
  if (loading) return <LoadingState label="Opening procedure studio" />;
  return (
    <div className="wm-page max-w-[1300px] space-y-8 pb-12">
      <header>
        <p className="text-[10px] font-bold uppercase tracking-[.18em] text-emerald-700">KNOWLEDGE GOVERNANCE</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-[-.05em] text-[#162f22] sm:text-[2.6rem]">Procedure Studio</h1>
        <p className="mt-3 max-w-xl text-sm leading-7 text-[#63786a]">Convert existing operating documents into reviewed procedure drafts, then govern the published workflows workers use.</p>
      </header>
      <div className="grid items-stretch gap-4 lg:grid-cols-3">
        <Link href="/procedure-studio/drafts" className="group flex min-h-[18rem] flex-col justify-between rounded-[1.6rem] bg-[#173c2d] p-7 text-white transition hover:bg-[#0e2c20] sm:p-8">
          <div className="flex items-start justify-between"><span className="grid h-12 w-12 place-items-center rounded-xl bg-white/10"><FilePlus2 className="h-6 w-6 text-[#beefd1]" /></span><ArrowRight className="h-5 w-5 text-[#beefd1] transition group-hover:translate-x-1" /></div>
          <div><p className="text-[10px] font-bold uppercase tracking-wider text-[#a8dcc0]">Document to draft</p><h2 className="mt-2 text-2xl font-semibold tracking-tight">Build procedure</h2><p className="mt-3 max-w-sm text-sm leading-6 text-[#c5d8ca]">Import a normal SOP and review editable operational steps against the original document.</p></div>
        </Link>
        <Link href="/knowledge-studio" className="group flex min-h-[18rem] flex-col justify-between rounded-[1.6rem] border border-[#dbe5dc] bg-white p-7 transition hover:border-emerald-300 sm:p-8">
          <div className="flex items-start justify-between"><span className="grid h-12 w-12 place-items-center rounded-xl bg-[#e6f3e9]"><GitBranchPlus className="h-6 w-6 text-emerald-800" /></span><ArrowRight className="h-5 w-5 text-emerald-700 transition group-hover:translate-x-1" /></div>
          <div><p className="text-[10px] font-bold uppercase tracking-wider text-emerald-800">Governed execution</p><h2 className="mt-2 text-2xl font-semibold tracking-tight text-[#183226]">Published SOPs</h2><p className="mt-3 max-w-sm text-sm leading-6 text-[#68776d]">Manage compiled versions, deterministic workflow steps and decisions.</p></div>
        </Link>
        <Link href="/knowledge-studio/references" className="group flex min-h-[18rem] flex-col justify-between rounded-[1.6rem] border border-[#dbe5dc] bg-white p-7 transition hover:border-emerald-300 sm:p-8">
          <div className="flex items-start justify-between"><span className="grid h-12 w-12 place-items-center rounded-xl bg-[#e6f3e9]"><FileSearch2 className="h-6 w-6 text-emerald-800" /></span><ArrowRight className="h-5 w-5 text-emerald-700 transition group-hover:translate-x-1" /></div>
          <div><p className="text-[10px] font-bold uppercase tracking-wider text-emerald-800">Grounded answers</p><h2 className="mt-2 text-2xl font-semibold tracking-tight text-[#183226]">Reference library</h2><p className="mt-3 max-w-sm text-sm leading-6 text-[#68776d]">Review parsed documents, approve trusted excerpts and archive outdated materials.</p></div>
        </Link>
      </div>
      <section className="rounded-[1.6rem] border border-[#dce5dc] bg-white p-6 sm:p-8">
        <h2 className="text-xl font-semibold tracking-tight">From document to controlled work</h2>
        <div className="mt-6 grid gap-3 sm:grid-cols-3">
          {[
            { step:'01',title:'Prepare',copy:'Import PDF, Word or other supported SOP documents into a reviewable draft.',icon:BookOpenText },
            { step:'02',title:'Review',copy:'Edit every suggested step; confirm its source and required actions.',icon:ClipboardCheck },
            { step:'03',title:'Govern',copy:'Only the existing compiler can publish an executable workflow.',icon:LockKeyhole },
          ].map(stage => <div key={stage.step} className="rounded-xl border border-[#e4ede5] bg-[#f7faf7] p-5">
            <div className="flex items-center justify-between"><span className="text-xs font-bold tracking-wider text-emerald-700">{stage.step}</span><stage.icon className="h-5 w-5 text-[#59886c]" /></div>
            <p className="mt-5 text-base font-semibold">{stage.title}</p><p className="mt-2 text-xs leading-6 text-[#728076]">{stage.copy}</p>
          </div>)}
        </div>
        <div className="mt-6 flex flex-wrap gap-3"><Link href="/procedure-studio/drafts" className="inline-flex min-h-11 items-center gap-2 rounded-xl bg-[#16553c] px-5 text-xs font-semibold text-white">Build from document <ArrowRight className="h-4 w-4" /></Link><Link href="/knowledge-studio/references" className="inline-flex min-h-11 items-center gap-2 rounded-xl border border-[#dce6de] bg-white px-5 text-xs font-semibold">Review reference drafts</Link></div>
      </section>
      <div className="flex items-start gap-3 rounded-xl border border-[#dce8de] bg-[#eef7f0] p-5"><ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-emerald-700" /><p className="text-xs leading-6 text-[#4e6e59]">Document-to-draft extraction and visual human review are now available. Automatic publication of a generated procedure is intentionally disabled until the reviewed draft passes the existing OWD compiler and publishing safeguards.</p></div>
    </div>
  );
}
