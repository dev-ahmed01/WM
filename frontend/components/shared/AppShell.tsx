'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { Check, ChevronsUpDown, Globe, LogOut, Stethoscope } from 'lucide-react';
import { loadUserClaims, getUserClaims, clearCachedUser, type UserClaims } from '@/lib/auth';
import { LANDING, NAV, isActive, isAllowedPath } from '@/lib/nav';
import { LANGUAGE_LABEL, useLanguage, type Language } from '@/lib/language';
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { cn } from '@/lib/utils';
import { LoadingState } from '@/components/shared/LoadingState';

// Pages that must render without a session (no shell, no redirect to /login).
const PUBLIC_PATHS = ['/login', '/accept-invite'];
const isPublicPath = (pathname: string) => PUBLIC_PATHS.some((p) => pathname === p || pathname.startsWith(`${p}/`));

// Presentation only: the session carries ids, not display names.
const displayName = (sub: string) => sub.replace(/^(demo|usr)_/, '').replace(/[_-]+/g, ' ');
const departmentLabel = (id: string) => id.replace(/[_-]+/g, ' ').replace(/(^|\s)[a-z]/g, (c) => c.toUpperCase());

function Brand() {
  return (
    <Link href="/" className="flex min-h-11 items-center gap-2.5 rounded-lg focus-visible:outline-offset-4" aria-label="WorkMate home">
      <span className="grid h-8 w-8 place-items-center rounded-lg bg-primary text-xs font-bold tracking-tight text-primary-foreground">WM</span>
      <span className="font-display text-[17px] font-semibold tracking-tight text-foreground">WorkMate</span>
    </Link>
  );
}

function AccountMenu({ user, onLogout, className }: { user: UserClaims; onLogout: () => void; className?: string }) {
  const [language, setLanguage] = useLanguage();
  const name = displayName(user.sub);
  const diagnostics = user.role !== 'employee';
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          aria-label="Account menu"
          className={cn('flex w-full items-center gap-2.5 rounded-xl p-2 text-left transition hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring', className)}
        >
          <span className="grid h-8 w-8 flex-none place-items-center rounded-full bg-accent text-xs font-semibold text-accent-foreground">
            {name.slice(0, 1).toUpperCase()}
          </span>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-[13px] font-medium capitalize text-foreground">{name}</span>
            <span className="block truncate text-[11px] capitalize text-muted-foreground">{user.role}</span>
          </span>
          <ChevronsUpDown className="h-4 w-4 flex-none text-muted-foreground" aria-hidden="true" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" side="top" className="w-60 rounded-xl p-1.5">
        <DropdownMenuLabel className="px-2.5 py-2 font-normal">
          <p className="truncate text-sm font-medium capitalize text-foreground">{name}</p>
          <p className="mt-0.5 truncate text-xs capitalize text-muted-foreground">{user.role} · {departmentLabel(user.department_id)}</p>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuLabel className="flex items-center gap-2 px-2.5 py-1 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
          <Globe className="h-3.5 w-3.5" aria-hidden="true" /> Language
        </DropdownMenuLabel>
        {(['en', 'hi'] as Language[]).map((code) => (
          <DropdownMenuItem key={code} onClick={() => setLanguage(code)} className="rounded-lg px-2.5 py-2">
            <span className="flex-1">{LANGUAGE_LABEL[code]}</span>
            {language === code ? <Check className="h-4 w-4 text-primary" aria-label="Selected" /> : null}
          </DropdownMenuItem>
        ))}
        {diagnostics ? (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuItem asChild className="rounded-lg px-2.5 py-2">
              <Link href="/pilot"><Stethoscope className="mr-2 h-4 w-4" aria-hidden="true" />Diagnostics</Link>
            </DropdownMenuItem>
          </>
        ) : null}
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={onLogout} className="rounded-lg px-2.5 py-2 text-red-600 focus:bg-red-50 focus:text-red-700">
          <LogOut className="mr-2 h-4 w-4" aria-hidden="true" />Log out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<UserClaims | null>(() => getUserClaims());

  useEffect(() => {
    let cancelled = false;
    if (isPublicPath(pathname)) return;
    void loadUserClaims().then((profile) => {
      if (cancelled) return;
      setUser(profile);
      if (!profile) router.replace('/login');
      else if (pathname !== '/' && !isAllowedPath(profile.role, pathname)) router.replace(LANDING[profile.role]);
    });
    return () => { cancelled = true; };
  }, [pathname, router]);

  if (isPublicPath(pathname)) return <>{children}</>;
  if (!user) return <div className="grid min-h-screen place-items-center bg-background"><LoadingState label="Opening WorkMate" /></div>;

  const items = NAV[user.role];
  const handleLogout = () => {
    void fetch('/api/session/logout', { method: 'POST', credentials: 'same-origin' }).finally(() => {
      clearCachedUser();
      setUser(null);
      router.replace('/login');
    });
  };

  return (
    <div className="min-h-dvh bg-background">
      <a href="#main-content" className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-[100] focus:rounded-lg focus:bg-card focus:px-4 focus:py-2 focus:text-sm focus:font-medium focus:text-primary focus:shadow-lg">
        Skip to main content
      </a>

      {/* Desktop: a compact sidebar with the three destinations; the account menu holds everything else. */}
      <aside className="fixed inset-y-0 left-0 z-40 hidden w-56 flex-col border-r border-border bg-card px-3 py-4 lg:flex">
        <div className="px-2 pb-6 pt-1"><Brand /></div>
        <nav aria-label="Primary" className="space-y-0.5">
          {items.map(({ label, href, icon: Icon }) => {
            const active = isActive(pathname, href);
            return (
              <Link key={href} href={href} aria-current={active ? 'page' : undefined}
                className={cn('flex h-10 items-center gap-3 rounded-lg px-3 text-sm transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                  active ? 'bg-accent font-medium text-accent-foreground' : 'text-muted-foreground hover:bg-muted hover:text-foreground')}>
                <Icon className="h-[18px] w-[18px] flex-none" aria-hidden="true" />{label}
              </Link>
            );
          })}
        </nav>
        <div className="mt-auto"><AccountMenu user={user} onLogout={handleLogout} /></div>
      </aside>

      {/* Mobile: a slim top bar and a bottom tab bar with the same three destinations. */}
      <header className="fixed inset-x-0 top-0 z-30 flex h-14 items-center justify-between border-b border-border bg-card/95 px-4 backdrop-blur lg:hidden">
        <Brand />
        <div className="w-44"><AccountMenu user={user} onLogout={handleLogout} /></div>
      </header>
      <nav aria-label="Primary" className="fixed inset-x-0 bottom-0 z-30 grid h-16 grid-cols-3 border-t border-border bg-card pb-[env(safe-area-inset-bottom)] lg:hidden">
        {items.map(({ label, href, icon: Icon }) => {
          const active = isActive(pathname, href);
          return (
            <Link key={href} href={href} aria-current={active ? 'page' : undefined}
              className={cn('flex flex-col items-center justify-center gap-1 text-[11px] font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring',
                active ? 'text-primary' : 'text-muted-foreground')}>
              <Icon className="h-5 w-5" aria-hidden="true" />{label}
            </Link>
          );
        })}
      </nav>

      <main id="main-content" tabIndex={-1}
        className="h-dvh min-w-0 overflow-y-auto pb-16 pt-14 focus:outline-none lg:pb-0 lg:pl-56 lg:pt-0">
        {children}
      </main>
    </div>
  );
}
