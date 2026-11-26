'use client';

import React, { Suspense, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useRequireRole } from '@/lib/auth';
import { StaffCases } from '@/components/cases/StaffCases';
import { BlockedWork } from '@/components/escalations/BlockedWork';
import { SopApprovals } from '@/components/escalations/SopApprovals';
import { PageTitle, Tabs } from '@/components/shared/ui';
import { LoadingState } from '@/components/shared/LoadingState';

function Centre() {
  const { user, loading } = useRequireRole(['manager', 'admin']);
  const router = useRouter();
  const search = useSearchParams();
  const manager = user?.role === 'manager';
  const requested = search.get('tab');
  const [tab, setTab] = useState(requested === 'blocked' || requested === 'approvals' ? requested : 'requests');
  if (loading || !user) return <LoadingState label="Loading escalations" />;

  const tabs = [
    { id: 'requests', label: manager ? 'Requests for you' : 'Requests' },
    { id: 'blocked', label: 'Blocked work' },
    ...(manager ? [{ id: 'approvals', label: 'SOP approvals' }] : []),
  ];
  const change = (id: string) => { setTab(id); router.replace(`/escalation-centre?tab=${id}`, { scroll: false }); };

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="space-y-4 px-4 pt-6 sm:px-6 lg:px-8 lg:pt-8">
        <PageTitle title="Escalations" hint="Requests that need a decision, work that is blocked, and SOPs waiting for approval." />
        <Tabs tabs={tabs} value={tab} onChange={change} label="Escalation areas" />
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto">
        {tab === 'requests' ? <div className="h-full"><StaffCases managed={manager} /></div> : null}
        {tab === 'blocked' ? <BlockedWork /> : null}
        {tab === 'approvals' && manager ? <SopApprovals /> : null}
      </div>
    </div>
  );
}

export default function EscalationCentre() {
  return <Suspense fallback={<LoadingState label="Loading escalations" />}><Centre /></Suspense>;
}
