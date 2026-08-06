'use client';

import React from 'react';
import { useRequireRole } from '@/lib/auth';
import { UploadDropzone } from '@/components/upload/UploadDropzone';

export default function KnowledgeUploadPage() {
  const { loading } = useRequireRole(['admin']);

  if (loading) return <div className="p-8">Loading...</div>;

  return (
    <div className="p-8 max-w-3xl mx-auto">
      <h1 className="text-2xl font-bold text-gray-900 mb-6">Upload Knowledge Document</h1>
      <UploadDropzone />
    </div>
  );
}
