'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { Archive, ArchiveRestore, Check, Pencil, Search, X } from 'lucide-react';
import { useRequireRole } from '@/lib/auth';
import { apiClient } from '@/lib/api-client';
import { EmptyState, ErrorNote, Page, PageTitle, buttonPrimary, inputClass, relativeDate } from '@/components/shared/ui';
import { LoadingState } from '@/components/shared/LoadingState';

interface Conversation { id: string; title: string; custom_title: boolean; preview: string; last_activity: string; messages: number; archived: boolean }

function group(items: Conversation[]): { label: string; items: Conversation[] }[] {
  const start = new Date(); start.setHours(0, 0, 0, 0);
  const day = 86400000;
  const buckets: Record<string, Conversation[]> = { Today: [], Yesterday: [], 'Previous 7 days': [], Earlier: [] };
  items.forEach((c) => {
    const age = start.getTime() - new Date(c.last_activity).getTime();
    (age <= 0 ? buckets.Today : age <= day ? buckets.Yesterday : age <= 7 * day ? buckets['Previous 7 days'] : buckets.Earlier).push(c);
  });
  return Object.entries(buckets).filter(([, v]) => v.length).map(([label, v]) => ({ label, items: v }));
}

export default function HistoryPage() {
  const { loading } = useRequireRole(['employee', 'manager', 'admin']);
  const [items, setItems] = useState<Conversation[] | null>(null);
  const [query, setQuery] = useState('');
  const [archived, setArchived] = useState(false);
  const [renaming, setRenaming] = useState<string | null>(null);
  const [draft, setDraft] = useState('');
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const r = await apiClient<{ items: Conversation[] }>(`/copilot/conversations?archived=${archived}&q=${encodeURIComponent(query.trim())}`);
      setItems(r.items); setError(null);
    } catch { setError('Could not load your conversations.'); setItems([]); }
  }, [archived, query]);

  useEffect(() => {
    if (loading) return;
    const t = setTimeout(() => void load(), query ? 250 : 0); // debounce typing
    return () => clearTimeout(t);
  }, [loading, load, query]);

  const patch = async (id: string, body: { title?: string; archived?: boolean }) => {
    try { await apiClient(`/copilot/conversations/${id}`, { method: 'PATCH', body: JSON.stringify(body) }); await load(); }
    catch { setError('That change could not be saved.'); }
  };

  const groups = useMemo(() => group(items ?? []), [items]);
  if (loading) return <LoadingState label="Loading history" />;

  return (
    <Page>
      <PageTitle title="History" hint={archived ? 'Archived conversations. Restore one to see it in your list again.' : 'Pick up where you left off.'}
        action={!archived ? <Link href="/copilot" className={buttonPrimary}>New conversation</Link> : undefined} />

      <div className="flex flex-wrap items-center gap-3">
        <div className="relative min-w-0 flex-1 sm:max-w-sm">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
          <input value={query} onChange={(e) => setQuery(e.target.value)} aria-label="Search conversations" placeholder="Search your conversations" className={`${inputClass} pl-9`} />
        </div>
        <button type="button" onClick={() => setArchived((a) => !a)} className="text-sm text-muted-foreground underline-offset-4 hover:text-foreground hover:underline">
          {archived ? 'Back to conversations' : 'Archived'}
        </button>
      </div>

      {error ? <ErrorNote>{error}</ErrorNote> : null}
      {items === null ? <p className="text-sm text-muted-foreground">Loading…</p> : groups.length === 0 ? (
        <EmptyState title={query ? 'No conversations match' : archived ? 'Nothing archived' : 'No conversations yet'}
          hint={query ? 'Try different words.' : archived ? undefined : 'Ask the assistant something and it will show up here.'} />
      ) : groups.map((g) => (
        <section key={g.label} aria-label={g.label}>
          <h2 className="mb-1 px-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">{g.label}</h2>
          <ul className="divide-y divide-border rounded-xl border border-border bg-card">
            {g.items.map((c) => (
              <li key={c.id} className="group flex items-center gap-2 px-4 py-3">
                {renaming === c.id ? (
                  <form className="flex flex-1 items-center gap-2" onSubmit={(e) => { e.preventDefault(); if (draft.trim()) void patch(c.id, { title: draft.trim() }); setRenaming(null); }}>
                    <input autoFocus value={draft} onChange={(e) => setDraft(e.target.value)} maxLength={160} aria-label="Conversation title" className={inputClass} />
                    <button type="submit" aria-label="Save title" className="grid h-10 w-10 place-items-center rounded-lg hover:bg-muted"><Check className="h-4 w-4" /></button>
                    <button type="button" aria-label="Cancel" onClick={() => setRenaming(null)} className="grid h-10 w-10 place-items-center rounded-lg hover:bg-muted"><X className="h-4 w-4" /></button>
                  </form>
                ) : (
                  <>
                    <Link href={`/copilot?session=${c.id}`} className="min-w-0 flex-1 rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
                      <p className="truncate text-sm font-medium">{c.title}</p>
                      <p className="mt-0.5 truncate text-xs text-muted-foreground">{c.preview || `${c.messages} messages`}</p>
                    </Link>
                    <span className="hidden flex-none text-xs text-muted-foreground sm:block">{relativeDate(c.last_activity)}</span>
                    <button type="button" aria-label={`Rename ${c.title}`} onClick={() => { setRenaming(c.id); setDraft(c.title); }}
                      className="grid h-10 w-10 flex-none place-items-center rounded-lg text-muted-foreground hover:bg-muted hover:text-foreground"><Pencil className="h-4 w-4" /></button>
                    <button type="button" aria-label={archived ? `Restore ${c.title}` : `Archive ${c.title}`} onClick={() => void patch(c.id, { archived: !archived })}
                      className="grid h-10 w-10 flex-none place-items-center rounded-lg text-muted-foreground hover:bg-muted hover:text-foreground">
                      {archived ? <ArchiveRestore className="h-4 w-4" /> : <Archive className="h-4 w-4" />}
                    </button>
                  </>
                )}
              </li>
            ))}
          </ul>
        </section>
      ))}
      <p className="text-xs text-muted-foreground">Archiving hides a conversation from you. Your company keeps a record of conversations as required by its retention policy.</p>
    </Page>
  );
}
