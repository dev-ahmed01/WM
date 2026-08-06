'use client';

import React, { useEffect, useState } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import Link from 'next/link';
import { getUserClaims, UserClaims } from '@/lib/auth';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Button } from '@/components/ui/button';
import {
  BookOpen,
  BarChart3,
  Bot,
  History,
  LogOut,
  User,
  ShieldAlert,
  Building2,
  ChevronDown,
} from 'lucide-react';

interface NavItem {
  label: string;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
  roles: Array<'admin' | 'manager' | 'employee'>;
}

const NAV_ITEMS: NavItem[] = [
  {
    label: 'Knowledge Studio',
    href: '/knowledge-studio',
    icon: BookOpen,
    roles: ['admin'],
  },
  {
    label: 'Intelligence Hub',
    href: '/intelligence-hub',
    icon: BarChart3,
    roles: ['manager'],
  },
  {
    label: 'Copilot',
    href: '/copilot',
    icon: Bot,
    roles: ['admin', 'manager', 'employee'],
  },
  {
    label: 'Session History',
    href: '/copilot/history',
    icon: History,
    roles: ['admin', 'manager', 'employee'],
  },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<UserClaims | null>(null);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    const claims = getUserClaims();
    setUser(claims);
  }, [pathname]);

  // Don't render shell header on auth / login pages
  if (pathname === '/login' || pathname.startsWith('/login/')) {
    return <>{children}</>;
  }

  const handleLogout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('refresh_token');
    setUser(null);
    router.push('/login');
  };

  const userRole = user?.role || 'employee';
  const visibleNavItems = NAV_ITEMS.filter((item) => item.roles.includes(userRole));

  return (
    <div className="min-h-screen flex flex-col bg-slate-50">
      {/* Top Shared Navigation Header */}
      <header className="sticky top-0 z-40 w-full border-b border-slate-200 bg-white/95 backdrop-blur shadow-sm">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
          {/* Brand & Logo */}
          <div className="flex items-center gap-8">
            <Link href="/" className="flex items-center gap-2 text-blue-600 font-bold text-lg tracking-tight">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-600 text-white font-black text-sm">
                WM
              </div>
              <span className="text-gray-900">WorkMate</span>
              <span className="text-blue-600 font-semibold">AI</span>
            </Link>

            {/* Navigation Links */}
            <nav className="hidden md:flex items-center gap-1">
              {visibleNavItems.map((item) => {
                const Icon = item.icon;
                const isActive = pathname === item.href || (item.href !== '/' && pathname.startsWith(item.href) && item.href !== '/copilot');
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={`flex items-center gap-2 px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                      isActive
                        ? 'bg-blue-50 text-blue-700 font-semibold'
                        : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
                    }`}
                  >
                    <Icon className="h-4 w-4" />
                    <span>{item.label}</span>
                  </Link>
                );
              })}
            </nav>
          </div>

          {/* User Claims & Profile Dropdown */}
          <div className="flex items-center gap-3">
            {mounted && user ? (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" className="flex items-center gap-2 px-3 py-1.5 h-auto text-left">
                    <div className="flex h-8 w-8 items-center justify-center rounded-full bg-slate-200 text-slate-700 font-bold text-xs">
                      {user.sub.charAt(0).toUpperCase()}
                    </div>
                    <div className="hidden sm:flex flex-col items-start text-xs">
                      <span className="font-semibold text-slate-800">{user.sub}</span>
                      <span className="text-slate-500 capitalize">{user.role}</span>
                    </div>
                    <ChevronDown className="h-3.5 w-3.5 text-slate-400" />
                  </Button>
                </DropdownMenuTrigger>

                <DropdownMenuContent align="end" className="w-56">
                  <DropdownMenuLabel className="font-normal">
                    <div className="flex flex-col space-y-1">
                      <p className="text-sm font-semibold leading-none text-slate-900">{user.sub}</p>
                      <div className="flex items-center gap-1 text-xs text-slate-500 mt-1">
                        <ShieldAlert className="h-3 w-3 text-blue-600" />
                        <span className="capitalize font-medium text-blue-700">{user.role}</span>
                        <span>•</span>
                        <Building2 className="h-3 w-3" />
                        <span>{user.department_id || 'GENERAL'}</span>
                      </div>
                    </div>
                  </DropdownMenuLabel>
                  <DropdownMenuSeparator />

                  <DropdownMenuItem onClick={handleLogout} className="text-red-600 focus:bg-red-50 focus:text-red-700">
                    <LogOut className="mr-2 h-4 w-4" />
                    <span>Log Out</span>
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            ) : (
              <Link href="/login">
                <Button size="sm" variant="default">
                  Sign In
                </Button>
              </Link>
            )}
          </div>
        </div>
      </header>

      {/* Main Content Body */}
      <main className="flex-1">{children}</main>
    </div>
  );
}
