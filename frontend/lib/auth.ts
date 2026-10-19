import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';

export interface UserClaims {
  sub: string;
  role: 'admin' | 'employee' | 'manager';
  department_id: string;
  exp: number;
}

let cachedProfile: UserClaims | null = null;

export function getUserClaims(): UserClaims | null {
  return cachedProfile;
}

export async function loadUserClaims(): Promise<UserClaims | null> {
  try {
    const result = await fetch('/api/session/me', { credentials: 'same-origin', cache: 'no-store' });
    if (!result.ok) {
      cachedProfile = null;
      return null;
    }
    const profile = await result.json() as UserClaims;
    if (!profile.sub || !profile.department_id ||
        !['admin', 'manager', 'employee'].includes(profile.role)) {
      cachedProfile = null;
      return null;
    }
    cachedProfile = profile;
    return profile;
  } catch {
    cachedProfile = null;
    return null;
  }
}

export function clearCachedUser() {
  cachedProfile = null;
}

export function getRoleRedirectPath(role?: string): string {
  if (role === 'admin') return '/procedure-studio';
  if (role === 'manager') return '/control-room';
  return '/workspace';
}

export function useRequireRole(allowedRoles: Array<'admin' | 'employee' | 'manager'>) {
  const router = useRouter();
  const [user, setUser] = useState<UserClaims | null>(null);
  const [loading, setLoading] = useState(true);
  const allowedKey = allowedRoles.join(',');

  useEffect(() => {
    let cancelled = false;
    void loadUserClaims().then(claims => {
      if (cancelled) return;
      if (!claims) router.replace('/login');
      else if (!allowedKey.split(',').includes(claims.role)) router.replace(getRoleRedirectPath(claims.role));
      else setUser(claims);
      setLoading(false);
    });
    return () => { cancelled = true; };
  }, [allowedKey, router]);

  return { user, loading };
}
