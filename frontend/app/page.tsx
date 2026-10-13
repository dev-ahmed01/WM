'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

import { getRoleRedirectPath, loadUserClaims } from '@/lib/auth';
import { LoadingState } from '@/components/shared/LoadingState';

export default function HomePage() {
  const router = useRouter();

  useEffect(() => {
    void loadUserClaims().then(claims => {
      router.replace(claims ? getRoleRedirectPath(claims.role) : '/login');
    });
  }, [router]);

  return <LoadingState label="Opening WorkMate" />;
}
