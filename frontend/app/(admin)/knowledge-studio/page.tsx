'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { ArrowUpRight, BookOpenText, Layers3, Plus, Search } from 'lucide-react';
import { useRequireRole } from '@/lib/auth';
import { apiClient, type PaginatedKnowledgeItems } from '@/lib/api-client';
import { PageHeader } from '@/components/shared/PageHeader';
import { LoadingState } from '@/components/shared/LoadingState';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';

export default function KnowledgeStudioPage() {
  const { loading: authLoading } = useRequireRole(['admin']);
  const [data, setData] = useState<PaginatedKnowledgeItems | null>(null);
  const [loadingData, setLoadingData] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState('');

  useEffect(() => {
    if (authLoading) return;
    apiClient<PaginatedKnowledgeItems>('/knowledge')
      .then(setData)
      .catch((caught) => setError(caught instanceof Error ? caught.message : 'Failed to load knowledge documents.'))
      .finally(() => setLoadingData(false));
  }, [authLoading]);

  if (authLoading || loadingData) return <LoadingState label="Loading Knowledge Studio" />;
  const items = (data?.items || []).filter((detail) => detail.item.title.toLowerCase().includes(query.trim().toLowerCase()) || detail.item.department_id.toLowerCase().includes(query.trim().toLowerCase()));

  return (
    <div className="wm-page space-y-7">
      <PageHeader eyebrow="Knowledge operations" title="Knowledge studio" description="Publish and govern the verified SOPs that power employee guidance." action={<Button asChild><Link href="/knowledge-studio/upload"><Plus className="h-4 w-4" />Upload SOP</Link></Button>} />

      <div className="grid gap-4 sm:grid-cols-3">
        <div className="wm-panel p-4"><p className="text-xs font-semibold text-muted-foreground">Documents</p><p className="mt-3 text-2xl font-semibold tracking-tight">{data?.total || 0}</p></div>
        <div className="wm-panel p-4"><p className="text-xs font-semibold text-muted-foreground">Published</p><p className="mt-3 text-2xl font-semibold tracking-tight text-emerald-700">{(data?.items || []).filter((item) => item.published_version).length}</p></div>
        <div className="wm-panel p-4"><p className="text-xs font-semibold text-muted-foreground">Departments</p><p className="mt-3 text-2xl font-semibold tracking-tight">{new Set((data?.items || []).map((item) => item.item.department_id)).size}</p></div>
      </div>

      {error ? <div role="alert" className="rounded-2xl border border-red-200 bg-red-50 p-5 text-sm text-red-700"><p className="font-semibold">Documents unavailable</p><p className="mt-1">{error}</p></div> : null}

      {!error ? (
        <section className="wm-panel overflow-hidden">
          <div className="flex flex-col gap-3 border-b p-4 sm:flex-row sm:items-center sm:justify-between sm:px-5">
            <div><h2 className="text-sm font-semibold">SOP library</h2><p className="mt-0.5 text-[11px] text-muted-foreground">Published and staged operational knowledge</p></div>
            <label className="relative block w-full sm:w-72"><span className="sr-only">Search SOP library</span><Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" /><input value={query} onChange={(event) => setQuery(event.target.value)} className="wm-input h-9 pl-9 text-xs" placeholder="Search title or department" /></label>
          </div>

          {items.length === 0 ? (
            <div className="grid min-h-64 place-items-center p-8 text-center"><div><span className="mx-auto grid h-11 w-11 place-items-center rounded-xl bg-muted text-muted-foreground"><BookOpenText className="h-5 w-5" /></span><p className="mt-3 text-sm font-semibold">{query ? 'No matching SOPs' : 'No SOPs published yet'}</p><p className="mt-1 text-xs text-muted-foreground">{query ? 'Try a different title or department.' : 'Upload an OWD Markdown file to begin.'}</p></div></div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[720px] text-left">
                <thead className="bg-muted/60 text-[10px] font-semibold uppercase tracking-[0.1em] text-muted-foreground"><tr><th className="px-5 py-3">Workflow</th><th className="px-4 py-3">Department</th><th className="px-4 py-3">Status</th><th className="px-4 py-3">Version</th><th className="px-5 py-3 text-right">Open</th></tr></thead>
                <tbody className="divide-y divide-border/70">
                  {items.map((detail) => {
                    const activeVersion = detail.published_version || detail.latest_version;
                    const status = activeVersion?.status?.toLowerCase() || 'unknown';
                    return (
                      <tr key={detail.item.id} className="group transition hover:bg-emerald-50/35">
                        <td className="px-5 py-4"><div className="flex items-center gap-3"><span className="grid h-9 w-9 place-items-center rounded-xl bg-muted text-muted-foreground group-hover:bg-emerald-100 group-hover:text-emerald-700"><Layers3 className="h-4 w-4" /></span><div><p className="text-sm font-semibold text-foreground">{detail.item.title}</p>{detail.item.workflow_code ? <p className="mt-0.5 font-mono text-[10px] text-muted-foreground">{detail.item.workflow_code}</p> : null}</div></div></td>
                        <td className="px-4 py-4 text-xs text-muted-foreground">{detail.item.department_id}</td>
                        <td className="px-4 py-4"><Badge variant={status === 'published' ? 'default' : status === 'staged' || status === 'processed' ? 'warning' : 'neutral'}>{status}</Badge></td>
                        <td className="px-4 py-4 text-xs font-medium">v{activeVersion?.version_number || 1}</td>
                        <td className="px-5 py-4 text-right"><Link href={`/knowledge-studio/${detail.item.id}`} aria-label={`Open ${detail.item.title}`} className="inline-grid h-8 w-8 place-items-center rounded-lg text-muted-foreground transition hover:bg-white hover:text-emerald-700 hover:shadow-sm"><ArrowUpRight className="h-4 w-4" /></Link></td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </section>
      ) : null}
    </div>
  );
}
