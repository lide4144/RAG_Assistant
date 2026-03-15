import type { ChatMode, KernelSource } from './kernel.js';
import type { KernelTaskError, KernelTaskState, KernelTaskStatus } from '../adapters/pythonKernelClient.js';

export interface WebProviderMeta {
  providerUsed: 'mock' | 'duckduckgo';
  isMockFallback: boolean;
  fallbackReason?: string;
}

interface EventMeta {
  webProvider?: WebProviderMeta;
}

type AgentExecutionTimestamp = string;

export interface PlanningEvent {
  type: 'planning';
  traceId: string;
  mode: ChatMode;
  timestamp: AgentExecutionTimestamp;
  phase: 'planning';
  decisionResult?: string;
  selectedPath?: string;
  selectedToolsOrSkills?: string[];
}

export interface ToolSelectionEvent {
  type: 'toolSelection';
  traceId: string;
  mode: ChatMode;
  timestamp: AgentExecutionTimestamp;
  toolName: string;
  callId: string;
  status: 'selected';
}

export interface ToolRunningEvent {
  type: 'toolRunning';
  traceId: string;
  mode: ChatMode;
  timestamp: AgentExecutionTimestamp;
  toolName: string;
  callId: string;
  status: 'running';
}

export interface ToolResultEvent {
  type: 'toolResult';
  traceId: string;
  mode: ChatMode;
  timestamp: AgentExecutionTimestamp;
  toolName: string;
  callId: string;
  status: 'succeeded' | 'failed' | 'clarify_required' | 'blocked' | 'skipped';
  resultKind?: 'final' | 'intermediate' | 'empty' | 'failed' | 'clarify_required';
  message?: string;
}

export interface FallbackEvent {
  type: 'fallback';
  traceId: string;
  mode: ChatMode;
  timestamp: AgentExecutionTimestamp;
  fallbackScope: 'planner' | 'tool' | 'legacy';
  reasonCode: string;
  failedTool?: string;
  continues: boolean;
  message?: string;
}

export interface ClientChatRequestEvent {
  type: 'chat';
  payload: {
    sessionId: string;
    mode: ChatMode;
    query: string;
    history?: Array<{ role: 'user' | 'assistant'; content: string }>;
  };
}

export interface ClientTaskStartGraphBuildEvent {
  type: 'task_start_graph_build';
  payload?: {
    input_path?: string;
    output_path?: string;
    threshold?: number;
    top_m?: number;
    include_front_matter?: boolean;
    force_new?: boolean;
    llm_max_concurrency?: number;
  };
}

export interface MessageEvent {
  type: 'message';
  traceId: string;
  mode: ChatMode;
  content: string;
  meta?: EventMeta;
}

export interface SourcesEvent {
  type: 'sources';
  traceId: string;
  mode: ChatMode;
  sources: KernelSource[];
  meta?: EventMeta;
}

export interface MessageEndEvent {
  type: 'messageEnd';
  traceId: string;
  mode: ChatMode;
  usage?: {
    latencyMs: number;
  };
  meta?: EventMeta;
}

export interface ErrorEvent {
  type: 'error';
  traceId: string;
  code: string;
  message: string;
  meta?: EventMeta;
}

export interface TaskStateEvent {
  type: 'taskState';
  taskId: string;
  taskKind: 'graph_build';
  state: KernelTaskState;
  accepted?: boolean;
  updatedAt: string;
}

export interface TaskProgressEvent {
  type: 'taskProgress';
  taskId: string;
  taskKind: 'graph_build';
  state: KernelTaskState;
  stage: string;
  processed: number;
  total: number;
  elapsedMs: number;
  message: string;
  updatedAt: string;
}

export interface TaskResultEvent {
  type: 'taskResult';
  taskId: string;
  taskKind: 'graph_build';
  state: KernelTaskState;
  result?: KernelTaskStatus['result'];
  error?: KernelTaskError;
  updatedAt: string;
}

export interface TaskErrorEvent {
  type: 'taskError';
  taskId: string;
  taskKind: 'graph_build';
  state: 'failed';
  error: KernelTaskError;
  updatedAt: string;
}

export type ClientInboundEvent = ClientChatRequestEvent | ClientTaskStartGraphBuildEvent;
export type OutboundEvent =
  | PlanningEvent
  | ToolSelectionEvent
  | ToolRunningEvent
  | ToolResultEvent
  | FallbackEvent
  | MessageEvent
  | SourcesEvent
  | MessageEndEvent
  | ErrorEvent
  | TaskStateEvent
  | TaskProgressEvent
  | TaskResultEvent
  | TaskErrorEvent;
