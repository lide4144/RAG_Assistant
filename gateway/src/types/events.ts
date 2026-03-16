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
  | AgentEvent
  | MessageEvent
  | SourcesEvent
  | MessageEndEvent
  | ErrorEvent
  | TaskStateEvent
  | TaskProgressEvent
  | TaskResultEvent
  | TaskErrorEvent;
