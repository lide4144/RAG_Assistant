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
}

export interface KernelErrorResponse {
  error: {
    code: string;
    message: string;
    retryable: boolean;
  };
}
