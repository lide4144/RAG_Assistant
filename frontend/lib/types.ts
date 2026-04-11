import type { AgentEvent } from './agent-events';
export type { AgentEvent } from './agent-events';

export type ChatMode = 'local' | 'web' | 'hybrid';
export type ViewMode = 'user' | 'developer';

export interface SourceItem {
  source_type: 'local' | 'web' | 'graph';
  source_id: string;
  title: string;
  snippet: string;
  locator: string;
  score: number;
}

export interface ChatMessage {
  id: string;
  jobId?: string;
  traceId?: string;
  runId?: string;
  role: 'user' | 'assistant';
  content: string;
  sources?: SourceItem[];
  agentEvents?: AgentEvent[];
  graphExpand?: boolean;
  status?: 'streaming' | 'done' | 'error';
  mode?: ChatMode;
  errorMeta?: {
    code?: string;
    detail?: string;
  };
}

export interface LlmDebugRecord {
  event: string;
  stage?: string;
  debug_stage?: string;
  provider?: string;
  model?: string;
  api_base?: string;
  endpoint?: string;
  transport?: string;
  route_id?: string;
  attempts_used?: number;
  elapsed_ms?: number;
  reason?: string;
  status_code?: number;
  error_category?: string;
  fallback_reason?: string;
  first_token_latency_ms?: number;
  chunks_received?: number;
  system_prompt?: string;
  user_prompt?: string;
  request_payload?: string;
  response_payload?: string;
  response_text?: string;
  timestamp?: string;
}

export interface LlmDebugTrace {
  trace_id: string;
  count: number;
  records: LlmDebugRecord[];
}

export interface JobEvent {
  job_id: string;
  seq: number;
  event_type: string;
  created_at: string;
  payload: Record<string, unknown>;
}

export interface JobStatus {
  job_id: string;
  kind: string;
  state: string;
  created_at: string;
  updated_at: string;
  accepted: boolean;
  session_id?: string | null;
  trace_id?: string | null;
  run_id?: string | null;
  config_version_id?: string | null;
  progress_stage?: string | null;
  latest_output_text?: string | null;
  result?: Record<string, unknown> | null;
  error?: Record<string, unknown> | null;
  metadata?: Record<string, unknown>;
}

export interface JobCreateResponse {
  ok: boolean;
  job: JobStatus;
}

export type RuntimeLevel = 'READY' | 'DEGRADED' | 'BLOCKED' | 'ERROR';
export type RuntimeSource = 'env' | 'runtime' | 'default';

export interface MarkerTuning {
  recognition_batch_size: number;
  detector_batch_size: number;
  layout_batch_size: number;
  ocr_error_batch_size: number;
  table_rec_batch_size: number;
  model_dtype: 'float16' | 'float32' | 'bfloat16' | string;
}

export interface MarkerLlmSummaryField {
  field: string;
  value: string;
  source: RuntimeSource;
}

export interface MarkerLlmRuntimeConfig {
  use_llm: boolean;
  llm_service: string;
  configured: boolean;
  status: 'disabled' | 'ready' | 'degraded' | string;
  required_errors?: string[];
  summary_fields?: MarkerLlmSummaryField[];
  effective_source?: Record<string, RuntimeSource>;
}

export interface MarkerArtifactAction {
  kind: 'copy_path' | 'rebuild' | 'delete';
  enabled: boolean;
  label: string;
  confirm_title?: string | null;
  confirm_message?: string | null;
}

export interface MarkerArtifactItem {
  key: string;
  group: 'indexes' | 'processed';
  path: string;
  file_name: string;
  artifact_type: string;
  related_stage: 'import' | 'clean' | 'index' | 'graph_build';
  exists: boolean;
  status: 'healthy' | 'missing' | 'stale';
  size_bytes?: number | null;
  updated_at?: string | null;
  health_message?: string | null;
  actions: MarkerArtifactAction[];
}

export interface MarkerParserDiagnostic {
  paper_id: string;
  source_uri: string;
  parser_engine: string;
  parser_mode?: string;
  base_parser?: string | null;
  enhanced_parser?: string | null;
  controlled_skip?: boolean;
  controlled_skip_reason?: string | null;
  parser_fallback: boolean;
  parser_fallback_stage?: string | null;
  parser_fallback_reason?: string | null;
  marker_attempt_duration_sec?: number;
  marker_stage_timings?: Record<string, number>;
}

export interface RuntimeStageSummary {
  provider: string;
  api_base?: string;
  model: string;
  configured: boolean;
  source?: RuntimeSource;
  source_label?: string;
  effective_source?: Partial<Record<'provider' | 'api_base' | 'model' | 'api_key', RuntimeSource>>;
}

export interface PlannerRuntimeSummary {
  service_mode?: 'production' | 'diagnostic' | string;
  llm_required?: boolean;
  provider: string;
  api_base?: string;
  model: string;
  timeout_ms: number;
  configured: boolean;
  formal_chat_available?: boolean;
  blocked?: boolean;
  block_reason_code?: string | null;
  block_reason_message?: string | null;
  source?: RuntimeSource;
  source_label?: string;
  effective_source?: Partial<Record<'service_mode' | 'provider' | 'api_base' | 'model' | 'api_key' | 'timeout_ms', RuntimeSource>>;
}

export interface ActiveJobSummary {
  jobId: string;
  kind: string;
  state: string;
  updatedAt: string;
  progressStage?: string;
}

export interface LlmLoggingSummary {
  enabled: boolean;
  max_body_chars: number;
  safe_root?: string;
  log_path?: string;
  download_url?: string;
  recent_files?: Array<{
    file_name: string;
    path: string;
    size_bytes: number;
    updated_at: string;
    current: boolean;
    download_url: string;
  }>;
  source?: RuntimeSource;
  effective_source?: Partial<Record<'enabled' | 'max_body_chars' | 'safe_root' | 'log_path', RuntimeSource>>;
}

export interface RuntimeOverview {
  llm: {
    answer: RuntimeStageSummary;
    embedding: RuntimeStageSummary;
    rerank: RuntimeStageSummary;
    rewrite: RuntimeStageSummary;
    graph_entity: RuntimeStageSummary;
    sufficiency_judge: RuntimeStageSummary;
  };
  planner: PlannerRuntimeSummary;
  pipeline: {
    marker_enabled?: boolean;
    marker_mode?: 'base_only' | 'enhanced' | string;
    marker_mode_summary?: 'base_only' | 'enhanced' | 'degraded_available' | string;
    marker_tuning: MarkerTuning;
    effective_source?: {
      marker_enabled?: RuntimeSource;
      marker_tuning?: Partial<Record<keyof MarkerTuning, RuntimeSource>>;
    };
    marker_llm?: MarkerLlmRuntimeConfig;
    last_ingest?: {
      degraded: boolean;
      fallback_reason?: string | null;
      fallback_path?: string | null;
      confidence_note?: string | null;
      updated_at?: string | null;
      stage_updated_at?: Partial<Record<'import' | 'clean' | 'index' | 'graph_build', string>>;
      parser_diagnostics?: MarkerParserDiagnostic[];
    };
    artifacts?: {
      counts?: Partial<Record<'healthy' | 'missing' | 'stale', number>>;
      groups?: {
        indexes?: MarkerArtifactItem[];
        processed?: MarkerArtifactItem[];
      };
    };
  };
  observability?: {
    llm_logging?: LlmLoggingSummary;
  };
  status: {
    level: RuntimeLevel;
    reasons: string[];
  };
  jobs?: {
    active: ActiveJobSummary[];
    settings_locked: boolean;
  };
}
