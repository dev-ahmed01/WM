import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { apiClient } from '@/lib/api-client';

export interface UserClaims {
  sub: string;
  role: 'admin' | 'employee' | 'manager';
  department_id: string;
  exp: number;
}

export function parseJwt(token: string): UserClaims | null {
  try {
    const base64Url = token.split('.')[1];
    const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
    const jsonPayload = decodeURIComponent(
      atob(base64)
        .split('')
        .map((c) => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2))
        .join('')
    );
    return JSON.parse(jsonPayload);
  } catch {
    return null;
  }
}

export function getUserClaims(): UserClaims | null {
  if (typeof window === 'undefined') return null;
  const token = localStorage.getItem('token');
  if (!token) return null;
  const claims = parseJwt(token);
  if (!claims) return null;
  if (claims.exp && Date.now() >= claims.exp * 1000) return null;
  return claims;
}

export function getRoleRedirectPath(role?: string): string {
  switch (role) {
    case 'admin':
      return '/knowledge-studio';
    case 'manager':
      return '/intelligence-hub';
    case 'employee':
    default:
      return '/copilot';
  }
}

/**
 * Exchanges the stored refresh token for a new access token via POST /auth/refresh.
 * On success, updates the stored 'token' in localStorage.
 */
export async function refreshAccessToken(): Promise<string | null> {
  if (typeof window === 'undefined') return null;
  const refreshToken = localStorage.getItem('refresh_token');
  if (!refreshToken) return null;

  try {
    const res = await apiClient<{ access_token: string }>('/auth/refresh', {
      method: 'POST',
      body: JSON.stringify({ refresh_token: refreshToken }),
    });

    if (res?.access_token) {
      localStorage.setItem('token', res.access_token);
      return res.access_token;
    }
    return null;
  } catch {
    return null;
  }
}

export function useRequireRole(allowedRoles: Array<'admin' | 'employee' | 'manager'>) {
  const router = useRouter();
  const [user, setUser] = useState<UserClaims | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  useEffect(() => {
    const claims = getUserClaims();
    if (!claims) {
      router.push('/login');
    } else if (!allowedRoles.includes(claims.role)) {
      router.push('/login');
    } else {
      setUser(claims);
      setLoading(false);
    }
  }, [router]);

  return { user, loading };
}
