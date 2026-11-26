'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { Copy, KeyRound, Plus, Search, UserCheck, UserX } from 'lucide-react';
import { useRequireRole } from '@/lib/auth';
import { apiClient, ApiError } from '@/lib/api-client';
import { PageHeader } from '@/components/shared/PageHeader';
import { LoadingState } from '@/components/shared/LoadingState';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';

interface Employee {
  id: string; email: string; full_name: string | null; status: string; department_id: string;
  warehouse_id: string | null; supervisor_id: string | null; preferred_language: string;
  job_profile: string | null; role: string; is_demo: boolean;
}
interface OrgOverview {
  organization: { id: string; name: string; is_demo: boolean };
  warehouses: { id: string; code: string; name: string }[];
  departments: { id: string; code: string; name: string }[];
  job_profiles: { code: string; name_en: string; name_hi: string }[];
}
interface IssuedToken { who: string; kind: string; token: string; hours: number }

const STATUS_VARIANT: Record<string, 'default' | 'warning' | 'neutral'> = { active: 'default', invited: 'warning', inactive: 'neutral' };

export default function EmployeesPage() {
  const { loading } = useRequireRole(['admin']);
  const [org, setOrg] = useState<OrgOverview | null>(null);
  const [rows, setRows] = useState<Employee[]>([]);
  const [query, setQuery] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [issued, setIssued] = useState<IssuedToken | null>(null);
  const [copied, setCopied] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ email: '', full_name: '', department_id: '', role: 'employee', job_profile: '', warehouse_id: '', supervisor_id: '' });

  const load = useCallback(async () => {
    setError('');
    try {
      const [overview, list] = await Promise.all([
        apiClient<OrgOverview>('/admin/org'),
        apiClient<Employee[]>(`/admin/employees?q=${encodeURIComponent(query)}&limit=200`),
      ]);
      setOrg(overview); setRows(list);
      setForm((f) => ({ ...f, department_id: f.department_id || overview.departments[0]?.id || '' }));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not load employees. Check your connection and retry.');
    }
  }, [query]);

  useEffect(() => { if (!loading) void load(); }, [loading, load]);

  const supervisors = rows.filter((r) => r.role !== 'employee' && r.status === 'active');
  const inviteLink = (token: string) => `${window.location.origin}/accept-invite?token=${encodeURIComponent(token)}`;

  async function act<T>(fn: () => Promise<T>) {
    setBusy(true); setError('');
    try { return await fn(); }
    catch (e) { setError(e instanceof ApiError ? e.message : 'The action failed. Nothing was changed.'); return null; }
    finally { setBusy(false); }
  }

  async function createEmployee(event: React.FormEvent) {
    event.preventDefault();
    const body: Record<string, string> = { email: form.email.trim(), full_name: form.full_name.trim(), department_id: form.department_id, role: form.role };
    if (form.job_profile) body.job_profile = form.job_profile;
    if (form.warehouse_id) body.warehouse_id = form.warehouse_id;
    if (form.supervisor_id) body.supervisor_id = form.supervisor_id;
    const res = await act(() => apiClient<{ employee: Employee; one_time_token: string; expires_in_hours: number }>('/admin/employees', { method: 'POST', body: JSON.stringify(body) }));
    if (res) {
      setIssued({ who: res.employee.email, kind: 'Invitation', token: res.one_time_token, hours: res.expires_in_hours });
      setShowForm(false); setForm((f) => ({ ...f, email: '', full_name: '' })); void load();
    }
  }

  async function setActive(emp: Employee, active: boolean) {
    if (await act(() => apiClient(`/admin/employees/${emp.id}/status`, { method: 'POST', body: JSON.stringify({ active }) }))) void load();
  }

  async function recovery(emp: Employee) {
    const res = await act(() => apiClient<{ one_time_token: string; expires_in_hours: number }>(`/admin/employees/${emp.id}/recovery-token`, { method: 'POST' }));
    if (res) setIssued({ who: emp.email, kind: 'Password recovery', token: res.one_time_token, hours: res.expires_in_hours });
  }

  async function copy(text: string) {
    try { await navigator.clipboard.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 2000); }
    catch { setError('Could not copy automatically. Select the link and copy it manually.'); }
  }

  if (loading) return <LoadingState />;

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <PageHeader
        eyebrow={org?.organization.name ?? 'Organization'}
        title="Employees"
        description="Invite employees, assign their warehouse and job profile, and deactivate accounts. You only see people in your own organization."
        action={<Button onClick={() => setShowForm((v) => !v)}><Plus className="h-4 w-4" />Add employee</Button>}
      />

      {error ? <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div> : null}

      {issued ? (
        <Card className="border-amber-200 bg-amber-50/60">
          <CardHeader>
            <CardTitle>{issued.kind} link for {issued.who}</CardTitle>
            <CardDescription>WorkMate does not send email. Give this link to the employee yourself. It works once, expires in {issued.hours} hour{issued.hours === 1 ? '' : 's'}, and will not be shown again.</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-3 sm:flex-row sm:items-center">
            <code className="min-w-0 flex-1 break-all rounded-lg border bg-white p-2.5 text-xs">{inviteLink(issued.token)}</code>
            <Button variant="outline" onClick={() => copy(inviteLink(issued.token))}><Copy className="h-4 w-4" />{copied ? 'Copied' : 'Copy link'}</Button>
            <Button variant="ghost" onClick={() => setIssued(null)}>Done</Button>
          </CardContent>
        </Card>
      ) : null}

      {showForm && org ? (
        <Card>
          <CardHeader><CardTitle>New employee</CardTitle><CardDescription>The account stays in “invited” status until they set a password.</CardDescription></CardHeader>
          <CardContent>
            <form onSubmit={createEmployee} className="grid gap-4 sm:grid-cols-2">
              <label className="block"><span className="wm-label">Full name</span><input required className="wm-input" value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} /></label>
              <label className="block"><span className="wm-label">Email</span><input required type="email" className="wm-input" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></label>
              <label className="block"><span className="wm-label">Role</span>
                <select className="wm-input" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}><option value="employee">Employee</option><option value="manager">Manager</option></select></label>
              {org.departments.length > 1 ? (
              <label className="block"><span className="wm-label">Department</span>
                <select className="wm-input" value={form.department_id} onChange={(e) => setForm({ ...form, department_id: e.target.value })}>
                  {org.departments.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}</select></label>
              ) : null}
              <details className="sm:col-span-2 rounded-xl border border-border p-3">
                <summary className="cursor-pointer text-sm font-medium text-muted-foreground">More details (optional)</summary>
                <div className="mt-3 grid gap-4 sm:grid-cols-2">
              <label className="block"><span className="wm-label">Job profile</span>
                <select className="wm-input" value={form.job_profile} onChange={(e) => setForm({ ...form, job_profile: e.target.value })}>
                  <option value="">Not set</option>{org.job_profiles.map((j) => <option key={j.code} value={j.code}>{j.name_en}</option>)}</select></label>
              <label className="block"><span className="wm-label">Warehouse</span>
                <select className="wm-input" value={form.warehouse_id} onChange={(e) => setForm({ ...form, warehouse_id: e.target.value })}>
                  <option value="">Not set</option>{org.warehouses.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}</select></label>
              <label className="block"><span className="wm-label">Supervisor</span>
                <select className="wm-input" value={form.supervisor_id} onChange={(e) => setForm({ ...form, supervisor_id: e.target.value })}>
                  <option value="">Not set</option>{supervisors.map((s) => <option key={s.id} value={s.id}>{s.full_name ?? s.email}</option>)}</select></label>
                </div>
              </details>
              <div className="flex gap-3 sm:col-span-2"><Button type="submit" disabled={busy}>{busy ? 'Creating…' : 'Create and get invite link'}</Button><Button type="button" variant="ghost" onClick={() => setShowForm(false)}>Cancel</Button></div>
            </form>
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardHeader className="gap-3 sm:flex-row sm:items-center sm:justify-between">
          <CardTitle>{rows.length} {rows.length === 1 ? 'person' : 'people'}</CardTitle>
          <label className="relative block sm:w-72"><span className="sr-only">Search employees</span>
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <input className="wm-input pl-9" placeholder="Search name or email" value={query} onChange={(e) => setQuery(e.target.value)} /></label>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          {rows.length === 0 ? (
            <div className="grid min-h-32 place-items-center rounded-xl border border-dashed bg-muted/25 p-5 text-center text-sm text-muted-foreground">{query ? 'No one matches that search.' : 'No employees yet. Use “Add employee” to invite the first person.'}</div>
          ) : (
            <table className="w-full min-w-[720px] text-left text-sm">
              <thead className="text-[11px] uppercase tracking-wide text-muted-foreground"><tr><th className="py-2 pr-3">Name</th><th className="pr-3">Role</th><th className="pr-3">Job profile</th><th className="pr-3">Warehouse</th><th className="pr-3">Status</th><th className="text-right">Actions</th></tr></thead>
              <tbody className="divide-y">
                {rows.map((r) => (
                  <tr key={r.id}>
                    <td className="py-3 pr-3"><p className="font-semibold">{r.full_name ?? '—'}{r.is_demo ? <Badge variant="neutral" className="ml-2">demo</Badge> : null}</p><p className="text-xs text-muted-foreground">{r.email}</p></td>
                    <td className="pr-3 capitalize">{r.role}</td>
                    <td className="pr-3">{org?.job_profiles.find((j) => j.code === r.job_profile)?.name_en ?? '—'}</td>
                    <td className="pr-3">{org?.warehouses.find((w) => w.id === r.warehouse_id)?.code ?? '—'}</td>
                    <td className="pr-3"><Badge variant={STATUS_VARIANT[r.status] ?? 'neutral'}>{r.status}</Badge></td>
                    <td className="space-x-1 whitespace-nowrap text-right">
                      <Button size="sm" variant="ghost" disabled={busy || r.role === 'admin'} onClick={() => recovery(r)}><KeyRound className="h-3.5 w-3.5" />Reset link</Button>
                      {r.status === 'inactive'
                        ? <Button size="sm" variant="outline" disabled={busy} onClick={() => setActive(r, true)}><UserCheck className="h-3.5 w-3.5" />Activate</Button>
                        : <Button size="sm" variant="ghost" disabled={busy || r.role === 'admin'} onClick={() => setActive(r, false)}><UserX className="h-3.5 w-3.5" />Deactivate</Button>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
