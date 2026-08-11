'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import {
  BarChart3,
  BookOpenText,
  Bot,
  Building2,
  ChevronDown,
  History,
  LogOut,
  Menu,
  PanelLeftClose,
  ShieldCheck,
  Sparkles,
  X,
} from 'lucide-react';
import { getUserClaims, type UserClaims } from '@/lib/auth';
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

interface NavItem {
  label: string;
  description: string;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
  roles: Array<'admin' | 'manager' | 'employee'>;
}

const NAV_ITEMS: NavItem[] = [
  {
    label: 'Copilot',
    description: 'Live SOP guidance',
    href: '/copilot',
    icon: Bot,
    roles: ['admin', 'manager', 'employee'],
  },
  {
    label: 'Session history',
    description: 'Resume past work',
    href: '/copilot/history',
    icon: History,
    roles: ['admin', 'manager', 'employee'],
  },
  {
    label: 'Knowledge studio',
    description: 'Manage verified SOPs',
    href: '/knowledge-studio',
    icon: BookOpenText,
    roles: ['admin'],
  },
  {
    label: 'Intelligence hub',
    description: 'Operational insights',
    href: '/intelligence-hub',
    icon: BarChart3,
    roles: ['manager', 'admin'],
  },
];

function isActiveRoute(pathname: string, href: string) {
  if (href === '/copilot') return pathname === href;
  return pathname === href || pathname.startsWith(`${href}/`);
}

function Brand() {
  return (
    <Link href="/copilot" className="group flex items-center gap-3" aria-label="WorkMate home">
      <span className="grid h-10 w-10 place-items-center rounded-xl bg-emerald-400 text-sm font-black tracking-tight text-emerald-950 shadow-[0_8px_24px_rgba(52,211,153,0.2)] transition-transform group-hover:-translate-y-0.5">
        WM
      </span>
      <span>
        <span className="block text-[15px] font-semibold tracking-tight text-white">WorkMate</span>
        <span className="block text-[10px] font-semibold uppercase tracking-[0.17em] text-slate-500">Operations AI</span>
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
            'flex w-full items-center gap-3 rounded-xl border border-white/10 bg-white/[0.045] p-2.5 text-left transition hover:bg-white/[0.08] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400',
            compact && 'border-border bg-white hover:bg-muted',
          )}
        >
          <span className={cn('grid h-9 w-9 flex-none place-items-center rounded-lg bg-emerald-400/15 text-xs font-bold text-emerald-300', compact && 'bg-emerald-100 text-emerald-800')}>
            {user.sub.slice(0, 1).toUpperCase()}
          </span>
          <span className={cn('min-w-0 flex-1', compact && 'hidden sm:block')}>
            <span className={cn('block truncate text-xs font-semibold text-slate-100', compact && 'text-foreground')}>{user.sub}</span>
            <span className={cn('mt-0.5 block truncate text-[11px] capitalize text-slate-500', compact && 'text-muted-foreground')}>{user.role} · {user.department_id}</span>
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

  return (
    <div className="flex h-full flex-col bg-[#0b1713] px-3 py-4 text-slate-300">
      <div className="px-2 pb-7 pt-1"><Brand /></div>
      <div className="px-2 pb-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-600">Workspace</div>
      <nav className="space-y-1" aria-label="Primary navigation">
        {visibleItems.map((item) => {
          const Icon = item.icon;
          const active = isActiveRoute(pathname, item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              onClick={onNavigate}
              aria-current={active ? 'page' : undefined}
              className={cn(
                'group flex items-center gap-3 rounded-xl px-3 py-2.5 transition',
                active ? 'bg-white/[0.09] text-white shadow-sm' : 'text-slate-500 hover:bg-white/[0.045] hover:text-slate-200',
              )}
            >
              <span className={cn('grid h-8 w-8 place-items-center rounded-lg border border-white/[0.06] bg-white/[0.03]', active && 'border-emerald-400/20 bg-emerald-400/10 text-emerald-300')}>
                <Icon className="h-4 w-4" aria-hidden="true" />
              </span>
              <span className="min-w-0">
                <span className="block text-[13px] font-semibold">{item.label}</span>
                <span className={cn('block truncate text-[10px] text-slate-600', active && 'text-slate-400')}>{item.description}</span>
              </span>
            </Link>
          );
        })}
      </nav>
      <div className="mt-auto space-y-3 pt-5">
        <div className="mx-1 rounded-xl border border-emerald-400/10 bg-emerald-400/[0.055] p-3">
          <div className="flex items-center gap-2 text-[11px] font-semibold text-emerald-300"><Sparkles className="h-3.5 w-3.5" />Verified guidance</div>
          <p className="mt-1.5 text-[10px] leading-4 text-slate-500">Answers stay grounded in your published operational knowledge.</p>
        </div>
        {user ? <UserMenu user={user} onLogout={onLogout} /> : null}
      </div>
    </div>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<UserClaims | null>(null);
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    setUser(getUserClaims());
    setMobileOpen(false);
  }, [pathname]);

  if (pathname === '/login' || pathname.startsWith('/login/')) return <>{children}</>;

  const handleLogout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('refresh_token');
    setUser(null);
    router.push('/login');
  };

  const activeItem = NAV_ITEMS.find((item) => isActiveRoute(pathname, item.href));

  return (
    <div className="min-h-screen bg-background">
      <aside className="fixed inset-y-0 left-0 z-40 hidden w-64 border-r border-black/10 lg:block">
        <SidebarContent pathname={pathname} user={user} onLogout={handleLogout} />
      </aside>

      {mobileOpen ? (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button className="absolute inset-0 bg-slate-950/55 backdrop-blur-sm" aria-label="Close navigation" onClick={() => setMobileOpen(false)} />
          <aside className="relative h-full w-[min(19rem,88vw)] shadow-2xl">
            <button type="button" className="absolute right-3 top-3 z-10 grid h-9 w-9 place-items-center rounded-lg text-slate-500 hover:bg-white/10 hover:text-white" onClick={() => setMobileOpen(false)} aria-label="Close navigation">
              <X className="h-5 w-5" />
            </button>
            <SidebarContent pathname={pathname} user={user} onNavigate={() => setMobileOpen(false)} onLogout={handleLogout} />
          </aside>
        </div>
      ) : null}

      <div className="min-h-screen lg:pl-64">
        <header className="sticky top-0 z-30 flex h-16 items-center justify-between border-b border-border/80 bg-background/90 px-4 backdrop-blur-xl sm:px-6 lg:px-8">
          <div className="flex items-center gap-3">
            <Button variant="ghost" size="icon" className="lg:hidden" onClick={() => setMobileOpen(true)} aria-label="Open navigation">
              <Menu className="h-5 w-5" />
            </Button>
            <div className="hidden lg:grid h-8 w-8 place-items-center rounded-lg border bg-white text-muted-foreground">
              <PanelLeftClose className="h-4 w-4" />
            </div>
            <div>
              <p className="text-xs font-semibold text-foreground">{activeItem?.label || 'Operational workspace'}</p>
              <p className="hidden text-[10px] text-muted-foreground sm:block">{activeItem?.description || 'WorkMate verified operations'}</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className="hidden items-center gap-2 rounded-full border bg-white px-3 py-1.5 text-[11px] font-semibold text-muted-foreground sm:inline-flex">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 shadow-[0_0_0_3px_rgba(16,185,129,0.12)]" />Systems online
            </span>
            {user ? <div className="w-14 sm:w-56"><UserMenu user={user} onLogout={handleLogout} compact /></div> : <Button asChild size="sm"><Link href="/login">Sign in</Link></Button>}
          </div>
        </header>
        <main>{children}</main>
      </div>
    </div>
  );
}
