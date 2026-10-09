export enum FileType {
  PDF = 'PDF',
  HTML = 'HTML',
  TXT = 'TXT'
}

export interface DocumentMetadata {
  author?: string;
  publishDate?: string;
  tags: string[];
  processedAt: string;
}

export interface PaperDocument {
  id: string;
  title: string;
  type: FileType;
  size: string;
  status: 'processing' | 'indexed' | 'error';
  metadata: DocumentMetadata;
  vectorCount: number;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: number;
  sources?: string[]; // IDs of source documents
  confidence?: number;
}

export type AppView = 'dashboard' | 'converter' | 'storage' | 'query' | 'settings';