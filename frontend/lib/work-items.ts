/** First-class WorkMate execution domain. Phase 1 is a queue, not step execution. */
export type WorkType = 'receiving' | 'putaway' | 'stock_count' | 'picking' | 'dispatch' | 'other';
export type WorkPriority = 'standard' | 'high';

export interface WorkItem {
  id: string;
  department_id: string;
  created_by: string;
  assigned_to: string | null;
  external_reference: string | null;
  title: string;
  work_type: WorkType;
  priority: WorkPriority;
  instructions: string;
  status: 'queued' | 'ready' | 'active' | 'paused' | 'blocked' | 'completed';
  workflow_version_id?: string | null;
  execution_session_id?: string | null;
  completed_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface WorkQueueResponse {
  items: WorkItem[];
  scope: 'department' | 'assigned';
}

export const WORK_TYPES: { value: WorkType; label: string }[] = [
  { value: 'receiving', label: 'Receiving' },
  { value: 'putaway', label: 'Putaway' },
  { value: 'stock_count', label: 'Stock count' },
  { value: 'picking', label: 'Picking' },
  { value: 'dispatch', label: 'Dispatch' },
  { value: 'other', label: 'Other' },
];

export function workTypeLabel(value: WorkType): string {
  return WORK_TYPES.find(item => item.value === value)?.label ?? 'Work';
}

/** Copilot drafts are always editable and never auto-sent. */
export function guidanceUrl(item: Pick<WorkItem, 'title' | 'work_type' | 'instructions'>): string {
  const prompt = [
    'Find the current approved procedure for ' + workTypeLabel(item.work_type).toLowerCase() + '.',
    'Work: ' + item.title + '.',
    item.instructions ? 'Context: ' + item.instructions : '',
    'Show the applicable first checkpoint. Do not claim this task is complete.',
  ].filter(Boolean).join(' ').slice(0, 500);
  return '/copilot?mode=workflow&draft=' + encodeURIComponent(prompt);
}


export interface ExecutionEvidenceSpec {
  id: string;
  evidence_type: 'DOCUMENT_PDF' | 'PHOTO_JPEG' | 'DIGITAL_SIGNATURE' | 'CHECKSUM_HASH' | 'SUPERVISOR_APPROVAL';
  is_required: boolean;
  min_size_bytes: number | null;
}

export interface ExecutionStep {
  id: string;
  step_code: string;
  ordinal_index: number;
  instruction: string;
  is_mandatory: boolean;
  expected_output_type: 'CONFIRMATION' | 'TEXT_INPUT' | 'NUMERIC_INPUT' | 'DOCUMENT_UPLOAD' | 'SINGLE_CHOICE' | 'MULTI_CHOICE';
  evidence_specs: ExecutionEvidenceSpec[];
}

export interface ExecutionPosition {
  work_id: string;
  case_id?: string | null;
  status: WorkItem['status'];
  workflow_version_id: string | null;
  session_id: string | null;
  state: { id: string; title: string; description?: string | null; state_type: string; is_terminal: boolean } | null;
  step: ExecutionStep | null;
  decision_options: { option_code: string; option_label: string }[];
  decision_question?: string | null;
  safety_gates: {rule_code:string;enforcement_level:string;error_message:string}[];
  completed_steps: number;
  total_steps: number;
}

export interface PublishedProcedure {
  workflow_version_id: string;
  title: string;
  workflow_code: string;
  version_number: number;
}

export interface WorkEvent {
  id: string;
  actor_id: string;
  action: string;
  event_payload: { [key: string]: unknown };
  created_at: string;
}

export function workStatusLabel(status: WorkItem['status']): string {
  const values: Record<WorkItem['status'], string> = {
    queued: 'Unlinked', ready: 'Ready', active: 'In progress',
    paused: 'Paused', blocked: 'Blocked', completed: 'Completed',
  };
  return values[status];
}
