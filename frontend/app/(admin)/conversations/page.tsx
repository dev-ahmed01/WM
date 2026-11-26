'use client';

import React from 'react';
import { useRequireRole } from '@/lib/auth';
import { StaffCases } from '@/components/cases/StaffCases';
import { PageTitle } from '@/components/shared/ui';
import { LoadingState } from '@/components/shared/LoadingState';

export default function ConversationsPage() {
  const { loading } = useRequireRole(['admin']);
  if (loading) return <LoadingState label="Loading conversations" />;
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="px-4 pb-3 pt-6 sm:px-6 lg:px-8 lg:pt-8">
        <PageTitle title="Conversations" hint="Questions WorkMate could not answer, requests for a person, and answers employees flagged." />
      </div>
      <div className="min-h-0 flex-1"><StaffCases /></div>
    </div>
  );
}
