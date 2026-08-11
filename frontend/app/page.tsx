'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

import { getRoleRedirectPath, getUserClaims } from '@/lib/auth';
import { LoadingState } from '@/components/shared/LoadingState';

export default function HomePage() {
  const router = useRouter();

  useEffect(() => {
    const claims = getUserClaims();
    router.replace(claims ? getRoleRedirectPath(claims.role) : '/login');
  }, [router]);

  return <LoadingState label="Opening WorkMate" />;
}
