'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import {
  BarChart3, BookOpenText, Bot, ChevronDown, ClipboardList, LayoutDashboard,
  LogOut, Menu, ShieldCheck, X,
} from 'lucide-react';
import { loadUserClaims, getUserClaims, clearCachedUser, type UserClaims } from '@/lib/auth';
import { LoadingState } from '@/components/shared/LoadingState';
import { cn } from '@/lib/utils';
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';

type Role = 'admin' | 'manager' | 'employee';
type Area = 'work' | 'operations' | 'assistant' | 'procedures' | 'insights';
type NavItem = {
  area: Area; label: string; href: string;
  icon: React.ComponentType<{ className?: string }>; roles: Role[];
};

const NAV: NavItem[] = [
  { area: 'work', label: 'My work', href: '/workspace', icon: ClipboardList, roles: ['admin', 'manager', 'employee'] },
  { area: 'operations', label: 'Operations', href: '/control-room', icon: LayoutDashboard, roles: ['admin', 'manager'] },
  { area: 'assistant', label: 'WorkMate Assist', href: '/copilot', icon: Bot, roles: ['admin', 'manager', 'employee'] },
  { area: 'procedures', label: 'Procedures', href: '/procedure-studio', icon: BookOpenText, roles: ['admin'] },
  { area: 'insights', label: 'Insights', href: '/intelligence-hub', icon: BarChart3, roles: ['admin', 'manager'] },
];

function getArea(pathname: string): Area {
  if (pathname === '/copilot/handover') return 'work';
  if (pathname.startsWith('/work/exceptions') || pathname.startsWith('/work/integrations') || pathname.startsWith('/handover/review') || pathname.startsWith('/control-room')) return 'operations';
  if (pathname.startsWith('/procedure-studio') || pathname.startsWith('/knowledge-studio')) return 'procedures';
  if (pathname.startsWith('/intelligence-hub') || pathname.startsWith('/pilot')) return 'insights';
  if (pathname.startsWith('/copilot')) return 'assistant';
  return 'work';
}

type Tab = { label: string; href: string; roles: Role[] };
const TABS: Record<Area, Tab[]> = {
  work: [
    { label: 'Queue', href: '/workspace', roles: ['admin', 'manager', 'employee'] },
    { label: 'Shift handover', href: '/copilot/handover', roles: ['admin', 'manager', 'employee'] },
  ],
  operations: [
    { label: 'Control room', href: '/control-room', roles: ['admin', 'manager'] },
    { label: 'Exceptions', href: '/work/exceptions', roles: ['admin', 'manager'] },
    { label: 'Shift reviews', href: '/handover/review', roles: ['admin', 'manager'] },
    { label: 'Integrations', href: '/work/integrations', roles: ['admin', 'manager'] },
  ],
  assistant: [
    { label: 'Ask WorkMate', href: '/copilot', roles: ['admin', 'manager', 'employee'] },
    { label: 'Sources', href: '/copilot/sources', roles: ['admin', 'manager', 'employee'] },
    { label: 'History', href: '/copilot/history', roles: ['admin', 'manager', 'employee'] },
  ],
  procedures: [
    { label: 'Overview', href: '/procedure-studio', roles: ['admin'] },
    { label: 'Drafts', href: '/procedure-studio/drafts', roles: ['admin'] },
    { label: 'Published SOPs', href: '/knowledge-studio', roles: ['admin'] },
    { label: 'References', href: '/knowledge-studio/references', roles: ['admin'] },
  ],
  insights: [
    { label: 'Metrics', href: '/intelligence-hub', roles: ['admin', 'manager'] },
    { label: 'Pilot', href: '/pilot', roles: ['admin', 'manager'] },
  ],
};

function tabActive(path: string, tab: Tab) {
  if (tab.href === '/copilot' || tab.href === '/procedure-studio' || tab.href === '/knowledge-studio') return path === tab.href;
  return path === tab.href || path.startsWith(tab.href + '/');
}

function UserMenu({ user, logout }: { user: UserClaims; logout: () => void }) {
  const readable = user.sub.startsWith('usr_') ? user.role + ' account' : user.sub;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button type="button" className="flex w-full min-w-0 items-center gap-2.5 rounded-xl border border-white/15 bg-white/10 px-3 py-3 text-left text-white hover:bg-white/15 focus-visible:outline-offset-2">
          <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-[#b9edcf] text-sm font-bold text-[#123728]">{user.role.slice(0, 1).toUpperCase()}</span>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm font-semibold capitalize">{readable}</span>
            <span className="block truncate text-xs text-[#a6c5b3]">{user.department_id}</span>
          </span>
          <ChevronDown className="h-4 w-4 text-[#a6c5b3]" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" side="top" className="w-56">
        <DropdownMenuItem onClick={logout} className="cursor-pointer text-red-700">
          <LogOut className="mr-2 h-4 w-4" /> Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function Sidebar({ pathname, user, close, logout }: { pathname: string; user: UserClaims; close?: () => void; logout: () => void }) {
  const area = getArea(pathname);
  return (
    <div className="flex h-full min-h-0 flex-col bg-[#102b23] px-4 py-6 text-white">
      <Link href="/workspace" onClick={close} className="flex items-center gap-3 px-2" aria-label="WorkMate home">
        <span className="grid h-11 w-11 place-items-center rounded-xl bg-[#b9edcf] text-base font-extrabold text-[#102b23]">WM</span>
        <span className="font-heading text-xl font-bold tracking-tight">WorkMate</span>
      </Link>
      <nav aria-label="Primary navigation" className="mt-12 flex min-h-0 flex-1 flex-col gap-1.5">
        {NAV.filter(item => item.roles.includes(user.role)).map(item => {
          const Icon = item.icon;
          const active = area === item.area;
          return (
            <Link key={item.area} href={item.href} onClick={close} aria-current={active ? 'page' : undefined}
              className={cn('flex min-h-12 items-center gap-3 rounded-xl px-4 py-3 text-sm font-semibold transition-colors',
                active ? 'bg-[#28533c] text-white' : 'text-[#b5cbbd] hover:bg-white/10 hover:text-white')}>
              <Icon className="h-[18px] w-[18px] shrink-0" />
              {item.label}
            </Link>
          );
        })}
      </nav>
      <div className="border-t border-white/10 pt-4">
        <UserMenu user={user} logout={logout} />
      </div>
    </div>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<UserClaims | null>(() => getUserClaims());
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    if (pathname === '/login' || pathname.startsWith('/login/')) return;
    void loadUserClaims().then(profile => {
      if (cancelled) return;
      setUser(profile);
      if (!profile) router.replace('/login');
    });
    setMobileOpen(false);
    return () => { cancelled = true; };
  }, [pathname, router]);

  if (pathname === '/login' || pathname.startsWith('/login/')) return <>{children}</>;
  if (!user) return <div className="grid min-h-screen place-items-center"><LoadingState label="Opening WorkMate" /></div>;

  const logout = () => {
    void fetch('/api/session/logout', { method: 'POST', credentials: 'same-origin' }).finally(() => {
      clearCachedUser();
      setUser(null);
      router.replace('/login');
    });
  };
  const area = getArea(pathname);
  const visibleTabs = TABS[area].filter(tab => tab.roles.includes(user.role));
  const label = NAV.find(item => item.area === area)?.label ?? 'WorkMate';
  return (
    <div className="min-h-screen bg-background">
      <aside className="fixed inset-y-0 left-0 z-40 hidden w-60 lg:block">
        <Sidebar pathname={pathname} user={user} logout={logout} />
      </aside>
      {mobileOpen ? (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button className="absolute inset-0 bg-slate-950/60" onClick={() => setMobileOpen(false)} aria-label="Close navigation" />
          <aside className="relative h-full w-[min(19rem,85vw)]">
            <button type="button" className="absolute right-3 top-3 z-10 rounded-lg p-2 text-white" onClick={() => setMobileOpen(false)} aria-label="Close navigation"><X className="h-5 w-5" /></button>
            <Sidebar pathname={pathname} user={user} close={() => setMobileOpen(false)} logout={logout} />
          </aside>
        </div>
      ) : null}
      <div className="min-h-screen lg:pl-60">
        <header className="sticky top-0 z-30 border-b border-border bg-white/95 backdrop-blur-xl">
          <div className="flex h-16 items-center gap-3 px-5 sm:px-8">
            <button type="button" className="rounded-lg p-2 lg:hidden" onClick={() => setMobileOpen(true)} aria-label="Open navigation"><Menu className="h-5 w-5" /></button>
            <span className="font-heading text-base font-bold">{label}</span>
            <span className="ml-auto hidden items-center gap-1.5 text-xs text-muted-foreground sm:flex"><ShieldCheck className="h-4 w-4 text-emerald-700" /> Controlled workflows</span>
          </div>
          {visibleTabs.length > 1 ? (
            <nav className="flex min-h-11 items-center gap-1 overflow-x-auto px-5 sm:px-8" aria-label={label + ' views'}>
              {visibleTabs.map(tab => (
                <Link key={tab.href} href={tab.href} aria-current={tabActive(pathname, tab) ? 'page' : undefined}
                  className={cn('whitespace-nowrap border-b-2 px-3 py-2.5 text-xs font-semibold transition-colors',
                    tabActive(pathname, tab) ? 'border-emerald-700 text-emerald-900' : 'border-transparent text-muted-foreground hover:text-foreground')}>
                  {tab.label}
                </Link>
              ))}
            </nav>
          ) : null}
        </header>
        <main className="min-w-0">{children}</main>
      </div>
    </div>
  );
}
