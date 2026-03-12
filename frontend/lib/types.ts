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
  traceId?: string;
  role: 'user' | 'assistant';
  content: string;
  sources?: SourceItem[];
  graphExpand?: boolean;
  status?: 'streaming' | 'done' | 'error';
  mode?: ChatMode;
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
  parser_fallback: boolean;
  parser_fallback_stage?: string | null;
  parser_fallback_reason?: string | null;
  marker_attempt_duration_sec?: number;
  marker_stage_timings?: Record<string, number>;
}

export interface RuntimeStageSummary {
  provider: string;
  model: string;
  configured: boolean;
}

export interface RuntimeOverview {
  llm: {
    answer: RuntimeStageSummary;
    embedding: RuntimeStageSummary;
    rerank: RuntimeStageSummary;
    rewrite: RuntimeStageSummary;
    graph_entity: RuntimeStageSummary;
  };
  pipeline: {
    marker_tuning: MarkerTuning;
    effective_source?: {
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
  status: {
    level: RuntimeLevel;
    reasons: string[];
  };
}
