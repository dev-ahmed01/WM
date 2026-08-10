'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

import { getRoleRedirectPath, getUserClaims } from '@/lib/auth';

export default function HomePage() {
  const router = useRouter();

  useEffect(() => {
    const claims = getUserClaims();
    router.replace(claims ? getRoleRedirectPath(claims.role) : '/login');
  }, [router]);

  return <div className="p-8 text-sm text-slate-600">Loading WorkMate…</div>;
}
