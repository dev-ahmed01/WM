'use client';

import React, { useState } from 'react';
import { useRequireRole } from '@/lib/auth';
import { UploadDropzone } from '@/components/upload/UploadDropzone';
import { DocumentPreviewImport } from '@/components/upload/DocumentPreviewImport';
import { PageHeader } from '@/components/shared/PageHeader';
import { LoadingState } from '@/components/shared/LoadingState';

export default function KnowledgeUploadPage() {
  const { loading } = useRequireRole(['admin']);
  const [mode, setMode] = useState<'preview' | 'publish'>('preview');

  if (loading) return <LoadingState label="Loading knowledge workspace" />;

  return (
    <div className="wm-page max-w-5xl space-y-6">
      <PageHeader
        eyebrow="Knowledge operations"
        title="Add knowledge"
        description="Inspect everyday documents or publish an approved operational workflow."
      />

      <div className="inline-flex max-w-full flex-wrap gap-1 rounded-xl border border-border bg-white p-1" role="group" aria-label="Knowledge import mode">
        <button
          type="button"
          aria-pressed={mode === 'preview'}
          onClick={() => setMode('preview')}
          className={`rounded-lg px-4 py-2.5 text-sm font-semibold transition ${mode === 'preview' ? 'bg-emerald-700 text-white shadow-sm' : 'text-muted-foreground hover:bg-muted hover:text-foreground'}`}
        >
          Read document
        </button>
        <button
          type="button"
          aria-pressed={mode === 'publish'}
          onClick={() => setMode('publish')}
          className={`rounded-lg px-4 py-2.5 text-sm font-semibold transition ${mode === 'publish' ? 'bg-emerald-700 text-white shadow-sm' : 'text-muted-foreground hover:bg-muted hover:text-foreground'}`}
        >
          Publish verified workflow
        </button>
      </div>

      {mode === 'preview' ? <DocumentPreviewImport /> : <UploadDropzone />}
    </div>
  );
}
