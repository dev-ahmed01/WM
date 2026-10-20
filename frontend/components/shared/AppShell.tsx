'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import {
  Activity, BarChart3, BookOpenText, Bot, Building2, ChevronDown,
  ClipboardCheck, ClipboardList, History, LayoutDashboard, LogOut, AlertTriangle,
  Menu, Search, ShieldCheck, X,
} from 'lucide-react';
import { loadUserClaims, getUserClaims, clearCachedUser, type UserClaims } from '@/lib/auth';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { cn } from '@/lib/utils';
import { LoadingState } from '@/components/shared/LoadingState';

interface NavItem {
  label: string;
  description: string;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
  roles: Array<'admin' | 'manager' | 'employee'>;
}

const NAV_ITEMS: NavItem[] = [
  { label: 'My work', description: 'Your assigned queue', href: '/workspace', icon: ClipboardList, roles: ['admin','manager','employee'] },
  { label: 'Control room', description: 'Department overview', href: '/control-room', icon: LayoutDashboard, roles: ['admin','manager'] },
  { label: 'SOP guidance', description: 'Contextual AI assistance', href: '/copilot', icon: Bot, roles: ['admin','manager','employee'] },
  { label: 'Shift handover', description: 'Transfer open context', href: '/copilot/handover', icon: ClipboardCheck, roles: ['admin','manager','employee'] },
  { label: 'Approved sources', description: 'Verified documents', href: '/copilot/sources', icon: Search, roles: ['admin','manager','employee'] },
  { label: 'Session history', description: 'Previous guidance', href: '/copilot/history', icon: History, roles: ['admin','manager','employee'] },
  { label: 'Procedure Studio', description: 'Manage governed SOPs', href: '/procedure-studio', icon: BookOpenText, roles: ['admin'] },
  { label: 'Task exceptions', description: 'Blocked work and reviews', href: '/work/exceptions', icon: AlertTriangle, roles: ['admin','manager'] },
  { label: 'Shift reviews', description: 'Department handovers', href: '/handover/review', icon: ClipboardCheck, roles: ['admin','manager'] },
  { label: 'Intelligence', description: 'Actual operational metrics', href: '/intelligence-hub', icon: BarChart3, roles: ['admin','manager'] },
  { label: 'Pilot evaluation', description: 'Private quality signals', href: '/pilot', icon: Activity, roles: ['admin','manager'] },
];

function isActiveRoute(pathname: string, href: string) {
  if (href === '/copilot') return pathname === href;
  if (href === '/knowledge-studio') return !pathname.startsWith('/knowledge-studio/references') && (pathname === href || pathname.startsWith(`${href}/`));
  return pathname === href || pathname.startsWith(`${href}/`);
}

function Brand() {
  return (
    <Link href="/workspace" className="group flex items-center gap-3 rounded-xl focus-visible:outline-offset-4" aria-label="WorkMate home">
      <span className="grid h-10 w-10 place-items-center rounded-xl bg-[#b9edcf] text-sm font-extrabold tracking-tight text-[#0d3725] shadow-sm transition group-hover:bg-white">
        WM
      </span>
      <span>
        <span className="block text-base font-bold tracking-tight text-white">WorkMate</span>
        <span className="block text-[10px] font-medium uppercase tracking-[0.13em] text-[#8cb39c]">Frontline execution</span>
      </span>
    </Link>
  );
}

function UserMenu({ user, onLogout, compact = false }: { user: UserClaims; onLogout: () => void; compact?: boolean }) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          className={cn(
            'flex w-full items-center gap-3 rounded-xl border border-border bg-white p-2.5 text-left transition hover:bg-emerald-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500',
            compact && 'border-border bg-white hover:bg-muted',
          )}
        >
          <span className={cn('grid h-9 w-9 flex-none place-items-center rounded-lg bg-emerald-100 text-xs font-bold text-emerald-800', compact && 'bg-emerald-100 text-emerald-800')}>
            {user.sub.slice(0, 1).toUpperCase()}
          </span>
          <span className={cn('min-w-0 flex-1', compact && 'hidden sm:block')}>
            <span className={cn('block truncate text-xs font-semibold text-foreground')}>{user.sub}</span>
            <span className={cn('mt-0.5 block truncate text-[11px] capitalize text-muted-foreground')}>{user.role} · {user.department_id}</span>
          </span>
          <ChevronDown className={cn('h-4 w-4 flex-none text-slate-500', compact && 'hidden sm:block')} aria-hidden="true" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" side="top" className="w-64 rounded-xl border-border p-1.5 shadow-lift">
        <DropdownMenuLabel className="p-3 font-normal">
          <p className="truncate text-sm font-semibold text-foreground">{user.sub}</p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-1 text-[10px] font-semibold capitalize text-emerald-800"><ShieldCheck className="h-3 w-3" />{user.role}</span>
            <span className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-1 text-[10px] font-semibold text-muted-foreground"><Building2 className="h-3 w-3" />{user.department_id}</span>
          </div>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={onLogout} className="rounded-lg px-3 py-2 text-red-600 focus:bg-red-50 focus:text-red-700">
          <LogOut className="mr-2 h-4 w-4" />
          Log out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function SidebarContent({ pathname, user, onNavigate, onLogout }: { pathname: string; user: UserClaims | null; onNavigate?: () => void; onLogout: () => void }) {
  const role = user?.role || 'employee';
  const visibleItems = NAV_ITEMS.filter((item) => item.roles.includes(role));
  const sections = [
    { title: 'Execute', items: visibleItems.filter(item => ['/workspace','/control-room','/work/exceptions','/copilot','/copilot/handover'].includes(item.href)) },
    { title: 'Knowledge', items: visibleItems.filter(item => ['/copilot/sources','/copilot/history','/procedure-studio'].includes(item.href)) },
    { title: 'Supervise', items: visibleItems.filter(item => ['/handover/review','/intelligence-hub','/pilot'].includes(item.href)) },
  ];

  return (
    <div className="flex h-full flex-col bg-[#102b23] px-3 py-5 text-white">
      <div className="px-3 pb-8 pt-1"><Brand /></div>
      <nav className="flex-1 space-y-7 overflow-y-auto px-1" aria-label="Primary navigation">
        {sections.filter((section) => section.items.length > 0).map((section) => (
          <div key={section.title}>
            <p className="mb-2 px-3 text-[10px] font-bold uppercase tracking-[0.14em] text-[#77a18a]">{section.title}</p>
            <div className="space-y-1">
              {section.items.map((item) => {
                const Icon = item.icon;
                const active = isActiveRoute(pathname, item.href);
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    onClick={onNavigate}
                    aria-current={active ? 'page' : undefined}
                    className={cn(
                      'group flex min-h-12 items-center gap-3 rounded-xl border px-3 py-2.5 transition focus-visible:outline-offset-2',
                      active
                        ? 'border-[#7bd4a4]/20 bg-[#28533c] text-white'
                        : 'border-transparent text-[#b4c7b9] hover:border-[#4c765b] hover:bg-[#1b4130] hover:text-white',
                    )}
                  >
                    <Icon className={cn('h-[18px] w-[18px] shrink-0', active ? 'text-[#b7efd1]' : 'text-[#83a591]')} aria-hidden="true" />
                    <span className="min-w-0">
                      <span className="block text-[13px] font-semibold">{item.label}</span>
                      <span className="block truncate text-[11px] text-[#87a592]">{item.description}</span>
                    </span>
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
      </nav>
      <div className="space-y-3 border-t border-[#2d4c3a] px-1 pt-4">
        <div className="flex items-center gap-2 px-3 py-2 text-[11px] font-semibold text-[#b0d9bc]"><ShieldCheck className="h-4 w-4" />Governed procedures</div>
        {user ? <UserMenu user={user} onLogout={onLogout} /> : null}
      </div>
    </div>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  // Do not render an employee sidebar or Sign in action while an admin/manager
  // session is still loading. Keep cached identity visible between modules.
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
  if (!user) return <div className="min-h-screen grid place-items-center bg-[#f8faf8]"><LoadingState label="Opening workspace" /></div>;

  const handleLogout = () => {
    void fetch('/api/session/logout', {
      method: 'POST', credentials: 'same-origin',
    }).finally(() => {
      clearCachedUser();
      setUser(null);
      router.replace('/login');
    });
  };

  const activeItem = NAV_ITEMS.find((item) => isActiveRoute(pathname, item.href));

  return (
    <div className="min-h-screen bg-background">
      <aside className="fixed inset-y-0 left-0 z-40 hidden w-64 border-r border-[#244b35] lg:block">
        <SidebarContent pathname={pathname} user={user} onLogout={handleLogout} />
      </aside>

      {mobileOpen ? (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button className="absolute inset-0 bg-slate-950/55 backdrop-blur-sm" aria-label="Close navigation" onClick={() => setMobileOpen(false)} />
          <aside className="relative h-full w-[min(19rem,88vw)] shadow-2xl">
            <button type="button" className="absolute right-3 top-3 z-10 grid h-9 w-9 place-items-center rounded-lg text-slate-600 hover:bg-emerald-100 hover:text-emerald-900" onClick={() => setMobileOpen(false)} aria-label="Close navigation">
              <X className="h-5 w-5" />
            </button>
            <SidebarContent pathname={pathname} user={user} onNavigate={() => setMobileOpen(false)} onLogout={handleLogout} />
          </aside>
        </div>
      ) : null}

      <div className="min-h-screen lg:pl-64">
        <header className="sticky top-0 z-30 flex h-16 items-center justify-between border-b border-border/80 bg-white/90 px-4 backdrop-blur-xl sm:px-6 lg:px-8">
          <div className="flex items-center gap-3">
            <Button variant="ghost" size="icon" className="lg:hidden" onClick={() => setMobileOpen(true)} aria-label="Open navigation">
              <Menu className="h-5 w-5" />
            </Button>
            <div>
              <p className="text-xs font-semibold text-foreground">{activeItem?.label || 'Operational workspace'}</p>
              <p className="hidden text-[10px] text-muted-foreground sm:block">{activeItem?.description || 'WorkMate verified operations'}</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className="hidden items-center gap-2 rounded-full border border-emerald-100 bg-emerald-50 px-3 py-1.5 text-[11px] font-medium text-emerald-800 sm:inline-flex">
              <ShieldCheck className="h-3.5 w-3.5" /> Verified context
            </span>
            {user ? <div className="w-14 sm:w-56"><UserMenu user={user} onLogout={handleLogout} compact /></div> : <Button asChild size="sm"><Link href="/login">Sign in</Link></Button>}
          </div>
        </header>
        <main className="min-w-0">{children}</main>
      </div>
    </div>
  );
}
