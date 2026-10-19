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
  status: 'queued';
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
