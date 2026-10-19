'use client';
import Link from 'next/link';
import { ArrowRight, BookOpenText, ClipboardCheck, FileSearch2, GitBranchPlus, Layers, LockKeyhole, ShieldCheck } from 'lucide-react';
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
        <p className="mt-3 max-w-xl text-sm leading-7 text-[#63786a]">Control which procedures and reference materials workers are allowed to use.</p>
      </header>
      <div className="grid items-stretch gap-4 lg:grid-cols-2">
        <Link href="/knowledge-studio" className="group flex min-h-[18rem] flex-col justify-between rounded-[1.6rem] bg-[#173c2d] p-7 text-white transition hover:bg-[#0e2c20] sm:p-8">
          <div className="flex items-start justify-between"><span className="grid h-12 w-12 place-items-center rounded-xl bg-white/10"><GitBranchPlus className="h-6 w-6 text-[#beefd1]" /></span><ArrowRight className="h-5 w-5 text-[#beefd1] transition group-hover:translate-x-1" /></div>
          <div><p className="text-[10px] font-bold uppercase tracking-wider text-[#a8dcc0]">Executable procedures</p><h2 className="mt-2 text-2xl font-semibold tracking-tight">Workflow library</h2><p className="mt-3 max-w-sm text-sm leading-6 text-[#c5d8ca]">Manage the versioned operational steps, decisions and required checks already supported by WorkMate.</p></div>
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
            { step:'01',title:'Prepare',copy:'Upload OWD-formatted workflow content or supported reference documents.',icon:BookOpenText },
            { step:'02',title:'Review',copy:'Verify the rules, published steps and reference excerpts.',icon:ClipboardCheck },
            { step:'03',title:'Govern',copy:'Restrict visible sources by department, version and approval status.',icon:LockKeyhole },
          ].map(stage => <div key={stage.step} className="rounded-xl border border-[#e4ede5] bg-[#f7faf7] p-5">
            <div className="flex items-center justify-between"><span className="text-xs font-bold tracking-wider text-emerald-700">{stage.step}</span><stage.icon className="h-5 w-5 text-[#59886c]" /></div>
            <p className="mt-5 text-base font-semibold">{stage.title}</p><p className="mt-2 text-xs leading-6 text-[#728076]">{stage.copy}</p>
          </div>)}
        </div>
        <div className="mt-6 flex flex-wrap gap-3"><Link href="/knowledge-studio/upload" className="inline-flex min-h-11 items-center gap-2 rounded-xl bg-[#16553c] px-5 text-xs font-semibold text-white">Upload controlled SOP <ArrowRight className="h-4 w-4" /></Link><Link href="/knowledge-studio/references" className="inline-flex min-h-11 items-center gap-2 rounded-xl border border-[#dce6de] bg-white px-5 text-xs font-semibold">Review reference drafts</Link></div>
      </section>
      <div className="flex items-start gap-3 rounded-xl border border-[#dce8de] bg-[#eef7f0] p-5"><ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-emerald-700" /><p className="text-xs leading-6 text-[#4e6e59]">Automatic PDF-to-executable-workflow conversion and visual step editing belong to Phase 3. This screen exposes only the current governed publishing tools.</p></div>
    </div>
  );
}
