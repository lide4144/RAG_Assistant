import type { ChatMode, KernelSource } from './kernel.js';
import type { KernelTaskError, KernelTaskState, KernelTaskStatus } from '../adapters/pythonKernelClient.js';
import type { AgentEvent } from './agent-events.js';

export interface WebProviderMeta {
  providerUsed: 'mock' | 'duckduckgo';
  isMockFallback: boolean;
  fallbackReason?: string;
}

interface EventMeta {
  webProvider?: WebProviderMeta;
}

interface JobEventIdentity {
  jobId?: string;
  seq?: number;
  createdAt?: string;
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

export interface ClientJobSubscribeEvent {
  type: 'job_subscribe';
  payload: {
    jobId: string;
    afterSeq?: number;
  };
}

export interface MessageEvent extends JobEventIdentity {
  type: 'message';
  traceId: string;
  mode: ChatMode;
  content: string;
  meta?: EventMeta;
}

export interface SourcesEvent extends JobEventIdentity {
  type: 'sources';
  traceId: string;
  mode: ChatMode;
  sources: KernelSource[];
  runId?: string;
  meta?: EventMeta;
}

export interface MessageEndEvent extends JobEventIdentity {
  type: 'messageEnd';
  traceId: string;
  mode: ChatMode;
  runId?: string;
  usage?: {
    latencyMs: number;
  };
  meta?: EventMeta;
}

export interface ErrorEvent extends JobEventIdentity {
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

export type ClientInboundEvent = ClientChatRequestEvent | ClientTaskStartGraphBuildEvent | ClientJobSubscribeEvent;
export type OutboundEvent =
  | AgentEvent
  | MessageEvent
  | SourcesEvent
  | MessageEndEvent
  | ErrorEvent
  | TaskStateEvent
  | TaskProgressEvent
  | TaskResultEvent
  | TaskErrorEvent;
