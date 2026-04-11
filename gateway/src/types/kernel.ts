export type ChatMode = 'local' | 'web' | 'hybrid';

export interface KernelChatRequest {
  sessionId: string;
  mode: ChatMode;
  query: string;
  history?: Array<{
    role: 'user' | 'assistant';
    content: string;
  }>;
  traceId?: string;
}

export interface KernelSource {
  source_type: 'local' | 'web' | 'graph';
  source_id: string;
  title: string;
  snippet: string;
  locator: string;
  score: number;
}

export interface KernelChatResponse {
  traceId: string;
  answer: string;
  sources: KernelSource[];
  runId?: string;
}

export interface KernelJobStatus {
  job_id: string;
  kind: string;
  state: string;
  created_at: string;
  updated_at: string;
  accepted: boolean;
  session_id?: string;
  trace_id?: string;
  run_id?: string;
  config_version_id?: string;
  progress_stage?: string;
  latest_output_text?: string;
  result?: Record<string, unknown>;
  error?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
}

export interface KernelJobEvent {
  job_id: string;
  seq: number;
  event_type: string;
  created_at: string;
  payload: Record<string, unknown>;
}

export interface KernelJobCreateResponse {
  ok: boolean;
  job: KernelJobStatus;
}

export interface KernelErrorResponse {
  error: {
    code: string;
    message: string;
    retryable: boolean;
  };
}
