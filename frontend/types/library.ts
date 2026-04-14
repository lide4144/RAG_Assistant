export interface Paper {
  paper_id: string;
  title: string;
  source_uri: string;
  status: 'imported' | 'parsed' | 'cleaned' | 'ready' | 'failed' | 'deleted' | 'rebuild_pending';
  topics: string[];
  imported_at: string;
  stage_statuses?: Record<string, { state: string; message?: string }>;
}

export interface Filters {
  q: string;
  status: string | null;
  topic: string | null;
}

export interface Pagination {
  page: number;
  pageSize: number;
}

export interface BulkOperationResult {
  paper_id: string;
  ok: boolean;
  error?: string;
}

export interface BulkDeleteResponse {
  ok: boolean;
  total: number;
  succeeded: number;
  failed: number;
  results: BulkOperationResult[];
}

export interface BulkRebuildResponse {
  ok: boolean;
  total: number;
  succeeded: number;
  failed: number;
  results: BulkOperationResult[];
}

export interface VectorBackendState {
  backend_name: string;
  status: 'healthy' | 'missing' | 'degraded';
  metadata?: {
    collection_count?: number;
    vector_count?: number;
    requires_rebuild?: boolean;
  };
}

export interface LibraryStats {
  total: number;
  ready: number;
  failed: number;
  processing: number;
  topics: Record<string, number>;
  vectorBackend: VectorBackendState | null;
}

export type PaperStatus = Paper['status'];

export const statusStyles: Record<PaperStatus, { border: string; bg: string; label: string; icon: string }> = {
  imported: { border: 'border-slate-200', bg: 'bg-slate-50', label: '已导入', icon: '📥' },
  parsed: { border: 'border-sky-200', bg: 'bg-sky-50', label: '解析中', icon: '⏳' },
  cleaned: { border: 'border-blue-200', bg: 'bg-blue-50', label: '已清洗', icon: '🧹' },
  ready: { border: 'border-emerald-200', bg: 'bg-emerald-50', label: '就绪', icon: '✅' },
  failed: { border: 'border-rose-200', bg: 'bg-rose-50', label: '失败', icon: '⚠️' },
  rebuild_pending: { border: 'border-amber-200', bg: 'bg-amber-50', label: '待重建', icon: '🔄' },
  deleted: { border: 'border-slate-200', bg: 'bg-slate-50', label: '已删除', icon: '🗑️' },
};

export const statusOptions = [
  { value: '', label: '全部状态' },
  { value: 'ready', label: '就绪' },
  { value: 'parsed', label: '解析中' },
  { value: 'failed', label: '失败' },
  { value: 'rebuild_pending', label: '待重建' },
  { value: 'deleted', label: '已删除' },
];
