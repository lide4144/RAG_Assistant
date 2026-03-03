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
