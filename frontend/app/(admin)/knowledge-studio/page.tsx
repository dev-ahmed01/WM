'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { FilePlus2, Search, FlaskConical } from 'lucide-react';
import { useRequireRole } from '@/lib/auth';
import { apiClient, type PaginatedKnowledgeItems } from '@/lib/api-client';
import { DocumentPreviewImport } from '@/components/upload/DocumentPreviewImport';
import { UploadDropzone } from '@/components/upload/UploadDropzone';
import { EmptyState, ErrorNote, Page, PageTitle, StatusPill, Tabs, buttonPrimary, buttonQuiet, inputClass, relativeDate } from '@/components/shared/ui';
import { LoadingState } from '@/components/shared/LoadingState';

type Kind = 'procedure' | 'draft' | 'document';
interface Row { key: string; kind: Kind; name: string; category: string; department: string; version: string; status: string; updated: string; href: string }
interface Dept { id: string; name: string }
type RefDoc = { id: string; department_id: string; title: string; file_type: string; status: 'DRAFT' | 'APPROVED' | 'ARCHIVED'; created_at: string };
type Draft = { id: string; title: string; status: 'draft' | 'reviewed'; revision: number; updated_at: string };

const KIND_LABEL: Record<Kind, string> = { procedure: 'Procedure', draft: 'Procedure draft', document: 'Document' };
const deptName = (d: Dept[], id: string) => d.find((x) => x.id === id)?.name ?? id.replace(/[_-]+/g, ' ');

function TestAnswer({ departments, onClose }: { departments: Dept[]; onClose: () => void }) {
  const [question, setQuestion] = useState('');
  const [dept, setDept] = useState(departments[0]?.id ?? '');
  const [result, setResult] = useState<null | { outcome: string; explanation: string; matches: { title: string; description: string; score: number; would_be_offered: boolean }[]; note: string }>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const run = async () => {
    setBusy(true); setError(null);
    try { setResult(await apiClient('/knowledge/test-answer', { method: 'POST', body: JSON.stringify({ question: question.trim(), department_id: dept }) })); }
    catch (e) { setError(e instanceof Error && e.message ? e.message : 'Could not test that question.'); }
    finally { setBusy(false); }
  };
  return (
    <div role="dialog" aria-modal="true" aria-label="Test answer" className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4">
      <div className="w-full max-w-xl space-y-3 rounded-2xl bg-card p-5 shadow-xl">
        <h2 className="font-display text-lg font-semibold">Test an answer</h2>
        <p className="text-sm text-muted-foreground">Ask a question as an employee would. Nothing is saved and nobody is notified.</p>
        <div className="flex flex-wrap gap-2">
          <input value={question} onChange={(e) => setQuestion(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter' && question.trim().length > 2) void run(); }}
            aria-label="Question" placeholder="e.g. How do I post a goods receipt?" className={`${inputClass} min-w-0 flex-1`} />
          {departments.length > 1 ? <select value={dept} onChange={(e) => setDept(e.target.value)} aria-label="Department" className={`${inputClass} !w-auto`}>{departments.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}</select> : null}
          <button type="button" className={buttonPrimary} disabled={busy || question.trim().length < 3} onClick={() => void run()}>{busy ? 'Testing…' : 'Test'}</button>
        </div>
        {error ? <ErrorNote>{error}</ErrorNote> : null}
        {result ? (
          <div className="space-y-2 rounded-xl border border-border p-3 text-sm">
            <p className="font-medium">{result.explanation}</p>
            {result.matches.length ? <ul className="space-y-1.5">{result.matches.map((m) => (
              <li key={m.title} className="flex items-start justify-between gap-3"><span><span className="font-medium">{m.title}</span>{m.description ? <span className="block text-xs text-muted-foreground">{m.description}</span> : null}</span>
                <span className="flex-none text-xs text-muted-foreground">{Math.round(m.score * 100)}% match</span></li>))}</ul> : null}
            <p className="text-xs text-muted-foreground">{result.note}</p>
          </div>
        ) : null}
        <div className="flex justify-end"><button type="button" className={buttonQuiet} onClick={onClose}>Close</button></div>
      </div>
    </div>
  );
}

export default function KnowledgeStudioPage() {
  const { loading } = useRequireRole(['admin']);
  const [tab, setTab] = useState('all');
  const [rows, setRows] = useState<Row[] | null>(null);
  const [departments, setDepartments] = useState<Dept[]>([]);
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [testing, setTesting] = useState(false);
  const [uploadKind, setUploadKind] = useState<'document' | 'procedure'>('document');

  const load = useCallback(async () => {
    try {
      const depts = await apiClient<Dept[]>('/knowledge/departments').catch(() => [] as Dept[]);
      setDepartments(depts);
      const [sops, drafts, refs] = await Promise.all([
        (async () => { // the API pages at 100: read every page so the table is the whole library, not the first screenful
          const first = await apiClient<PaginatedKnowledgeItems>('/knowledge?limit=100&page=1');
          const pages = Math.ceil(first.total / 100);
          const rest = await Promise.all(Array.from({ length: Math.max(0, pages - 1) }, (_, i) => apiClient<PaginatedKnowledgeItems>(`/knowledge?limit=100&page=${i + 2}`)));
          return { ...first, items: [...first.items, ...rest.flatMap((r) => r.items)] } as PaginatedKnowledgeItems;
        })().catch(() => null),
        apiClient<{ items: Draft[] }>('/procedure/drafts').catch(() => null),
        Promise.all(depts.map((d) => apiClient<{ items: RefDoc[] }>(`/knowledge/references?department_id=${encodeURIComponent(d.id)}`).then((r) => r.items).catch(() => [] as RefDoc[]))),
      ]);
      const out: Row[] = [];
      (sops?.items ?? []).forEach((d) => {
        const v = d.published_version || d.latest_version;
        const s = (v?.status || '').toLowerCase();
        out.push({ key: `p-${d.item.id}`, kind: 'procedure', name: d.item.title, category: (d.item.category || 'Procedure').replace(/_/g, ' ').toLowerCase().replace(/^./, (c) => c.toUpperCase()), department: deptName(depts, d.item.department_id),
          version: v ? `v${v.version_number}` : '—', status: s === 'published' ? 'published' : s === 'archived' ? 'archived' : 'draft', updated: d.item.updated_at || d.item.created_at, href: `/knowledge-studio/${d.item.id}` });
      });
      (drafts?.items ?? []).forEach((d) => out.push({ key: `d-${d.id}`, kind: 'draft', name: d.title, category: 'Procedure draft', department: '—', version: `rev ${d.revision}`,
        status: d.status === 'reviewed' ? 'review' : 'draft', updated: d.updated_at, href: `/procedure-studio/drafts/${d.id}` }));
      refs.flat().forEach((r) => out.push({ key: `r-${r.id}`, kind: 'document', name: r.title, category: 'Company documents', department: deptName(depts, r.department_id), version: '—',
        status: r.status === 'APPROVED' ? 'published' : r.status === 'ARCHIVED' ? 'archived' : 'review', updated: r.created_at, href: '/knowledge-studio/references' }));
      out.sort((a, b) => (b.updated || '').localeCompare(a.updated || ''));
      setRows(out); setError(null);
    } catch { setError('Could not load your knowledge.'); setRows([]); }
  }, []);
  useEffect(() => { if (!loading) void load(); }, [loading, load]);

  const filtered = useMemo(() => (rows ?? []).filter((r) => (!status || r.status === status) &&
    (!query.trim() || `${r.name} ${r.category} ${r.department}`.toLowerCase().includes(query.trim().toLowerCase()))), [rows, query, status]);
  const categories = useMemo(() => {
    const map = new Map<string, { count: number; published: number; departments: Set<string> }>();
    (rows ?? []).forEach((r) => {
      const c = map.get(r.category) ?? { count: 0, published: 0, departments: new Set<string>() };
      c.count += 1; if (r.status === 'published') c.published += 1; if (r.department !== '—') c.departments.add(r.department);
      map.set(r.category, c);
    });
    return [...map.entries()].sort((a, b) => b[1].count - a[1].count);
  }, [rows]);

  if (loading || rows === null) return <LoadingState label="Loading Knowledge Studio" />;

  return (
    <Page wide>
      <PageTitle title="Knowledge Studio" hint="Everything WorkMate is allowed to answer from. Only published items are used."
        action={<div className="flex gap-2"><button type="button" className={buttonQuiet} onClick={() => setTesting(true)}><FlaskConical className="h-4 w-4" />Test answer</button>
          <button type="button" className={buttonPrimary} onClick={() => setTab('upload')}><FilePlus2 className="h-4 w-4" />Add knowledge</button></div>} />
      <Tabs label="Knowledge sections" value={tab} onChange={setTab} tabs={[{ id: 'all', label: 'All knowledge', count: rows.length }, { id: 'upload', label: 'Upload' }, { id: 'categories', label: 'Categories', count: categories.length }]} />
      {error ? <ErrorNote>{error}</ErrorNote> : null}

      {tab === 'all' ? (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-3">
            <div className="relative min-w-0 flex-1 sm:max-w-sm">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
              <input value={query} onChange={(e) => setQuery(e.target.value)} aria-label="Search knowledge" placeholder="Search by name, category or department" className={`${inputClass} pl-9`} />
            </div>
            <select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status" className={`${inputClass} !w-auto`}>
              <option value="">Any status</option><option value="published">Published</option><option value="review">Review required</option><option value="draft">Draft</option><option value="archived">Archived</option>
            </select>
          </div>
          {filtered.length === 0 ? (
            <EmptyState title={rows.length ? 'No knowledge matches' : 'No knowledge yet'} hint={rows.length ? 'Clear the search or status filter.' : 'Upload a company document or a procedure so WorkMate has something to answer from.'}
              action={rows.length ? undefined : <button type="button" className={buttonPrimary} onClick={() => setTab('upload')}>Add knowledge</button>} />
          ) : (
            <div className="overflow-x-auto rounded-xl border border-border bg-card">
              <table className="w-full min-w-[820px] text-left text-sm">
                <thead className="border-b border-border text-xs text-muted-foreground">
                  <tr><th className="px-4 py-3 font-medium">Name</th><th className="px-3 py-3 font-medium">Category</th><th className="px-3 py-3 font-medium">Department</th><th className="px-3 py-3 font-medium">Version</th><th className="px-3 py-3 font-medium">Status</th><th className="px-3 py-3 font-medium">Updated</th><th className="px-3 py-3" /></tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {filtered.map((r) => (
                    <tr key={r.key} className="hover:bg-muted/40">
                      <td className="px-4 py-3"><Link href={r.href} className="font-medium hover:underline">{r.name}</Link><span className="block text-xs text-muted-foreground">{KIND_LABEL[r.kind]}</span></td>
                      <td className="px-3 py-3 text-muted-foreground">{r.category}</td>
                      <td className="px-3 py-3 text-muted-foreground">{r.department}</td>
                      <td className="px-3 py-3 tabular-nums text-muted-foreground">{r.version}</td>
                      <td className="px-3 py-3"><StatusPill status={r.status} /></td>
                      <td className="px-3 py-3 text-muted-foreground">{relativeDate(r.updated)}</td>
                      <td className="px-3 py-3 text-right"><Link href={r.href} className="text-primary hover:underline">Open</Link></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      ) : null}

      {tab === 'upload' ? (
        <div className="space-y-5">
          <div role="radiogroup" aria-label="What are you adding?" className="grid gap-3 sm:grid-cols-2">
            {([['document', 'A company document', 'Policies, guides and manuals. Employees can ask questions about it once an administrator approves it.'],
              ['procedure', 'A step-by-step procedure', 'A procedure employees follow one step at a time. A manager must approve it before it goes live.']] as const).map(([id, title, hint]) => (
              <button key={id} type="button" role="radio" aria-checked={uploadKind === id} onClick={() => setUploadKind(id)}
                className={`rounded-xl border p-4 text-left transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${uploadKind === id ? 'border-primary bg-accent/50' : 'border-border hover:bg-muted/50'}`}>
                <span className="block font-medium">{title}</span><span className="mt-1 block text-sm text-muted-foreground">{hint}</span>
              </button>
            ))}
          </div>
          {uploadKind === 'document' ? <DocumentPreviewImport /> : (
            <div className="space-y-3">
              <UploadDropzone />
              <p className="text-sm text-muted-foreground">Have a Word or PDF document you want turned into steps instead? <Link href="/procedure-studio/drafts" className="text-primary underline">Import it as a draft</Link> and review each step.</p>
            </div>
          )}
        </div>
      ) : null}

      {tab === 'categories' ? (
        categories.length === 0 ? <EmptyState title="No categories yet" hint="Categories come from the knowledge you add." /> : (
          <div className="overflow-x-auto rounded-xl border border-border bg-card">
            <table className="w-full min-w-[480px] text-left text-sm">
              <thead className="border-b border-border text-xs text-muted-foreground"><tr><th className="px-4 py-3 font-medium">Category</th><th className="px-3 py-3 font-medium">Items</th><th className="px-3 py-3 font-medium">Published</th><th className="px-3 py-3 font-medium">Departments</th></tr></thead>
              <tbody className="divide-y divide-border">
                {categories.map(([name, c]) => (
                  <tr key={name} className="hover:bg-muted/40">
                    <td className="px-4 py-3 font-medium"><button type="button" className="hover:underline" onClick={() => { setQuery(name); setTab('all'); }}>{name}</button></td>
                    <td className="px-3 py-3 tabular-nums">{c.count}</td><td className="px-3 py-3 tabular-nums">{c.published}</td>
                    <td className="px-3 py-3 text-muted-foreground">{[...c.departments].join(', ') || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="border-t border-border px-4 py-3 text-xs text-muted-foreground">Categories are set when a procedure is written, so they are shown here but not edited here.</p>
          </div>
        )
      ) : null}

      {testing ? <TestAnswer departments={departments} onClose={() => setTesting(false)} /> : null}
    </Page>
  );
}
