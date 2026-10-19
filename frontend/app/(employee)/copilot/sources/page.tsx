'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { ArrowLeft, Search, ShieldCheck } from 'lucide-react';
import { useRequireRole } from '@/lib/auth';
import { apiClient } from '@/lib/api-client';
import { LoadingState } from '@/components/shared/LoadingState';
import { PageHeader } from '@/components/shared/PageHeader';
import { SourceComparison } from '@/components/chat/SourceComparison';

type Source = {
  document_id: string; document_title: string; department_id: string;
  chunk_id: string; excerpt: string; chunk_index: number;
  start_offset: number; end_offset: number; match_score: number;
};

export default function SourceSearchPage() {
  const { loading } = useRequireRole(['admin', 'manager', 'employee']);
  const [query, setQuery] = useState('');
  const [sources, setSources] = useState<Source[]>([]);
  const [searched, setSearched] = useState(false);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const search = async () => {
    const q = query.trim();
    if (q.length < 2 || searching) return;
    setSearching(true);
    setSearched(false);
    setError(null);
    try {
      const response = await apiClient<{sources: Source[]}>(`/knowledge/references/search?q=${encodeURIComponent(q)}&limit=10`);
      setSources(response.sources);
      setSearched(true);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not search approved sources.');
    } finally {
      setSearching(false);
    }
  };

  if (loading) return <LoadingState label="Loading source search" />;

  return (
    <div className="wm-page max-w-5xl space-y-6">
      <Link href="/copilot" className="inline-flex items-center gap-2 text-xs font-medium text-muted-foreground hover:text-emerald-700"><ArrowLeft className="h-4 w-4" />Copilot</Link>
      <PageHeader eyebrow="Workplace knowledge" title="Find an approved source" description="Search approved evidence and compare source excerpts side by side. Nothing here advances a workflow." />
      <form onSubmit={(event) => { event.preventDefault(); void search(); }} className="wm-panel flex items-center gap-3 p-3 sm:p-4">
        <Search className="h-5 w-5 flex-none text-muted-foreground" />
        <input value={query} onChange={(event) => setQuery(event.target.value)} maxLength={300} aria-label="Search reference documents" placeholder="Search for a policy, instruction, or operational term…" className="min-w-0 flex-1 bg-transparent px-1 py-2 text-sm outline-none" />
        <button type="submit" disabled={searching || query.trim().length < 2} className="rounded-xl bg-emerald-700 px-4 py-2.5 text-xs font-semibold text-white hover:bg-emerald-800 disabled:opacity-50">{searching ? 'Searching…' : 'Search'}</button>
      </form>
      <div className="flex items-start gap-2 text-xs leading-5 text-muted-foreground">
        <ShieldCheck className="mt-0.5 h-4 w-4 flex-none text-emerald-700" />
        Only approved reference documents within your assigned department are searchable. Always follow validated SOP steps for actual workflow actions.
      </div>
      {error ? <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">{error}</div> : null}
      {searched && sources.length === 0 ? <div className="wm-panel p-8 text-center"><p className="text-sm font-semibold">No verified matching passages</p><p className="mt-2 text-xs text-muted-foreground">Try a different keyword or ask your administrator to review missing policy documentation.</p></div> : null}
      {sources.length > 0 ? <SourceComparison key={sources.map(source => source.chunk_id).join(':')} sources={sources} query={query} /> : null}
    </div>
  );
}
