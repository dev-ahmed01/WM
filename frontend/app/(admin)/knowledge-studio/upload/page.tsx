'use client';

import React from 'react';
import { useRequireRole } from '@/lib/auth';
import { UploadDropzone } from '@/components/upload/UploadDropzone';
import { PageHeader } from '@/components/shared/PageHeader';
import { LoadingState } from '@/components/shared/LoadingState';

export default function KnowledgeUploadPage() {
  const { loading } = useRequireRole(['admin']);

  if (loading) return <LoadingState label="Loading upload workspace" />;

  return (
    <div className="wm-page max-w-5xl space-y-7">
      <PageHeader eyebrow="Knowledge operations" title="Publish an SOP" description="Upload a UTF-8 OWD Markdown workflow. WorkMate validates, compiles, and publishes it as one governed operation." />
      <UploadDropzone />
    </div>
  );
}
