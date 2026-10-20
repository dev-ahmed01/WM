'use client';

import { useCallback, useEffect, useState } from 'react';
import {
  AlertTriangle, ArrowRight, Camera, CheckCircle2, ClipboardCheck,
  Clock3, FileCheck2, FileText, GitBranchPlus, LockKeyhole,
  PauseCircle, PlayCircle, RefreshCw, ShieldAlert, ShieldCheck,
} from 'lucide-react';
import { apiClient } from '@/lib/api-client';
import type {
  ExecutionPosition, PublishedProcedure, WorkEvent, WorkItem,
} from '@/lib/work-items';

type Staff = { id:string; label:string };

type Props = {
  item: WorkItem;
  canManage: boolean;
  isAssignee: boolean;
  onTaskChanged: () => void;
};

const ALLOWED_FILES = 2 * 1024 * 1024;

async function encodeFile(file: File): Promise<string> {
  if (file.size > ALLOWED_FILES) throw new Error('Each document or photo must be at most 2 MB.');
  const data = await new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ''));
    reader.onerror = () => reject(new Error('Could not read this evidence file.'));
    reader.readAsDataURL(file);
  });
  const encoded = data.split(',')[1];
  if (!encoded) throw new Error('The selected evidence file was empty.');
  return encoded;
}

const eventLabel: Record<string, string> = {
  created: 'Assignment created', bound: 'Published SOP linked',
  started: 'Execution started', step_recorded: 'Step evidence recorded',
  decision_recorded: 'Decision selected', state_advanced: 'State entered', paused: 'Execution paused',
  resumed: 'Execution resumed', blocked: 'Work blocked', completed: 'SOP completed',
};

export function WorkExecutionPanel({ item, canManage, isAssignee, onTaskChanged }: Props) {
  const [position, setPosition] = useState<ExecutionPosition | null>(null);
  const [events, setEvents] = useState<WorkEvent[]>([]);
  const [procedures, setProcedures] = useState<PublishedProcedure[]>([]);
  const [staff, setStaff] = useState<Staff[]>([]);
  const [selectedAssignee, setSelectedAssignee] = useState(item.assigned_to || '');
  const [selectedVersion, setSelectedVersion] = useState('');
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState('');
  const [note, setNote] = useState('');
  const [number, setNumber] = useState('');
  const [confirmed, setConfirmed] = useState(false);
  const [files, setFiles] = useState<Record<string, File | null>>({});
  const [blockReason, setBlockReason] = useState('');
  const [decision, setDecision] = useState('');

  const refresh = useCallback(async () => {
    setError('');
    try {
      const [current, timeline] = await Promise.all([
        apiClient<ExecutionPosition>('/work/execution/' + encodeURIComponent(item.id)),
        apiClient<{events: WorkEvent[]}>('/work/execution/' + encodeURIComponent(item.id) + '/timeline'),
      ]);
      setPosition(current);
      setEvents(timeline.events || []);
      if (canManage && (current.status === 'queued' || current.status === 'ready')) {
        const people = await apiClient<{items: Staff[]}>('/work/items/assignees');
        setStaff(people.items || []);
        if (current.status === 'queued') {
          const approved = await apiClient<{items: PublishedProcedure[]}>('/work/execution/procedures');
          setProcedures(approved.items || []);
        }
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Execution status unavailable.');
    } finally {
      setLoading(false);
    }
  }, [item.id, canManage]);

  useEffect(() => {
    setLoading(true);
    void refresh();
  }, [refresh]);

  useEffect(() => {
    setSelectedAssignee(item.assigned_to || '');
  }, [item.assigned_to]);

  const assignWork = async () => {
    if (!selectedAssignee || working) return;
    setWorking(true);
    setError('');
    try {
      await apiClient('/work/items/' + encodeURIComponent(item.id) + '/assign', {
        method:'POST',body:JSON.stringify({assigned_to:selectedAssignee}),
      });
      onTaskChanged();
      await refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not update the assigned employee.');
    } finally {
      setWorking(false);
    }
  };

  const commit = async (suffix: string, payload?: object) => {
    setWorking(true);
    setError('');
    try {
      await apiClient('/work/execution/' + encodeURIComponent(item.id) + '/' + suffix, {
        method: 'POST', ...(payload ? { body: JSON.stringify(payload) } : {}),
      });
      setConfirmed(false);
      setNote('');
      setNumber('');
      setFiles({});
      setDecision('');
      onTaskChanged();
      await refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'The operation could not be recorded.');
    } finally {
      setWorking(false);
    }
  };

  const recordStep = async () => {
    if (!position?.step) return;
    setWorking(true);
    setError('');
    try {
      const attachments: { spec_id: string; filename: string; content_base64: string }[] = [];
      for (const spec of position.step.evidence_specs) {
        const file = files[spec.id];
        if (!file) continue;
        attachments.push({ spec_id: spec.id, filename: file.name, content_base64: await encodeFile(file) });
      }
      await apiClient('/work/execution/' + encodeURIComponent(item.id) + '/step', {
        method: 'POST',
        body: JSON.stringify({
          step_id: position.step.id,
          confirmation: confirmed,
          text: note.trim(),
          number: number === '' ? null : Number(number),
          evidence_files: attachments,
        }),
      });
      setConfirmed(false);
      setNote('');
      setNumber('');
      setFiles({});
      onTaskChanged();
      await refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Evidence was not recorded.');
    } finally {
      setWorking(false);
    }
  };

  const step = position?.step;
  const requiredSpecs = step?.evidence_specs.filter(spec => spec.is_required) || [];
  const unsupportedSpec = requiredSpecs.some(spec => !['DOCUMENT_PDF','PHOTO_JPEG'].includes(spec.evidence_type));
  const inputReady = !step ? false :
    step.expected_output_type === 'CONFIRMATION' ? confirmed :
    ['TEXT_INPUT','SINGLE_CHOICE','MULTI_CHOICE'].includes(step.expected_output_type) ? note.trim().length >= 2 :
    step.expected_output_type === 'NUMERIC_INPUT' ? number !== '' && Number.isFinite(Number(number)) :
    step.expected_output_type === 'DOCUMENT_UPLOAD' ? Object.values(files).some(Boolean) : true;
  const filesReady = requiredSpecs.every(spec => Boolean(files[spec.id]));
  const safetyGates = position?.safety_gates || [];

  return (
    <section className="overflow-hidden rounded-[1.6rem] border border-[#d8e2da] bg-white" aria-labelledby="work-execution-title">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#e9efe9] px-6 py-5">
        <div>
          <p className="text-[10px] font-bold uppercase tracking-[.15em] text-emerald-700">CONTROLLED EXECUTION</p>
          <h2 id="work-execution-title" className="mt-1 text-xl font-semibold tracking-tight">Work procedure</h2>
        </div>
        <button type="button" onClick={() => void refresh()} disabled={working || loading}
          className="inline-flex min-h-10 items-center gap-2 rounded-lg border border-[#dce5dc] px-3 text-xs font-semibold text-[#405a49] disabled:opacity-50">
          <RefreshCw className="h-3.5 w-3.5" />Refresh
        </button>
      </div>
      <div className="space-y-6 p-5 sm:p-6">
        {loading ? <p className="text-sm text-[#62746a]">Checking the current task and approved SOP…</p> : null}
        {error ? <div role="alert" className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-xs leading-6 text-red-800">{error}</div> : null}
        {position ? <>
          {position.workflow_version_id ? (
            <div className="flex flex-wrap items-center gap-3 rounded-xl bg-[#f2f7f2] px-4 py-3">
              <ShieldCheck className="h-5 w-5 text-emerald-700" />
              <div className="min-w-0 flex-1"><p className="text-xs font-semibold text-[#234b33]">Published SOP version linked</p><p className="break-all text-[11px] text-[#7c8c80]">{position.workflow_version_id}</p></div>
              <span className="rounded-md bg-white px-2.5 py-1 text-[10px] font-bold uppercase tracking-wide text-emerald-800">{position.status.replaceAll('_',' ')}</span>
            </div>
          ) : null}

          {canManage && ['queued','ready'].includes(position.status) ? (
            <div className="space-y-3 rounded-xl border border-[#dfe7df] bg-[#f7faf7] p-4">
              <p className="text-xs font-semibold text-[#284a32]">Assigned worker</p>
              <div className="flex flex-wrap gap-2">
                <select aria-label="Assigned worker" className="wm-input min-w-0 flex-1" value={selectedAssignee}
                  onChange={event => setSelectedAssignee(event.target.value)}>
                  <option value="">Unassigned</option>
                  {staff.map(person => <option key={person.id} value={person.id}>{person.label}</option>)}
                </select>
                <button type="button" disabled={!selectedAssignee || working || selectedAssignee === item.assigned_to}
                  onClick={() => void assignWork()} className="rounded-xl bg-[#205a40] px-4 py-2 text-xs font-semibold text-white disabled:opacity-50">
                  Assign worker
                </button>
              </div>
              <p className="text-[11px] text-[#77877b]">Only active employees in your department can receive this assignment. Ownership becomes locked once work starts.</p>
            </div>
          ) : null}

          {position.status === 'queued' ? (
            <div className="space-y-5">
              <div className="flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 p-4">
                <LockKeyhole className="mt-0.5 h-5 w-5 shrink-0 text-amber-800" />
                <div><h3 className="text-sm font-semibold text-amber-950">No published procedure linked</h3><p className="mt-1 text-xs leading-6 text-amber-900">This assignment cannot be executed until a supervisor links a published SOP for this department.</p></div>
              </div>
              {canManage ? <div className="space-y-3">
                <label htmlFor="approved-procedure" className="wm-label">Published procedure</label>
                <select id="approved-procedure" className="wm-input" value={selectedVersion} onChange={e => setSelectedVersion(e.target.value)}>
                  <option value="">Choose an approved SOP</option>
                  {procedures.map(proc => <option key={proc.workflow_version_id} value={proc.workflow_version_id}>{proc.title} · v{proc.version_number} ({proc.workflow_code})</option>)}
                </select>
                {procedures.length === 0 ? <p className="text-xs text-[#7b877b]">No executable published SOPs in this department. An administrator must publish one first.</p> : null}
                <button type="button" disabled={!selectedVersion || working} onClick={() => void commit('bind', {workflow_version_id:selectedVersion})}
                  className="inline-flex min-h-11 items-center gap-2 rounded-xl bg-[#175b42] px-5 text-sm font-semibold text-white disabled:opacity-50">
                  <GitBranchPlus className="h-4 w-4" />Link published SOP
                </button>
              </div> : null}
            </div>
          ) : null}

          {position.status === 'ready' ? (
            <div className="space-y-4 rounded-[1.35rem] bg-[#f1f8f3] p-6">
              <h3 className="text-lg font-semibold text-[#1d432d]">Ready for the first checkpoint</h3>
              <p className="text-sm leading-6 text-[#607464]">The versioned SOP is locked to this assignment. Start only when you are ready to record your actions against its approved steps.</p>
              {isAssignee ? <button type="button" disabled={working} onClick={() => void commit('start')}
                className="inline-flex min-h-12 items-center gap-2 rounded-xl bg-[#15583e] px-5 text-sm font-semibold text-white disabled:opacity-50">
                <PlayCircle className="h-5 w-5" />Start guided work <ArrowRight className="h-4 w-4" />
              </button> : <p className="text-xs font-semibold text-[#5f7867]">Waiting for the assigned employee to begin.</p>}
            </div>
          ) : null}

          {position.status === 'active' && safetyGates.length ? (
            <div role="alert" className="rounded-xl border border-amber-200 bg-amber-50 p-4">
              <div className="flex items-center gap-2 text-sm font-semibold text-amber-950">
                <ShieldAlert className="h-5 w-5" />Supervisor / safety validation required
              </div>
              {safetyGates.map(gate => <p key={gate.rule_code} className="mt-2 text-xs leading-6 text-amber-950">
                {gate.rule_code}: {gate.error_message}
              </p>)}
              <p className="mt-2 text-xs leading-6 text-amber-900">This state cannot be approved automatically. Stop work and escalate; a worker attestation will not bypass the published gate.</p>
            </div>
          ) : null}
          {position.status === 'active' ? <>
            <div className="space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <span className="text-xs font-semibold text-[#657b6e]">{position.state?.title || 'Current checkpoint'}</span>
                <span className="text-xs font-bold tabular-nums text-emerald-800">{position.completed_steps} / {position.total_steps} recorded</span>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-[#e6eee7]">
                <div className="h-full rounded-full bg-[#1d865a] transition-[width]"
                  style={{width: position.total_steps ? Math.min(100, position.completed_steps / position.total_steps * 100) + '%' : '0%'}} />
              </div>
            </div>
            {step ? <div className="rounded-[1.4rem] border border-[#d7e2d8] p-5 sm:p-6">
              <p className="text-[10px] font-bold uppercase tracking-[.14em] text-emerald-700">STEP {step.ordinal_index} · {step.step_code}</p>
              <h3 className="mt-3 text-xl font-semibold leading-8 tracking-tight text-[#1b3527]">{step.instruction}</h3>
              <p className="mt-3 text-xs leading-6 text-[#7c8a7e]">A recorded worker attestation is not independent verification that the physical action occurred.</p>
              {isAssignee ? <div className="mt-5 space-y-4">
                {step.expected_output_type === 'CONFIRMATION' ? (
                  <label className="flex cursor-pointer items-start gap-3 rounded-xl border border-[#dfe9e0] bg-[#f5f9f5] p-4">
                    <input type="checkbox" checked={confirmed} onChange={e => setConfirmed(e.target.checked)} className="mt-1 h-5 w-5 accent-emerald-700" />
                    <span className="text-sm font-semibold text-[#254b32]">I confirm I performed this checkpoint</span>
                  </label>
                ) : ['TEXT_INPUT','SINGLE_CHOICE','MULTI_CHOICE'].includes(step.expected_output_type) ? (
                  <div><label htmlFor="step-observation" className="wm-label">Recorded observation</label>
                    <textarea id="step-observation" className="wm-input min-h-28" maxLength={1500}
                      value={note} onChange={e => setNote(e.target.value)}
                      placeholder="Record the actual condition, barcode, reading or result…" />
                  </div>
                ) : step.expected_output_type === 'NUMERIC_INPUT' ? (
                  <div><label htmlFor="step-numeric" className="wm-label">Actual numeric reading</label>
                    <input id="step-numeric" type="number" className="wm-input" value={number} onChange={e => setNumber(e.target.value)} placeholder="Enter a number" />
                  </div>
                ) : null}
                {step.evidence_specs.length ? <div className="space-y-3 border-t border-[#e8eee8] pt-5">
                  <h4 className="flex items-center gap-2 text-sm font-semibold"><FileCheck2 className="h-4 w-4 text-emerald-700" />SOP evidence requirements</h4>
                  {step.evidence_specs.map(spec => {
                    const supported = ['DOCUMENT_PDF','PHOTO_JPEG'].includes(spec.evidence_type);
                    return <div key={spec.id} className="rounded-xl border border-[#dce7de] bg-[#f7faf7] p-4">
                      <label htmlFor={'file-'+spec.id} className="mb-2 flex items-center gap-2 text-xs font-semibold text-[#234834]">
                        {spec.evidence_type === 'PHOTO_JPEG' ? <Camera className="h-4 w-4" /> : <FileText className="h-4 w-4" />}
                        {spec.evidence_type.replaceAll('_',' ')}{spec.is_required ? ' · Required' : ' · Optional'}
                      </label>
                      {supported ? <input id={'file-'+spec.id} type="file" accept={spec.evidence_type === 'PHOTO_JPEG' ? '.jpg,.jpeg,image/jpeg' : '.pdf,application/pdf'}
                        onChange={e => setFiles(old => ({...old,[spec.id]:e.target.files?.[0] || null}))}
                        className="block w-full max-w-full text-xs text-[#54695b] file:mr-3 file:rounded-lg file:border-0 file:bg-[#e0efe3] file:px-3 file:py-2 file:font-semibold file:text-[#15583e]" />
                        : <p className="text-xs leading-6 text-amber-800">Requires specialist human validation. WorkMate will not self-approve this checkpoint.</p>}
                      {spec.min_size_bytes ? <p className="mt-2 text-[11px] text-[#8b998e]">Minimum size {spec.min_size_bytes} bytes. Maximum upload 2 MB.</p> : null}
                    </div>;
                  })}
                </div> : null}
                <button type="button" disabled={!inputReady || !filesReady || unsupportedSpec || safetyGates.length > 0 || working} onClick={() => void recordStep()}
                  className="inline-flex min-h-12 w-full items-center justify-center gap-2 rounded-xl bg-[#15583e] px-5 text-sm font-semibold text-white hover:bg-[#0d3929] disabled:cursor-not-allowed disabled:opacity-50">
                  <ClipboardCheck className="h-5 w-5" />{working ? 'Recording…' : 'Record checkpoint'}<ArrowRight className="h-4 w-4" />
                </button>
              </div> : <p className="mt-5 text-xs text-[#728075]">Only the assigned employee can record this checkpoint.</p>}
            </div> : null}
            {!step && position.decision_options.length ? (
              <div className="rounded-[1.4rem] border border-[#d7e2d8] p-5 sm:p-6">
                <p className="text-[10px] font-bold uppercase tracking-[.15em] text-emerald-700">SOP DECISION</p>
                <h3 className="mt-2 text-lg font-semibold">{position.decision_question || position.state?.title}</h3>
                <p className="mt-2 text-xs leading-6 text-[#6d796f]">Select only the actual observed outcome. The approved workflow determines the next state.</p>
                {isAssignee ? <div className="mt-4 space-y-3">
                  <fieldset className="space-y-2"><legend className="sr-only">Approved decision path</legend>
                    {position.decision_options.map(option => <label key={option.option_code} className="flex cursor-pointer items-center gap-3 rounded-xl border border-[#dae6dc] p-4 text-sm font-medium">
                      <input type="radio" name="work-decision" value={option.option_code} checked={decision===option.option_code} onChange={() => setDecision(option.option_code)} className="h-4 w-4 accent-emerald-700" />
                      {option.option_label}
                    </label>)}
                  </fieldset>
                  <button type="button" disabled={!decision || safetyGates.length > 0 || working} onClick={() => void commit('decision',{decision_option:decision})}
                    className="inline-flex min-h-12 items-center gap-2 rounded-xl bg-[#15583e] px-5 text-sm font-semibold text-white disabled:opacity-50">
                    Record decision <ArrowRight className="h-4 w-4" />
                  </button>
                </div> : null}
              </div>
            ) : null}
            {!step && position.decision_options.length === 0 ? (
              <div className="rounded-[1.3rem] border border-[#dbe5dc] bg-[#f4f8f4] p-5">
                <h3 className="text-lg font-semibold">{position.state?.title || 'Procedure checkpoint'}</h3>
                {position.state?.description ? <p className="mt-2 text-xs leading-6 text-[#657b6d]">{position.state.description}</p> : null}
                <p className="mt-2 text-xs leading-6 text-[#728579]">No atomic step or decision is required in this published state. Continue only after checking the listed procedure context.</p>
                {isAssignee ? <button type="button" disabled={working || safetyGates.length > 0} onClick={() => void commit('continue')}
                  className="mt-4 inline-flex min-h-11 items-center gap-2 rounded-xl bg-[#15583e] px-5 text-xs font-semibold text-white disabled:opacity-50">Continue approved procedure <ArrowRight className="h-4 w-4" /></button> : null}
              </div>
            ) : null}
            {isAssignee ? <div className="space-y-3 border-t border-[#edf1ed] pt-5">
              <div className="flex flex-wrap gap-2">
                <button type="button" onClick={() => void commit('pause')} disabled={working}
                  className="inline-flex min-h-10 items-center gap-2 rounded-xl border border-[#dce4dd] px-4 text-xs font-semibold"><PauseCircle className="h-4 w-4" />Pause work</button>
              </div>
              <label htmlFor="block-reason" className="wm-label">Unsafe or unexpected condition?</label>
              <textarea id="block-reason" className="wm-input min-h-20" value={blockReason} maxLength={500}
                onChange={e => setBlockReason(e.target.value)} placeholder="Describe why work must stop and supervisor help is needed…" />
              <button type="button" disabled={blockReason.trim().length < 8 || working}
                onClick={() => void commit('block',{reason:blockReason.trim()})}
                className="inline-flex min-h-10 items-center gap-2 rounded-xl border border-amber-200 bg-amber-50 px-4 text-xs font-semibold text-amber-900 disabled:opacity-50">
                <ShieldAlert className="h-4 w-4" />Block and escalate
              </button>
            </div> : null}
          </> : null}

          {position.status === 'paused' ? <div className="rounded-xl border border-[#dbe6dd] bg-[#f6f9f6] p-5">
            <h3 className="text-base font-semibold">Work paused</h3>
            <p className="mt-2 text-xs leading-6 text-[#6b7b70]">Your step history is retained. Resume only when it is appropriate to continue.</p>
            {isAssignee ? <button type="button" onClick={() => void commit('resume')} disabled={working} className="mt-4 inline-flex min-h-11 items-center gap-2 rounded-xl bg-[#15583e] px-5 text-xs font-semibold text-white"><PlayCircle className="h-4 w-4" />Resume execution</button> : null}
          </div> : null}

          {position.status === 'blocked' ? <div className="flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 p-5">
            <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-amber-800" />
            <div><h3 className="text-base font-semibold text-amber-950">Work blocked</h3><p className="mt-2 text-xs leading-6 text-amber-900">Stop this operation and contact your supervisor. Worker self-release is disabled; a human-authorized resolution process will be added before blocked work can resume.</p></div>
          </div> : null}

          {position.status === 'completed' ? <div className="rounded-[1.4rem] border border-[#cce4d1] bg-[#eff8f0] p-6">
            <CheckCircle2 className="h-7 w-7 text-emerald-700" />
            <h3 className="mt-3 text-xl font-semibold text-[#205036]">Published workflow completed</h3>
            <p className="mt-2 text-xs leading-6 text-[#597261]">All required recorded checkpoints and published branch decisions were submitted. Photographs and documents are stored with hashes, but their physical truth has not been independently verified.</p>
            <p className="mt-3 text-xs font-bold text-emerald-800">{position.completed_steps} / {position.total_steps} atomic steps recorded</p>
          </div> : null}
        </> : null}

        <div className="border-t border-[#eaf0e9] pt-5">
          <div className="flex items-center gap-2"><Clock3 className="h-4 w-4 text-[#638975]" /><h3 className="text-sm font-semibold">Execution record</h3></div>
          {events.length ? <div className="mt-3 divide-y divide-[#eef2ed]">
            {events.slice(-12).reverse().map(event => <div key={event.id} className="flex items-start justify-between gap-3 py-3 text-xs">
              <div><p className="font-semibold text-[#294434]">{eventLabel[event.action] || event.action.replaceAll('_',' ')}</p><p className="mt-1 break-words text-[11px] text-[#88968b]">Recorded by {event.actor_id}</p></div>
              <span className="shrink-0 text-[11px] text-[#87958a]">{new Date(event.created_at).toLocaleString()}</span>
            </div>)}
          </div> : <p className="mt-3 text-xs text-[#77857b]">No workflow events recorded.</p>}
        </div>
        <div className="flex items-start gap-2 text-[11px] leading-5 text-[#728175]">
          <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-emerald-700" />
          <p>Actions are checked against the current published procedure and server-side task state. Evidence is retained privately for review; recording does not certify physical SOP compliance.</p>
        </div>
      </div>
    </section>
  );
}
