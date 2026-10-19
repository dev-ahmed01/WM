'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { ArrowRight, BookOpenText, Check, ClipboardCopy, Download, Plus, ShieldCheck } from 'lucide-react';

export type ReferenceExcerpt = {
  document_id: string;
  document_title: string;
  department_id: string;
  chunk_id: string;
  excerpt: string;
  chunk_index: number;
  start_offset: number;
  end_offset: number;
  match_score: number;
};

function comparisonNote(entries: ReferenceExcerpt[]): string {
  const parts = [
    'WORKMATE SOURCE COMPARISON',
    'Exported at: ' + new Date().toISOString(),
    'Retrieved approved passages; no automated policy interpretation or conflict determination.',
  ];
  entries.forEach((entry, index) => {
    parts.push('', 'SOURCE ' + (index + 1), 'Document: ' + entry.document_title,
      'Department: ' + entry.department_id,
      'Excerpt: ' + (entry.chunk_index + 1),
      'Offsets: ' + entry.start_offset + '-' + entry.end_offset,
      'Citation ID: ' + entry.chunk_id, '', entry.excerpt);
  });
  parts.push('', 'This comparison is not a signed audit record. Verify the full source documents before operational action.');
  return parts.join('\n');
}

export function SourceComparison({ sources, query }: { sources: ReferenceExcerpt[]; query: string }) {
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [notice, setNotice] = useState('');
  const chosen = selectedIds.map(id => sources.find(source => source.chunk_id === id))
    .filter((item): item is ReferenceExcerpt => Boolean(item));
  const canCompare = chosen.length === 2;

  function choose(id: string) {
    setSelectedIds(current => current.includes(id) ? current.filter(item => item !== id)
      : current.length < 2 ? [...current, id] : current);
    setNotice('');
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText(comparisonNote(chosen));
      setNotice('Comparison copied to clipboard.');
    } catch {
      setNotice('Clipboard access is unavailable; download instead.');
    }
  }

  function download() {
    const blob = new Blob([comparisonNote(chosen)], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = 'workmate-reference-comparison.txt';
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    setNotice('Evidence comparison prepared.');
  }

  const question = canCompare ? 'Compare the approved guidance in "' + chosen[0].document_title +
    '" and "' + chosen[1].document_title + '" regarding ' + query +
    '. Explain only what the available cited references actually establish.' : '';

  return (
    <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(19rem,0.72fr)]">
      <section className="space-y-3" aria-label="Verified source excerpts">
        <div className="flex items-end justify-between gap-3">
          <div><h2 className="text-base font-semibold">{sources.length} matching excerpts</h2><p className="mt-1 text-xs text-muted-foreground">Choose up to two to inspect side by side.</p></div>
          <span className="shrink-0 text-xs font-semibold text-emerald-700">{chosen.length}/2 selected</span>
        </div>
        {sources.map((source) => {
          const selected = selectedIds.includes(source.chunk_id);
          return (
            <article key={source.chunk_id} className={'rounded-2xl border bg-white p-5 shadow-panel transition sm:p-6 ' + (selected ? 'border-emerald-400 ring-2 ring-emerald-100' : 'border-border/80')}>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <div className="inline-flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-widest text-emerald-700"><ShieldCheck className="h-3.5 w-3.5" />Approved reference</div>
                  <h3 className="mt-2 break-words text-sm font-semibold text-emerald-900">{source.document_title}</h3>
                  <p className="mt-1 text-[11px] text-muted-foreground">Excerpt {source.chunk_index + 1} · offset {source.start_offset}–{source.end_offset}</p>
                </div>
                <button type="button" aria-label={(selected ? 'Remove from comparison: ' : 'Compare excerpt from ') + source.document_title} aria-pressed={selected} disabled={!selected && chosen.length === 2}
                  onClick={() => choose(source.chunk_id)} className={'inline-flex items-center gap-1.5 rounded-xl px-3 py-2 text-xs font-semibold transition disabled:cursor-not-allowed disabled:opacity-40 ' + (selected ? 'bg-emerald-700 text-white' : 'border border-emerald-200 bg-emerald-50 text-emerald-800 hover:bg-emerald-100')}>
                  {selected ? <Check className="h-3.5 w-3.5" /> : <Plus className="h-3.5 w-3.5" />}{selected ? 'Selected' : 'Compare'}
                </button>
              </div>
              <p className="mt-4 whitespace-pre-wrap break-words border-l-[3px] border-emerald-200 pl-4 text-sm leading-7 text-foreground">{source.excerpt}</p>
            </article>
          );
        })}
      </section>
      <aside className="wm-panel overflow-hidden lg:sticky lg:top-24" aria-label="Evidence comparison">
        <div className="border-b border-border bg-[#f5faf6] p-5">
          <span className="grid h-10 w-10 place-items-center rounded-xl bg-emerald-100 text-emerald-800"><BookOpenText className="h-5 w-5" /></span>
          <h2 className="mt-3 text-lg font-semibold tracking-tight">Evidence comparison</h2>
          <p className="mt-1 text-xs leading-5 text-muted-foreground">Review exact approved excerpts without AI-generated differences.</p>
        </div>
        <div className="space-y-3 p-5">
          {chosen.length === 0 ? <p className="text-xs leading-6 text-muted-foreground">Select a passage to start. WorkMate only compares sources you can already access.</p> : null}
          {chosen.map((entry, index) => (
            <div key={entry.chunk_id} className="rounded-xl border border-border bg-muted/30 p-3.5">
              <p className="text-[10px] font-bold uppercase tracking-widest text-emerald-700">Source {index + 1}</p>
              <p className="mt-1.5 break-words text-xs font-semibold">{entry.document_title}</p>
              <p className="mt-2 whitespace-pre-wrap break-words text-xs leading-6 text-muted-foreground">{entry.excerpt}</p>
            </div>
          ))}
          {chosen.length === 1 ? <p className="text-xs text-muted-foreground">Choose one more passage to enable comparison export.</p> : null}
          {canCompare ? (
            <>
              <div className="grid grid-cols-2 gap-2">
                <button type="button" onClick={() => void copy()} className="inline-flex items-center justify-center gap-1.5 rounded-xl border border-border px-3 py-2.5 text-xs font-semibold hover:bg-muted"><ClipboardCopy className="h-3.5 w-3.5" />Copy</button>
                <button type="button" onClick={download} className="inline-flex items-center justify-center gap-1.5 rounded-xl border border-border px-3 py-2.5 text-xs font-semibold hover:bg-muted"><Download className="h-3.5 w-3.5" />Download</button>
              </div>
              <Link href={'/copilot?mode=reference&draft=' + encodeURIComponent(question.slice(0, 500))} className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-emerald-700 px-3 py-3 text-xs font-semibold text-white hover:bg-emerald-800">Ask Copilot <ArrowRight className="h-4 w-4" /></Link>
            </>
          ) : null}
          {notice ? <p role="status" className="text-[11px] text-emerald-800">{notice}</p> : null}
          {chosen.length ? <button type="button" onClick={() => setSelectedIds([])} className="w-full text-center text-[11px] font-medium text-muted-foreground hover:text-emerald-700">Clear selection</button> : null}
        </div>
      </aside>
    </div>
  );
}
