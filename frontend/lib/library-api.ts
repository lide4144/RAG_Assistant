import { fetchAdminJson } from './admin-http';
import { resolveKernelApiUrl } from './deployment-endpoints';
import type {
  Paper,
  BulkDeleteResponse,
  BulkRebuildResponse,
  VectorBackendState
} from '../types/library';

export interface ListPapersParams {
  limit?: number;
  status?: string;
  topic?: string;
  q?: string;
}

export async function listPapers(params: ListPapersParams = {}): Promise<Paper[]> {
  const searchParams = new URLSearchParams();
  if (params.limit) searchParams.set('limit', String(params.limit));
  if (params.status) searchParams.set('status', params.status);
  if (params.topic) searchParams.set('topic', params.topic);
  if (params.q) searchParams.set('q', params.q);

  const queryString = searchParams.toString();
  const url = resolveKernelApiUrl(`/api/library/papers${queryString ? `?${queryString}` : ''}`);

  const result = await fetchAdminJson<Paper[]>(url);
  if (!result.ok) {
    throw new Error(result.message);
  }
  return result.data;
}

export async function getPaper(paperId: string): Promise<Paper> {
  const url = resolveKernelApiUrl(`/api/library/papers/${encodeURIComponent(paperId)}`);
  const result = await fetchAdminJson<Paper>(url);
  if (!result.ok) {
    throw new Error(result.message);
  }
  return result.data;
}

export async function deletePaper(paperId: string): Promise<{ ok: boolean; message: string }> {
  const url = resolveKernelApiUrl(`/api/library/papers/${encodeURIComponent(paperId)}/delete`);
  const result = await fetchAdminJson<{ ok: boolean; message: string }>(url, {
    method: 'POST',
  });
  if (!result.ok) {
    throw new Error(result.message);
  }
  return result.data;
}

export async function rebuildPaper(paperId: string): Promise<{ ok: boolean; message: string }> {
  const url = resolveKernelApiUrl(`/api/library/papers/${encodeURIComponent(paperId)}/rebuild`);
  const result = await fetchAdminJson<{ ok: boolean; message: string }>(url, {
    method: 'POST',
  });
  if (!result.ok) {
    throw new Error(result.message);
  }
  return result.data;
}

export async function retryPaper(paperId: string): Promise<{ ok: boolean; message: string }> {
  const url = resolveKernelApiUrl(`/api/library/papers/${encodeURIComponent(paperId)}/retry`);
  const result = await fetchAdminJson<{ ok: boolean; message: string }>(url, {
    method: 'POST',
  });
  if (!result.ok) {
    throw new Error(result.message);
  }
  return result.data;
}

export async function bulkDeletePapers(paperIds: string[]): Promise<BulkDeleteResponse> {
  const url = resolveKernelApiUrl('/api/library/papers/bulk-delete');
  const result = await fetchAdminJson<BulkDeleteResponse>(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ paper_ids: paperIds }),
  });
  if (!result.ok) {
    throw new Error(result.message);
  }
  return result.data;
}

export async function bulkRebuildPapers(paperIds: string[]): Promise<BulkRebuildResponse> {
  const url = resolveKernelApiUrl('/api/library/papers/execute-rebuild');
  const result = await fetchAdminJson<BulkRebuildResponse>(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(paperIds),
  });
  if (!result.ok) {
    throw new Error(result.message);
  }
  return result.data;
}

export async function getVectorBackendState(): Promise<VectorBackendState> {
  const url = resolveKernelApiUrl('/api/library/vector-backend');
  const result = await fetchAdminJson<VectorBackendState>(url);
  if (!result.ok) {
    throw new Error(result.message);
  }
  return result.data;
}
