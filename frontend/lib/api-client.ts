// Typed Fetch Client Wrapper for WorkMate AI FastAPI Endpoints
import { refreshAccessToken } from '@/lib/auth';

export interface ApiErrorPayload {
  error_code: string;
  message: string;
  details?: Record<string, any>;
}

export class ApiError extends Error {
  error_code: string;
  details?: Record<string, any>;

  constructor(payload: ApiErrorPayload, public status: number) {
    super(payload.message);
    this.name = 'ApiError';
    this.error_code = payload.error_code || 'UNKNOWN_ERROR';
    this.details = payload.details;
  }
}

export interface Citation {
  document_id: string;
  document_title: string;
  version_number: number;
  step_number?: number | string;
  chunk_id: string;
  excerpt: string;
  state_id?: string | null;
}

export interface CopilotResponse {
  conversation_id?: string;
  message_id: string;
  answer: string;
  spoken_answer?: string | null;
  sop_details?: string | null;
  citations: Citation[];
  confidence_score: number;
  is_grounded: boolean;
  requires_escalation: boolean;
  active_session_id?: string | null;
  active_session_status?: 'active' | 'paused' | 'completed' | 'abandoned' | 'escalated' | null;
  active_sop_id?: string | null;
  active_step_number?: number | null;
  active_step_title?: string | null;
  active_decision_options?: WorkflowDecisionOption[];
  sop_suggestions?: SopSuggestion[];
}

export interface SopSuggestion {
  workflow_code: string;
  title: string;
  description: string;
  match_score: number;
}

export interface WorkflowDecisionOption {
  option_code: string;
  option_label: string;
}

export type VoiceLanguage = 'auto' | 'en' | 'hi';

export interface VoiceCopilotResponse {
  language: Exclude<VoiceLanguage, 'auto'>;
  transcript: string;
  translated_transcript: string;
  response_text: string;
  audio_url?: string | null;
  confidence: number;
  transcription_ms: number;
  translation_ms: number;
  synthesis_ms: number;
  copilot: CopilotResponse;
}

export interface VoiceSynthesisResponse {
  audio_url: string;
  synthesis_ms: number;
}

export interface WorkflowAdvanceResponse {
  status: CopilotResponse['active_session_status'];
  current_state_id?: string | null;
  active_step_number?: number | null;
  active_step_title?: string | null;
  active_decision_options: WorkflowDecisionOption[];
}

export interface KnowledgeDocument {
  id: string;
  title: string;
  department_id: string;
  category: string;
  status: 'DRAFT' | 'PROCESSING' | 'PUBLISHED' | 'ARCHIVED';
  current_version: number;
  created_at: string;
  updated_at: string;
}

export interface MetricCardData {
  title: string;
  value: string | number;
  change?: string;
  trend?: 'up' | 'down' | 'neutral';
}

export interface WorkflowState {
  id: string;
  state_key: string;
  state_type: string;
  title: string;
  description?: string;
  is_initial?: boolean;
  is_terminal?: boolean;
  ordinal_index?: number;
}

export interface KnowledgeItem {
  id: string;
  title: string;
  department_id: string;
  created_by: string;
  created_at: string;
  workflow_code?: string;
  description?: string;
  category?: string;
  updated_at?: string;
}

export interface KnowledgeVersion {
  id: string;
  knowledge_item_id: string;
  workflow_id?: string;
  version_number: number;
  semantic_version?: string;
  stage_file_uri: string;
  ast_hash?: string;
  status: string;
  created_at: string;
  published_at?: string;
}

export interface KnowledgeItemDetail {
  item: KnowledgeItem;
  latest_version?: KnowledgeVersion;
  published_version?: KnowledgeVersion;
  states?: WorkflowState[];
}

export interface PaginatedKnowledgeItems {
  items: KnowledgeItemDetail[];
  total: number;
  page: number;
  limit: number;
}

export interface KnowledgeVersionHistory {
  knowledge_item_id: string;
  versions: KnowledgeVersion[];
}

export interface KnowledgePermanentDeleteResponse {
  id: string;
  message: string;
  deleted_counts: Record<string, number>;
  stage_files_deleted: number;
  stage_cleanup_warning?: string | null;
}

export interface CopilotSessionSummary {
  id: string;
  title: string;
  status: string;
  started_at: string;
  last_message_preview?: string;
}

export interface CopilotHistoryResponse {
  sessions: CopilotSessionSummary[];
  total: number;
}

export interface CopilotConversationDetail {
  conversation_id: string;
  messages: Array<{
    id: string;
    sender: 'employee' | 'ai';
    content: string;
    confidence_score: number;
    created_at: string;
  }>;
  active_session_id?: string | null;
  active_session_status?: CopilotResponse['active_session_status'];
  active_sop_id?: string | null;
  active_step_number?: number | null;
  active_step_title?: string | null;
  active_decision_options?: WorkflowDecisionOption[];
}

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000/api/v1';

export async function apiClient<T>(
  endpoint: string,
  options: RequestInit & { _isRetry?: boolean } = {}
): Promise<T> {
  const { _isRetry, ...fetchOptions } = options;
  const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null;

  const headers: Record<string, string> = {
    ...(fetchOptions.headers as Record<string, string>),
  };

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  if (!(fetchOptions.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
  }

  let response = await fetch(`${API_BASE_URL}${endpoint}`, {
    ...fetchOptions,
    headers,
  });

  // Automatic 401 refresh token retry logic
  if (response.status === 401 && endpoint !== '/auth/refresh' && !_isRetry) {
    const newToken = await refreshAccessToken();
    if (newToken) {
      headers['Authorization'] = `Bearer ${newToken}`;
      response = await fetch(`${API_BASE_URL}${endpoint}`, {
        ...fetchOptions,
        headers,
      });
    } else {
      if (typeof window !== 'undefined') {
        localStorage.removeItem('token');
        localStorage.removeItem('refresh_token');
        if (window.location.pathname !== '/login') {
          window.location.href = '/login';
        }
      }
    }
  }

  if (!response.ok) {
    let errorPayload: ApiErrorPayload;
    try {
      const body = await response.json();
      // FastAPI HTTPException responses wrap the application payload in
      // `detail`; global exception handlers return it at the top level.
      errorPayload = body?.detail ?? body;
    } catch {
      errorPayload = {
        error_code: 'HTTP_ERROR',
        message: response.statusText || 'An unexpected error occurred.',
      };
    }
    throw new ApiError(errorPayload, response.status);
  }

  return response.json() as Promise<T>;
}

export async function apiBlob(endpoint: string): Promise<Blob> {
  let token = typeof window !== 'undefined' ? localStorage.getItem('token') : null;
  let response = await fetch(`${API_BASE_URL}${endpoint}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (response.status === 401) {
    token = await refreshAccessToken();
    if (token) {
      response = await fetch(`${API_BASE_URL}${endpoint}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
    }
  }
  if (!response.ok) {
    throw new ApiError(
      { error_code: 'VOICE_AUDIO_ERROR', message: 'Voice audio is unavailable or expired.' },
      response.status,
    );
  }
  return response.blob();
}
