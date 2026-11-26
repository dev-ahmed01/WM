import { Bot, History, LifeBuoy, Library, MessagesSquare, Users, LayoutDashboard, ShieldAlert, BarChart3 } from 'lucide-react';
import type { ComponentType } from 'react';

export type Role = 'employee' | 'admin' | 'manager';

export interface NavItem {
  label: string;
  href: string;
  icon: ComponentType<{ className?: string }>;
}

/** Three destinations per role, no more. Everything else lives inside these pages or the account menu. */
export const NAV: Record<Role, NavItem[]> = {
  employee: [
    { label: 'Assistant', href: '/copilot', icon: Bot },
    { label: 'History', href: '/copilot/history', icon: History },
    { label: 'Escalations', href: '/escalations', icon: LifeBuoy },
  ],
  admin: [
    { label: 'Knowledge Studio', href: '/knowledge-studio', icon: Library },
    { label: 'Conversations', href: '/conversations', icon: MessagesSquare },
    { label: 'Employees', href: '/employees', icon: Users },
  ],
  manager: [
    { label: 'Overview', href: '/control-room', icon: LayoutDashboard },
    { label: 'Escalations', href: '/escalation-centre', icon: ShieldAlert },
    { label: 'Analytics', href: '/intelligence-hub', icon: BarChart3 },
  ],
};

export const LANDING: Record<Role, string> = {
  employee: '/copilot',
  admin: '/knowledge-studio',
  manager: '/control-room',
};

/**
 * Client-side routing guard so a role never lands on another role's page by typing a URL. This is a convenience:
 * every API behind these pages enforces the role again on the server and in the database.
 */
const ALLOWED: Record<Role, string[]> = {
  employee: ['/copilot', '/escalations', '/work'],
  admin: ['/knowledge-studio', '/conversations', '/employees', '/escalation-centre', '/procedure-studio', '/work/exceptions', '/pilot', '/account'],
  manager: ['/control-room', '/escalation-centre', '/intelligence-hub', '/approvals', '/work', '/handover', '/pilot', '/account'],
};

export function isAllowedPath(role: Role, pathname: string): boolean {
  return ALLOWED[role].some((prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`));
}

export function isActive(pathname: string, href: string): boolean {
  if (href === '/copilot') return pathname === '/copilot';
  return pathname === href || pathname.startsWith(`${href}/`);
}
