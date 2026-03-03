import type { ChatMode, KernelSource } from './kernel.js';

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

export type OutboundEvent = MessageEvent | SourcesEvent | MessageEndEvent | ErrorEvent;
