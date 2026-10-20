'use client';

import React, { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { ArrowLeft, BookOpenCheck, FileText, ShieldCheck } from 'lucide-react';
import { useRequireRole } from '@/lib/auth';
import { apiClient } from '@/lib/api-client';
import { LoadingState } from '@/components/shared/LoadingState';
import { PageHeader } from '@/components/shared/PageHeader';

type ReferenceRow = {
  id: string; department_id: string; title: string; original_filename: string;
  file_type: string; status: 'DRAFT' | 'APPROVED' | 'ARCHIVED';
  extracted_characters: number; chunk_count: number; created_at: string;
};
type SourceContent = {
  document: ReferenceRow;
  chunks: Array<{id: string; chunk_index: number; content: string; start_offset: number; end_offset: number}>;
  preview_truncated: boolean;
};

export default function ReferenceLibraryPage() {
  const { loading: authLoading } = useRequireRole(['admin']);
  const [departments, setDepartments] = useState<Array<{id: string; name: string}>>([]);
  const [departmentId, setDepartmentId] = useState('');
  const [items, setItems] = useState<ReferenceRow[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selected, setSelected] = useState<SourceContent | null>(null);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (authLoading) return;
    apiClient<Array<{id: string; name: string}>>('/knowledge/departments')
      .then((rows) => { setDepartments(rows); setDepartmentId(rows[0]?.id || ''); })
      .catch((err: Error) => { setError(err.message); setLoading(false); });
  }, [authLoading]);

  const refresh = useCallback(async () => {
    if (!departmentId) return;
    setLoading(true);
    setError(null);
    try {
      const response = await apiClient<{items: ReferenceRow[]}>(
        `/knowledge/references?department_id=${encodeURIComponent(departmentId)}`,
      );
      setItems(response.items);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not load reference documents.');
    } finally {
      setLoading(false);
    }
  }, [departmentId]);

  useEffect(() => {
    setSelectedId(null);
    setSelected(null);
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (!selectedId || !departmentId) return;
    setSelected(null);
    apiClient<SourceContent>(`/knowledge/references/${encodeURIComponent(selectedId)}/content?department_id=${encodeURIComponent(departmentId)}`)
      .then(setSelected)
      .catch((caught) => setError(caught instanceof Error ? caught.message : 'Unable to review document.'));
  }, [selectedId, departmentId]);

  const review = async (action: 'approve' | 'archive') => {
    if (!selectedId || !departmentId || working) return;
    if (action === 'approve' && !window.confirm('Approve this reviewed document for department-scoped search? It will not become an executable SOP.')) return;
    if (action === 'archive' && !window.confirm('Archive this document? Employees will no longer find it in reference search.')) return;
    setWorking(true);
    setError(null);
    try {
      await apiClient(`/knowledge/references/${encodeURIComponent(selectedId)}/${action}?department_id=${encodeURIComponent(departmentId)}`, { method: 'POST' });
      setSelectedId(null);
      setSelected(null);
      await refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Review action failed.');
    } finally {
      setWorking(false);
    }
  };

  if (authLoading) return <LoadingState label="Loading reference library" />;

  return (
    <div className="wm-page space-y-6">
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <Link href="/knowledge-studio" className="inline-flex items-center gap-1 hover:text-emerald-700"><ArrowLeft className="h-4 w-4" />Knowledge Studio</Link>
        <span>/</span><span>Reference library</span>
      </div>
      <PageHeader eyebrow="Knowledge operations" title="Reference library" description="Review extracted documents before making them searchable. Existing executable workflows are managed separately." />
      <div className="flex flex-wrap items-end justify-between gap-3">
        <label><span className="wm-label">Department</span><select value={departmentId} onChange={(event) => setDepartmentId(event.target.value)} className="wm-input min-w-48">{departments.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}</select></label>
        <Link href="/knowledge-studio/upload" className="rounded-xl bg-emerald-700 px-4 py-2.5 text-sm font-semibold text-white hover:bg-emerald-800">Add document</Link>
      </div>
      {error ? <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700" role="alert">{error}</div> : null}
      <div className="grid gap-5 lg:grid-cols-[minmax(0,22rem)_minmax(0,1fr)]">
        <section className="wm-panel min-h-72 overflow-hidden" aria-label="Department reference documents">
          <div className="border-b border-border p-4"><h2 className="text-sm font-semibold">Documents</h2><p className="mt-1 text-xs text-muted-foreground">Drafts require review before employee search</p></div>
          {loading ? <p className="p-5 text-sm text-muted-foreground">Loading documents…</p> : items.length === 0 ? <p className="p-5 text-sm text-muted-foreground">No reference documents in this department yet.</p> : (
            <div className="divide-y divide-border">
              {items.map((item) => (
                <button key={item.id} type="button" onClick={() => setSelectedId(item.id)} className={`flex w-full items-start gap-3 px-4 py-4 text-left hover:bg-emerald-50 ${selectedId === item.id ? 'bg-emerald-50' : ''}`} aria-pressed={selectedId === item.id}>
                  <FileText className="mt-0.5 h-5 w-5 shrink-0 text-emerald-700" />
                  <span className="min-w-0 flex-1"><span className="block truncate text-sm font-semibold">{item.title}</span><span className="mt-1 block truncate text-xs text-muted-foreground">{item.original_filename} · {item.chunk_count} excerpts</span></span>
                  <span className={`rounded-md px-2 py-1 text-[10px] font-semibold ${item.status === 'APPROVED' ? 'bg-emerald-100 text-emerald-800' : item.status === 'DRAFT' ? 'bg-amber-100 text-amber-800' : 'bg-slate-100 text-slate-600'}`}>{item.status}</span>
                </button>
              ))}
            </div>
          )}
        </section>
        <section className="wm-panel min-h-72 overflow-hidden" aria-label="Document review">
          {!selectedId ? (
            <div className="flex min-h-72 flex-col items-center justify-center px-8 text-center"><BookOpenCheck className="h-8 w-8 text-emerald-700" /><p className="mt-3 text-sm font-semibold">Select a document to inspect</p><p className="mt-2 max-w-sm text-xs leading-5 text-muted-foreground">Only manually approved reference text becomes searchable; it never changes the OWD workflow graph.</p></div>
          ) : !selected ? <p className="p-6 text-sm text-muted-foreground">Loading extracted evidence…</p> : (
            <>
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border p-5">
                <div><h2 className="text-base font-semibold">{selected.document.title}</h2><p className="mt-1 text-xs text-muted-foreground">{selected.document.file_type.toUpperCase()} · {selected.document.extracted_characters.toLocaleString()} characters</p></div>
                <span className="inline-flex items-center gap-1.5 text-xs text-emerald-800"><ShieldCheck className="h-4 w-4" />Scoped to {selected.document.department_id}</span>
              </div>
              <div className="max-h-[30rem] space-y-3 overflow-auto p-5">
                {selected.chunks.map((chunk) => <div key={chunk.id} className="rounded-xl border border-border bg-[#fafcfb] p-4"><p className="mb-2 text-[10px] font-medium text-muted-foreground">Excerpt {chunk.chunk_index + 1} · characters {chunk.start_offset}–{chunk.end_offset}</p><p className="whitespace-pre-wrap break-words text-sm leading-6">{chunk.content}</p></div>)}
                {selected.preview_truncated ? <p className="text-xs text-amber-700">Only the first 50 excerpts are displayed. Do not approve without checking the full source.</p> : null}
              </div>
              <div className="flex flex-wrap items-center gap-2 border-t border-border p-5">
                {selected.document.status === 'DRAFT' ? <button disabled={working || selected.preview_truncated} onClick={() => void review('approve')} className="rounded-xl bg-emerald-700 px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-50">Approve for search</button> : null}
                {selected.document.status === 'APPROVED' ? <button disabled={working} onClick={() => void review('archive')} className="rounded-xl border border-red-200 px-4 py-2.5 text-sm font-semibold text-red-700 disabled:opacity-50">Archive document</button> : null}
                <p className="text-xs text-muted-foreground">{selected.document.status === 'ARCHIVED' ? 'Archived documents are excluded from search.' : 'Approval enables read-only reference search, not workflow execution.'}</p>
              </div>
            </>
          )}
        </section>
      </div>
    </div>
  );
}
