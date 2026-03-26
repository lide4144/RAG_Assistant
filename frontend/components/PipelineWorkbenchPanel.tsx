'use client';

import { Check, Copy } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { fetchAdminJson } from '../lib/admin-http';
import { resolveKernelApiUrl } from '../lib/deployment-endpoints';
import { NumberTicker } from './number-ticker';
import { mapConnectionStatus, mapPipelineStageState, shortRunId } from '../lib/status-mapper';
import { MarkerArtifactPanel } from './marker-artifact-panel';
import type { MarkerArtifactItem } from '../lib/types';

export type PipelineTaskState = 'idle' | 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled';

export interface PipelineTaskPanelState {
  taskId: string;
  state: PipelineTaskState;
  stage: string;
  processed: number;
  total: number;
  elapsedMs: number;
  message: string;
  updatedAt: string;
  accepted?: boolean;
  error?: { stage: string; message: string; recovery: string };
  result?: Record<string, unknown>;
  batchTotal?: number | null;
  batchCompleted?: number | null;
  batchRunning?: number | null;
  batchFailed?: number | null;
  currentStage?: string | null;
  currentItemName?: string | null;
  stageProcessed?: number | null;
  stageTotal?: number | null;
  recentItems?: Array<{ name: string; state: string; stage: string; message: string }>;
}

interface ImportLatestResult {
  added: number;
  skipped: number;
  failed: number;
  total_papers: number;
  failure_reasons: string[];
  pipeline_stages: Array<{
    stage: 'import' | 'clean' | 'index' | 'graph_build';
    state: string;
    updated_at?: string | null;
    message?: string | null;
    detail?: string | null;
  }>;
  report_path?: string | null;
  updated_at?: string | null;
  degraded?: boolean;
  fallback_reason?: string | null;
  fallback_path?: string | null;
  confidence_note?: string | null;
  parser_diagnostics?: Array<{
    paper_id: string;
    source_uri: string;
    parser_engine: string;
    parser_fallback: boolean;
    parser_fallback_stage?: string | null;
    parser_fallback_reason?: string | null;
    marker_attempt_duration_sec?: number;
    marker_stage_timings?: Record<string, number>;
  }>;
  artifact_summary?: {
    counts?: Partial<Record<'healthy' | 'missing' | 'stale', number>>;
  };
  batch_total?: number | null;
  batch_completed?: number | null;
  batch_running?: number | null;
  batch_failed?: number | null;
  current_stage?: string | null;
  current_item_name?: string | null;
  stage_processed?: number | null;
  stage_total?: number | null;
  recent_items?: Array<{
    name: string;
    state: string;
    stage: string;
    message: string;
  }>;
}

interface ImportHistoryItem {
  run_id: string;
  updated_at: string;
  added: number;
  skipped: number;
  failed: number;
  total_candidates: number;
  report_path: string;
}

interface LibraryImportSubmitResponse {
  ok: boolean;
  message?: string;
  task_id?: string | null;
  task_state?: PipelineTaskState | null;
  accepted?: boolean | null;
}

interface BackendTaskStatus {
  task_id: string;
  task_kind: 'graph_build' | 'library_import';
  state: PipelineTaskState;
  updated_at: string;
  message?: string;
  accepted?: boolean;
  progress?: {
    stage: string;
    processed: number;
    total: number;
    elapsed_ms: number;
    message: string;
    batch_total?: number | null;
    batch_completed?: number | null;
    batch_running?: number | null;
    batch_failed?: number | null;
    current_stage?: string | null;
    current_item_name?: string | null;
    stage_processed?: number | null;
    stage_total?: number | null;
    recent_items?: Array<{
      name: string;
      state: string;
      stage: string;
      message: string;
    }>;
  } | null;
  error?: {
    stage: string;
    message: string;
    recovery: string;
  } | null;
  result?: Record<string, unknown> | null;
}

interface MarkerArtifactsResponse {
  items: MarkerArtifactItem[];
  summary?: {
    counts?: Partial<Record<'healthy' | 'missing' | 'stale', number>>;
  };
}

interface PipelineWorkbenchPanelProps {
  statusText: string;
  taskPanel: PipelineTaskPanelState | null;
  onStartGraphBuild: (options?: { llmMaxConcurrency?: number }) => void;
  onRetryGraphBuild: (options?: { llmMaxConcurrency?: number }) => void;
  onCancelGraphBuild: () => void;
  onGoChat: () => void;
}

function stageStateFromTaskState(state: PipelineTaskState): string {
  if (state === 'running' || state === 'queued') return 'running';
  if (state === 'succeeded') return 'succeeded';
  if (state === 'failed' || state === 'cancelled') return 'failed';
  return 'idle';
}

type ImportRecentItem = { name: string; state: string; stage: string; message: string };

function resolveImportPipelineStage(raw?: string | null): 'import' | 'clean' | 'index' | 'graph_build' | null {
  const value = String(raw ?? '').toLowerCase();
  if (!value) return null;
  if (['queued', 'import_validate', 'import_prepare', 'topic_assign', 'done'].includes(value)) return 'import';
  if (['import_clean', 'clean'].includes(value)) return 'clean';
  if (['index_build', 'index'].includes(value)) return 'index';
  if (value.includes('graph')) return 'graph_build';
  return null;
}

function normalizeImportRecentItems(items: unknown): ImportRecentItem[] {
  if (!Array.isArray(items)) return [];
  return items
    .filter((item) => item && typeof item === 'object')
    .map((item) => ({
      name: String((item as { name?: string }).name ?? '').trim(),
      state: String((item as { state?: string }).state ?? 'queued').trim() || 'queued',
      stage: String((item as { stage?: string }).stage ?? 'queued').trim() || 'queued',
      message: String((item as { message?: string }).message ?? '').trim()
    }))
    .filter((item) => item.name);
}

export function PipelineWorkbenchPanel({
  statusText,
  taskPanel,
  onStartGraphBuild,
  onRetryGraphBuild,
  onCancelGraphBuild,
  onGoChat
}: PipelineWorkbenchPanelProps) {
  const persistKey = 'pipeline-workbench-ui-v1';
  const terminalRef = useRef<HTMLPreElement | null>(null);
  const [importResult, setImportResult] = useState<ImportLatestResult | null>(null);
  const [importHistory, setImportHistory] = useState<ImportHistoryItem[]>([]);
  const [importLoading, setImportLoading] = useState(false);
  const [importError, setImportError] = useState('');
  const [importTopic, setImportTopic] = useState('');
  const [importDir, setImportDir] = useState('data/papers');
  const [importFiles, setImportFiles] = useState<File[]>([]);
  const [importSubmitLoading, setImportSubmitLoading] = useState(false);
  const [importSubmitMessage, setImportSubmitMessage] = useState('');
  const [importTaskId, setImportTaskId] = useState('');
  const [importTaskState, setImportTaskState] = useState<PipelineTaskState | null>(null);
  const [importTaskSnapshot, setImportTaskSnapshot] = useState<BackendTaskStatus | null>(null);
  const [artifactItems, setArtifactItems] = useState<MarkerArtifactItem[]>([]);
  const [artifactActionMessage, setArtifactActionMessage] = useState('');
  const [llmConcurrency, setLlmConcurrency] = useState(8);
  const [terminalFilter, setTerminalFilter] = useState('');
  const [terminalScrollTop, setTerminalScrollTop] = useState(0);
  const [terminalLogs, setTerminalLogs] = useState<string[]>([]);
  const [copiedRunId, setCopiedRunId] = useState('');
  const importBusyEventName = 'pipeline-import-busy';

  const formatTime = (raw?: string | null): string => {
    if (!raw) return '-';
    const date = new Date(raw);
    if (Number.isNaN(date.getTime())) return raw;
    return date.toLocaleString();
  };

  const stageMap = useMemo(() => {
    const entries = importResult?.pipeline_stages ?? [];
    const map = new Map<string, { state: string; message?: string | null; detail?: string | null; updated_at?: string | null }>();
    for (const entry of entries) {
      map.set(entry.stage, entry);
    }
    return map;
  }, [importResult?.pipeline_stages]);
  const liveStageMap = useMemo(() => {
    const next = new Map(stageMap);
    const importStageKey = resolveImportPipelineStage(importTaskSnapshot?.progress?.current_stage ?? importTaskSnapshot?.progress?.stage);
    if (importStageKey && importTaskSnapshot) {
      next.set(importStageKey, {
        state: stageStateFromTaskState(importTaskSnapshot.state),
        message: importTaskSnapshot.progress?.message ?? importTaskSnapshot.error?.message ?? importTaskSnapshot.message,
        updated_at: importTaskSnapshot.updated_at
      });
    }
    if (!taskPanel) {
      return next;
    }
    next.set('graph_build', {
      state: stageStateFromTaskState(taskPanel.state),
      message: taskPanel.message,
      updated_at: taskPanel.updatedAt
    });
    return next;
  }, [stageMap, taskPanel]);

  const libraryImportProgress = useMemo(() => {
    const progress = importTaskSnapshot?.progress;
    if (progress) {
      return {
        batchTotal: progress.batch_total ?? null,
        batchCompleted: progress.batch_completed ?? null,
        batchRunning: progress.batch_running ?? null,
        batchFailed: progress.batch_failed ?? null,
        currentStage: progress.current_stage ?? progress.stage,
        currentItemName: progress.current_item_name ?? null,
        stageProcessed: progress.stage_processed ?? progress.processed ?? null,
        stageTotal: progress.stage_total ?? progress.total ?? null,
        recentItems: normalizeImportRecentItems(progress.recent_items),
        message: progress.message ?? '',
        updatedAt: importTaskSnapshot.updated_at
      };
    }
    if (!importResult) {
      return null;
    }
    return {
      batchTotal: importResult.batch_total ?? null,
      batchCompleted: importResult.batch_completed ?? null,
      batchRunning: importResult.batch_running ?? null,
      batchFailed: importResult.batch_failed ?? null,
      currentStage: importResult.current_stage ?? null,
      currentItemName: importResult.current_item_name ?? null,
      stageProcessed: importResult.stage_processed ?? null,
      stageTotal: importResult.stage_total ?? null,
      recentItems: importResult.recent_items ?? [],
      message: importSubmitMessage || '',
      updatedAt: importResult.updated_at ?? null
    };
  }, [importResult, importSubmitMessage, importTaskSnapshot]);

  const taskProgressPercent = useMemo(() => {
    if (!taskPanel || taskPanel.total <= 0) {
      return 0;
    }
    return Math.max(0, Math.min(100, Math.round((taskPanel.processed / taskPanel.total) * 100)));
  }, [taskPanel]);
  const batchProgressKnown =
    libraryImportProgress?.batchTotal !== null &&
    libraryImportProgress?.batchTotal !== undefined &&
    (libraryImportProgress.batchTotal ?? 0) > 0 &&
    libraryImportProgress.batchCompleted !== null &&
    libraryImportProgress.batchFailed !== null &&
    libraryImportProgress.batchRunning !== null;
  const batchProgressPercent = batchProgressKnown
    ? Math.max(
        0,
        Math.min(
          100,
          Math.round((((libraryImportProgress?.batchCompleted ?? 0) + (libraryImportProgress?.batchFailed ?? 0)) / Math.max(1, libraryImportProgress?.batchTotal ?? 1)) * 100)
        )
      )
    : null;
  const showTerminal = taskPanel !== null;

  useEffect(() => {
    if (!taskPanel?.updatedAt) {
      return;
    }
    const line = `[${formatTime(taskPanel.updatedAt)}] [${taskPanel.state.toUpperCase()}] ${taskPanel.stage}: ${taskPanel.message || '状态更新'}`;
    setTerminalLogs((prev) => {
      if (prev[prev.length - 1] === line) {
        return prev;
      }
      return [...prev.slice(-199), line];
    });
  }, [taskPanel?.updatedAt, taskPanel?.message, taskPanel?.stage, taskPanel?.state]);

  const loadLatestImportResult = async () => {
    setImportLoading(true);
    setImportError('');
    try {
      const result = await fetchAdminJson<Partial<ImportLatestResult>>(resolveKernelApiUrl('/api/library/import-latest'));
      if (!result.ok) {
        throw new Error(result.message || '加载导入结果失败');
      }
      const payload = result.data;
      setImportResult({
        added: Number(payload.added ?? 0),
        skipped: Number(payload.skipped ?? 0),
        failed: Number(payload.failed ?? 0),
        total_papers: Number(payload.total_papers ?? 0),
        failure_reasons: Array.isArray(payload.failure_reasons)
          ? payload.failure_reasons.map((item) => String(item))
          : [],
        pipeline_stages: Array.isArray(payload.pipeline_stages)
          ? payload.pipeline_stages
              .filter((item) => item && typeof item === 'object')
              .map((item) => {
                const stage = String((item as { stage?: string }).stage ?? '');
                return {
                  stage:
                    stage === 'import' || stage === 'clean' || stage === 'index' || stage === 'graph_build'
                      ? stage
                      : 'import',
                  state: String((item as { state?: string }).state ?? 'unknown'),
                  updated_at: ((item as { updated_at?: string | null }).updated_at ?? null) as string | null,
                  message: ((item as { message?: string | null }).message ?? null) as string | null,
                  detail: ((item as { detail?: string | null }).detail ?? null) as string | null
                };
              })
          : [],
        report_path: payload.report_path ?? null,
        updated_at: payload.updated_at ?? null,
        degraded: Boolean(payload.degraded),
        fallback_reason: payload.fallback_reason ?? null,
        fallback_path: payload.fallback_path ?? null,
        confidence_note: payload.confidence_note ?? null,
        parser_diagnostics: Array.isArray(payload.parser_diagnostics)
          ? payload.parser_diagnostics
              .filter((item) => item && typeof item === 'object')
              .map((item) => ({
                paper_id: String((item as { paper_id?: string }).paper_id ?? ''),
                source_uri: String((item as { source_uri?: string }).source_uri ?? ''),
                parser_engine: String((item as { parser_engine?: string }).parser_engine ?? 'legacy'),
                parser_fallback: Boolean((item as { parser_fallback?: boolean }).parser_fallback),
                parser_fallback_stage: ((item as { parser_fallback_stage?: string | null }).parser_fallback_stage ?? null) as string | null,
                parser_fallback_reason: ((item as { parser_fallback_reason?: string | null }).parser_fallback_reason ?? null) as string | null,
                marker_attempt_duration_sec: Number((item as { marker_attempt_duration_sec?: number }).marker_attempt_duration_sec ?? 0),
                marker_stage_timings:
                  typeof (item as { marker_stage_timings?: unknown }).marker_stage_timings === 'object' &&
                  (item as { marker_stage_timings?: unknown }).marker_stage_timings !== null
                    ? ((item as { marker_stage_timings?: Record<string, number> }).marker_stage_timings ?? {})
                    : {}
              }))
          : [],
        artifact_summary: payload.artifact_summary ?? {},
        batch_total: payload.batch_total ?? null,
        batch_completed: payload.batch_completed ?? null,
        batch_running: payload.batch_running ?? null,
        batch_failed: payload.batch_failed ?? null,
        current_stage: payload.current_stage ?? null,
        current_item_name: payload.current_item_name ?? null,
        stage_processed: payload.stage_processed ?? null,
        stage_total: payload.stage_total ?? null,
        recent_items: normalizeImportRecentItems(payload.recent_items)
      });
    } catch (error) {
      setImportError(error instanceof Error ? error.message : '加载导入结果失败');
    } finally {
      setImportLoading(false);
    }
  };

  const loadImportHistory = async () => {
    try {
      const result = await fetchAdminJson<ImportHistoryItem[]>(resolveKernelApiUrl('/api/library/import-history?limit=10'));
      if (!result.ok || !Array.isArray(result.data)) {
        return;
      }
      setImportHistory(
        result.data.map((item) => ({
          run_id: String(item.run_id ?? ''),
          updated_at: String(item.updated_at ?? ''),
          added: Number(item.added ?? 0),
          skipped: Number(item.skipped ?? 0),
          failed: Number(item.failed ?? 0),
          total_candidates: Number(item.total_candidates ?? 0),
          report_path: String(item.report_path ?? '')
        }))
      );
    } catch {
      setImportHistory([]);
    }
  };

  const loadMarkerArtifacts = async () => {
    try {
      const result = await fetchAdminJson<MarkerArtifactsResponse>(resolveKernelApiUrl('/api/library/marker-artifacts'));
      if (!result.ok || !Array.isArray(result.data.items)) {
        return;
      }
      setArtifactItems(result.data.items);
    } catch {
      setArtifactItems([]);
    }
  };

  useEffect(() => {
    try {
      const cached = sessionStorage.getItem(persistKey);
      if (!cached) {
        return;
      }
      const parsed = JSON.parse(cached) as {
        importTopic?: unknown;
        importDir?: unknown;
        llmConcurrency?: unknown;
        terminalFilter?: unknown;
        terminalScrollTop?: unknown;
      };
      if (typeof parsed.importTopic === 'string') {
        setImportTopic(parsed.importTopic);
      }
      if (typeof parsed.importDir === 'string') {
        setImportDir(parsed.importDir);
      }
      if (typeof parsed.llmConcurrency === 'number') {
        setLlmConcurrency(Math.max(1, Math.min(32, Math.round(parsed.llmConcurrency))));
      }
      if (typeof parsed.terminalFilter === 'string') {
        setTerminalFilter(parsed.terminalFilter);
      }
      if (typeof parsed.terminalScrollTop === 'number') {
        setTerminalScrollTop(Math.max(0, parsed.terminalScrollTop));
      }
    } catch {
      // ignore invalid persisted state
    }
  }, []);

  useEffect(() => {
    sessionStorage.setItem(
      persistKey,
      JSON.stringify({
        importTopic,
        importDir,
        llmConcurrency,
        terminalFilter,
        terminalScrollTop
      })
    );
  }, [importDir, importTopic, llmConcurrency, terminalFilter, terminalScrollTop]);

  useEffect(() => {
    if (!showTerminal || !terminalRef.current) {
      return;
    }
    terminalRef.current.scrollTop = terminalScrollTop;
  }, [showTerminal, terminalLogs, terminalScrollTop]);

  const filteredTerminalLogs = useMemo(() => {
    const keyword = terminalFilter.trim().toLowerCase();
    if (!keyword) {
      return terminalLogs;
    }
    return terminalLogs.filter((line) => line.toLowerCase().includes(keyword));
  }, [terminalFilter, terminalLogs]);
  const hasVolatileChanges =
    importFiles.length > 0 ||
    importSubmitLoading ||
    importTaskState === 'running' ||
    importTaskState === 'queued' ||
    taskPanel?.state === 'running' ||
    taskPanel?.state === 'queued';

  useEffect(() => {
    if (!importTaskId) {
      return;
    }
    let cancelled = false;
    const poll = async () => {
      try {
        const result = await fetchAdminJson<BackendTaskStatus>(resolveKernelApiUrl(`/api/tasks/${importTaskId}`));
        if (!result.ok) {
          throw new Error(result.message || '加载导入任务状态失败');
        }
        if (cancelled) {
          return;
        }
        const payload = result.data;
        const nextState = payload.state;
        setImportTaskState(nextState);
        setImportTaskSnapshot(payload);
        const progressMessage = payload.progress?.message?.trim() || payload.error?.message?.trim() || payload.message?.trim();
        if (progressMessage) {
          setImportSubmitMessage(progressMessage);
        }
        if (nextState === 'succeeded' || nextState === 'failed' || nextState === 'cancelled') {
          setImportTaskId('');
          await loadLatestImportResult();
          await loadImportHistory();
          await loadMarkerArtifacts();
        }
      } catch (error) {
        if (!cancelled) {
          setImportSubmitMessage(error instanceof Error ? error.message : '加载导入任务状态失败');
          setImportTaskId('');
          setImportTaskState('failed');
        }
      }
    };
    void poll();
    const timer = window.setInterval(() => {
      void poll();
    }, 3000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [importTaskId]);

  useEffect(() => {
    if (!hasVolatileChanges) {
      return;
    }
    const onBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', onBeforeUnload);
    return () => window.removeEventListener('beforeunload', onBeforeUnload);
  }, [hasVolatileChanges]);

  useEffect(() => {
    if (!hasVolatileChanges) {
      return;
    }
    const onDocumentClick = (event: MouseEvent) => {
      const target = event.target as HTMLElement | null;
      const anchor = target?.closest('a[href]') as HTMLAnchorElement | null;
      if (!anchor) {
        return;
      }
      const href = anchor.getAttribute('href') ?? '';
      if (!href.startsWith('/')) {
        return;
      }
      const nextUrl = new URL(href, window.location.origin);
      if (nextUrl.pathname === window.location.pathname) {
        return;
      }
      const shouldLeave = window.confirm('当前存在未完成任务或未提交导入内容，确认离开当前页面吗？');
      if (!shouldLeave) {
        event.preventDefault();
        event.stopPropagation();
      }
    };
    document.addEventListener('click', onDocumentClick, true);
    return () => document.removeEventListener('click', onDocumentClick, true);
  }, [hasVolatileChanges]);

  useEffect(() => {
    void loadLatestImportResult();
    void loadImportHistory();
    void loadMarkerArtifacts();
  }, []);

  useEffect(() => {
    if (taskPanel?.state === 'succeeded') {
      void loadLatestImportResult();
      void loadImportHistory();
      void loadMarkerArtifacts();
    }
  }, [taskPanel?.state]);

  useEffect(() => {
    if (taskPanel?.state !== 'running' && taskPanel?.state !== 'queued') {
      return;
    }
    const timer = window.setInterval(() => {
      void loadLatestImportResult();
    }, 3000);
    return () => window.clearInterval(timer);
  }, [taskPanel?.state]);

  const submitImportFiles = async () => {
    if (!importFiles.length) {
      setImportSubmitMessage('请先选择 PDF 文件。');
      return;
    }
    setImportSubmitLoading(true);
    setImportSubmitMessage('');
    window.dispatchEvent(new CustomEvent(importBusyEventName, { detail: { busy: true } }));

    try {
      const form = new FormData();
      form.append('topic', importTopic.trim());
      for (const file of importFiles) {
        form.append('files', file);
      }
      const result = await fetchAdminJson<LibraryImportSubmitResponse>(resolveKernelApiUrl('/api/library/import'), {
        method: 'POST',
        body: form
      });
      if (!result.ok) {
        const message =
          typeof result.data === 'object' && result.data !== null && 'detail' in result.data
            ? ((result.data as { detail?: { message?: string } }).detail?.message ?? result.message)
            : result.message;
        throw new Error(message || '导入失败');
      }
      const payload = result.data;
      setImportSubmitMessage(payload.message ?? '导入任务已提交。');
      setImportTaskId(payload.task_id ?? '');
      setImportTaskState(payload.task_state ?? 'queued');
      setImportTaskSnapshot(null);
      setImportFiles([]);
    } catch (error) {
      const message =
        error instanceof Error && error.message === 'Failed to fetch'
          ? '上传请求未成功到达服务端，通常是批量文件总体积超过了反向代理上传上限，或上传连接被中途断开。请减少单次文件数，或把服务器上的 NGINX_CLIENT_MAX_BODY_SIZE 调大后重启服务。'
          : error instanceof Error
            ? error.message
            : '导入失败';
      setImportSubmitMessage(message);
      setImportTaskId('');
      setImportTaskState('failed');
      setImportTaskSnapshot(null);
    } finally {
      setImportSubmitLoading(false);
      window.dispatchEvent(new CustomEvent(importBusyEventName, { detail: { busy: false } }));
    }
  };

  const submitImportDir = async () => {
    if (!importDir.trim()) {
      setImportSubmitMessage('请填写目录路径。');
      return;
    }
    setImportSubmitLoading(true);
    setImportSubmitMessage('');
    window.dispatchEvent(new CustomEvent(importBusyEventName, { detail: { busy: true } }));
    try {
      const result = await fetchAdminJson<LibraryImportSubmitResponse>(
        resolveKernelApiUrl('/api/library/import-from-dir'),
        {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source_dir: importDir.trim(), topic: importTopic.trim() })
        }
      );
      if (!result.ok) {
        const message =
          typeof result.data === 'object' && result.data !== null && 'detail' in result.data
            ? ((result.data as { detail?: { message?: string } }).detail?.message ?? result.message)
            : result.message;
        throw new Error(message || '目录导入失败');
      }
      const payload = result.data;
      setImportSubmitMessage(payload.message ?? '目录导入任务已提交。');
      setImportTaskId(payload.task_id ?? '');
      setImportTaskState(payload.task_state ?? 'queued');
    } catch (error) {
      setImportSubmitMessage(error instanceof Error ? error.message : '目录导入失败');
      setImportTaskId('');
      setImportTaskState('failed');
    } finally {
      setImportSubmitLoading(false);
      window.dispatchEvent(new CustomEvent(importBusyEventName, { detail: { busy: false } }));
    }
  };

  const parserDiagnostics = importResult?.parser_diagnostics ?? [];

  const handleCopyArtifactPath = async (path: string) => {
    try {
      await navigator.clipboard.writeText(path);
      setArtifactActionMessage(`已复制路径：${path}`);
      window.setTimeout(() => setArtifactActionMessage(''), 1500);
    } catch {
      setArtifactActionMessage('复制路径失败，请检查浏览器权限。');
    }
  };

  const handleDeleteArtifact = async (item: MarkerArtifactItem) => {
    const deleteAction = item.actions.find((action) => action.kind === 'delete');
    const confirmed = window.confirm(deleteAction?.confirm_message || `确认删除 ${item.file_name} 吗？`);
    if (!confirmed) {
      return;
    }
    try {
      const result = await fetchAdminJson<{ message?: string; detail?: { message?: string } }>(
        resolveKernelApiUrl('/api/library/marker-artifacts/delete'),
        {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key: item.key })
        }
      );
      if (!result.ok) {
        const message =
          typeof result.data === 'object' && result.data !== null && 'detail' in result.data
            ? ((result.data as { detail?: { message?: string } }).detail?.message ?? result.message)
            : result.message;
        throw new Error(message || '删除失败');
      }
      const payload = result.data;
      setArtifactActionMessage(payload.message ?? `${item.file_name} 已删除`);
      await loadMarkerArtifacts();
      await loadLatestImportResult();
    } catch (error) {
      setArtifactActionMessage(error instanceof Error ? error.message : '删除失败');
    }
  };

  const handleRebuildArtifact = (item: MarkerArtifactItem) => {
    if (item.related_stage === 'graph_build') {
      onStartGraphBuild({ llmMaxConcurrency: llmConcurrency });
      setArtifactActionMessage(`已触发 ${item.file_name} 的重建流程。`);
      return;
    }
    setArtifactActionMessage(`请使用导入入口或索引流程重建 ${item.file_name}（关联阶段：${item.related_stage}）。`);
  };

  const bentoCards = [
    { label: '库内论文总数', value: importResult?.total_papers ?? 0, testId: 'pipeline-import-total' },
    { label: '本轮新增', value: importResult?.added ?? 0, testId: 'pipeline-import-added' },
    { label: '重复跳过', value: importResult?.skipped ?? 0, testId: 'pipeline-import-skipped' },
    { label: '失败条目', value: importResult?.failed ?? 0, testId: 'pipeline-import-failed' }
  ];

  const stageOrder: Array<{ key: 'import' | 'clean' | 'index' | 'graph_build'; label: string }> = [
    { key: 'import', label: '导入' },
    { key: 'clean', label: '清洗' },
    { key: 'index', label: '索引' },
    { key: 'graph_build', label: '图构建' }
  ];
  const connection = mapConnectionStatus(statusText);
  const completedStageCount = stageOrder.filter((stage) => {
    const state = liveStageMap.get(stage.key)?.state ?? 'not_started';
    return ['done', 'succeeded', 'completed', 'success'].includes(String(state).toLowerCase());
  }).length;
  const importActiveStageKey =
    importTaskSnapshot && (importTaskSnapshot.state === 'running' || importTaskSnapshot.state === 'queued')
      ? resolveImportPipelineStage(libraryImportProgress?.currentStage)
      : null;
  const activeStageKey =
    importActiveStageKey ??
    stageOrder.find((stage) => {
      const state = String(liveStageMap.get(stage.key)?.state ?? '').toLowerCase();
      return ['running', 'queued', 'processing'].includes(state);
    })?.key ??
    stageOrder.find((stage) => {
      const state = String(liveStageMap.get(stage.key)?.state ?? '').toLowerCase();
      return !['done', 'succeeded', 'completed', 'success'].includes(state);
    })?.key ??
    'graph_build';
  const importSelectedCount = importFiles.length;
  const recentImportItems = libraryImportProgress?.recentItems ?? [];
  const importSummaryLine = batchProgressKnown
    ? `${libraryImportProgress?.batchTotal ?? 0} 篇论文 · 已完成 ${libraryImportProgress?.batchCompleted ?? 0} · 处理中 ${libraryImportProgress?.batchRunning ?? 0} · 失败 ${libraryImportProgress?.batchFailed ?? 0}`
    : importTaskState === 'running' || importTaskState === 'queued'
      ? '任务已受理，正在同步后台导入进度。'
      : '等待下一次导入任务，系统会在拿到真实批次统计后再显示总体进度。';
  const importSummaryBadge = batchProgressKnown
    ? `${libraryImportProgress?.batchCompleted ?? 0}/${libraryImportProgress?.batchTotal ?? 0} 完成`
    : importTaskState === 'running' || importTaskState === 'queued'
      ? '进度同步中'
      : `${completedStageCount}/4 阶段完成`;

  return (
    <section className="glass-card rounded-[34px] p-5 md:p-6">
      <header className="mb-5 flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">知识处理</p>
          <h2 className="mt-2 text-[32px] font-semibold tracking-tight text-slate-950">知识库处理进度中心</h2>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">把“导入、清洗、索引、图构建”拆成用户能读懂的进度流程，避免只看到冷冰冰的待处理状态。</p>
        </div>
        <span className="inline-flex items-center gap-2 rounded-full border border-white/70 bg-white/80 px-3 py-1.5 text-xs text-slate-600 shadow-sm">
          <span
            className={`h-2.5 w-2.5 rounded-full ${connection.connected ? 'bg-emerald-500 shadow-[0_0_10px_rgba(16,185,129,0.65)]' : 'bg-slate-400'}`}
            aria-hidden
          />
          {connection.connected ? '已连接' : '未连接'}
        </span>
      </header>

      <section className="bento-grid mb-5">
        {bentoCards.map((card) => (
          <article
            key={card.label}
            data-testid={card.testId}
            className="rounded-[26px] border border-white/70 bg-[linear-gradient(180deg,rgba(255,255,255,0.96),rgba(248,250,252,0.92))] p-4 shadow-[0_18px_40px_rgba(15,23,42,0.05)]"
          >
            <p className="text-xs font-medium uppercase tracking-[0.14em] text-slate-500">{card.label}</p>
            <NumberTicker value={card.value} className="mt-2 block text-4xl font-semibold tabular-nums text-slate-900" />
          </article>
        ))}
      </section>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.2fr)_minmax(320px,0.8fr)]">
        <section className="rounded-[28px] border border-slate-200 bg-white/90 p-5 shadow-[0_18px_50px_rgba(15,23,42,0.05)]">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h3 className="text-lg font-semibold text-slate-900">导入资料</h3>
              <p className="mt-1 text-sm text-slate-600">支持上传 PDF 或从服务器目录批量导入，系统会自动回填最新处理结果。</p>
            </div>
            <div className="rounded-2xl bg-slate-50 px-4 py-3 text-right">
              <p className="text-[11px] uppercase tracking-[0.14em] text-slate-400">本次提交</p>
              <p className="mt-1 text-2xl font-semibold text-slate-950">{importSelectedCount}</p>
              <p className="text-xs text-slate-500">个文件已选中</p>
            </div>
          </div>
          <div className="mt-4 grid gap-2 md:grid-cols-[2fr_1fr]">
            <input
              type="file"
              multiple
              accept=".pdf,application/pdf"
              onChange={(event) => setImportFiles(Array.from(event.target.files ?? []))}
              className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm"
            />
            <input
              type="text"
              value={importTopic}
              onChange={(event) => setImportTopic(event.target.value)}
              placeholder="专题名（可选）"
              className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm"
            />
          </div>
          <input
            type="text"
            value={importDir}
            onChange={(event) => setImportDir(event.target.value)}
            placeholder="服务器目录，例如 data/papers"
            className="mt-2 w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm"
          />
          <div className="mt-4 flex flex-wrap items-center gap-2">
          <button
            type="button"
            data-testid="pipeline-import-submit-btn"
            onClick={() => void submitImportFiles()}
            disabled={importSubmitLoading}
            className="rounded-2xl bg-slate-950 px-4 py-3 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            {importSubmitLoading ? '导入处理中...' : `开始导入（${importFiles.length} 个文件）`}
          </button>
          <button
            type="button"
            data-testid="pipeline-import-dir-btn"
            onClick={() => void submitImportDir()}
            disabled={importSubmitLoading}
            className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm font-medium text-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {importSubmitLoading ? '目录导入中...' : '从目录批量导入'}
          </button>
          <button
            type="button"
            onClick={() => {
              void loadLatestImportResult();
              void loadImportHistory();
            }}
            className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600"
          >
            刷新状态
          </button>
          </div>
          {importSubmitMessage ? <p className="mt-3 text-sm text-slate-600">{importSubmitMessage}</p> : null}
          {importError ? <p className="mt-3 text-sm text-rose-600">{importError}</p> : null}
          {importResult?.failure_reasons?.length ? (
            <p data-testid="pipeline-import-failure-reasons" className="mt-3 text-sm text-rose-600">
              {importResult.failure_reasons.join('；')}
            </p>
          ) : null}
        </section>

        <section className="rounded-[28px] border border-slate-200 bg-[linear-gradient(180deg,#fffdfa,#ffffff)] p-5 shadow-[0_18px_50px_rgba(15,23,42,0.05)]">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h3 className="text-lg font-semibold text-slate-900">处理状态</h3>
              <p className="mt-1 text-sm text-slate-600">系统会明确告诉你目前走到哪一步，而不是只显示“待处理”。</p>
            </div>
            <span className="rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs font-medium text-emerald-700">
              {importSummaryBadge}
            </span>
          </div>

          <div data-testid="pipeline-batch-summary" className="mt-4 rounded-[22px] border border-slate-200 bg-white p-4">
            <div className="flex items-start justify-between gap-3 text-sm">
              <div>
                <p className="font-medium text-slate-900">
                  {batchProgressKnown ? `本批次已完成 ${libraryImportProgress?.batchCompleted ?? 0}/${libraryImportProgress?.batchTotal ?? 0}` : '批次总体进度'}
                </p>
                <p className="mt-1 text-xs text-slate-500" data-testid="pipeline-batch-summary-text">
                  {importSummaryLine}
                </p>
                {libraryImportProgress?.currentItemName ? (
                  <p className="mt-2 text-xs font-medium text-slate-700">当前处理：{libraryImportProgress.currentItemName}</p>
                ) : null}
              </div>
              <p className="text-right text-2xl font-semibold text-slate-950">
                {batchProgressPercent !== null ? `${batchProgressPercent}%` : '...'}
              </p>
            </div>
            <div className="mt-3 h-3 overflow-hidden rounded-full bg-slate-100" data-testid="pipeline-batch-progress">
              {batchProgressPercent !== null ? (
                <div
                  className="h-full rounded-full bg-[linear-gradient(90deg,#0f766e,#38bdf8,#f59e0b)] transition-all"
                  style={{ width: `${batchProgressPercent}%` }}
                />
              ) : (
                <div className="h-full w-1/3 rounded-full bg-[linear-gradient(90deg,#cbd5e1,#94a3b8,#cbd5e1)] animate-pulse" />
              )}
            </div>
            {!batchProgressKnown ? (
              <p data-testid="pipeline-batch-fallback" className="mt-2 text-[11px] text-amber-700">
                当前响应缺少可靠批次统计，界面已退回阶段级提示，不显示伪精确百分比。
              </p>
            ) : null}
            <div className="mt-4 grid gap-3 sm:grid-cols-4">
              {[
                { label: '已完成', value: libraryImportProgress?.batchCompleted ?? 0 },
                { label: '处理中', value: libraryImportProgress?.batchRunning ?? 0 },
                { label: '失败', value: libraryImportProgress?.batchFailed ?? 0 },
                { label: '阶段内', value: `${libraryImportProgress?.stageProcessed ?? 0}/${libraryImportProgress?.stageTotal ?? 0}` }
              ].map((item) => (
                <article key={item.label} className="rounded-2xl border border-slate-200 bg-slate-50/80 px-3 py-3">
                  <p className="text-[11px] uppercase tracking-[0.14em] text-slate-400">{item.label}</p>
                  <p className="mt-2 text-xl font-semibold tabular-nums text-slate-950">{item.value}</p>
                </article>
              ))}
            </div>
          </div>

          <div data-testid="pipeline-stage-cards" className="mt-4 grid gap-3 md:grid-cols-4">
          {stageOrder.map((stage) => {
            const stageData = liveStageMap.get(stage.key);
            const mapped = mapPipelineStageState(stageData?.state ?? 'not_started');
            const isActive = activeStageKey === stage.key;
            return (
              <article
                key={stage.key}
                className={`relative rounded-[22px] border p-4 transition ${
                  isActive ? 'border-sky-200 bg-sky-50 shadow-[0_18px_32px_rgba(56,189,248,0.12)]' : 'border-slate-200 bg-slate-50/80'
                }`}
              >
                {stage.key !== 'graph_build' ? (
                  <span className="absolute -right-2 top-5 hidden h-[2px] w-4 bg-slate-300 md:block" aria-hidden />
                ) : null}
                <div className="flex items-center gap-2">
                  <span className="text-sm" aria-hidden>
                    {mapped.icon}
                  </span>
                  <span className="text-xs font-semibold text-slate-700">{stage.label}</span>
                </div>
                <p className="mt-2 text-sm font-medium text-slate-900">{mapped.label}</p>
                <p className="mt-1 text-[11px] text-slate-500">{formatTime(stageData?.updated_at)}</p>
                {stageData?.message || stageData?.detail ? (
                  <p className="mt-1 text-[11px] leading-5 text-slate-500">{stageData?.detail || stageData?.message}</p>
                ) : null}
                {isActive && libraryImportProgress?.stageTotal ? (
                  <p className="mt-2 text-[11px] font-medium text-slate-700">
                    当前阶段 {libraryImportProgress.stageProcessed ?? 0}/{libraryImportProgress.stageTotal}
                  </p>
                ) : null}
              </article>
            );
          })}
          </div>

          <div className="mt-4 rounded-[22px] border border-slate-200 bg-slate-50/70 p-4" data-testid="pipeline-recent-items">
            <div className="flex items-center justify-between gap-2">
              <div>
                <h4 className="text-sm font-semibold text-slate-900">单篇论文状态</h4>
                <p className="mt-1 text-xs text-slate-600">优先展示最近处理项、失败项和仍在运行的条目。</p>
              </div>
              {libraryImportProgress?.updatedAt ? (
                <span className="text-[11px] text-slate-500">更新于 {formatTime(libraryImportProgress.updatedAt)}</span>
              ) : null}
            </div>
            {recentImportItems.length ? (
              <div className="mt-3 space-y-2">
                {recentImportItems.map((item) => {
                  const itemState = item.state.toLowerCase();
                  const tone =
                    itemState === 'failed'
                      ? 'border-rose-200 bg-rose-50 text-rose-700'
                      : itemState === 'succeeded'
                        ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                        : 'border-sky-200 bg-sky-50 text-sky-700';
                  return (
                    <article
                      key={`${item.name}-${item.stage}`}
                      className="flex flex-wrap items-start justify-between gap-3 rounded-2xl border border-slate-200 bg-white px-3 py-3"
                    >
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium text-slate-900 [overflow-wrap:anywhere]">{item.name}</p>
                        <p className="mt-1 text-[11px] text-slate-500">{item.message || item.stage}</p>
                      </div>
                      <div className="flex shrink-0 items-center gap-2">
                        <span className="rounded-full border border-slate-200 bg-slate-50 px-2 py-1 text-[11px] text-slate-600">
                          {resolveImportPipelineStage(item.stage) ?? item.stage}
                        </span>
                        <span className={`rounded-full border px-2 py-1 text-[11px] font-medium ${tone}`}>{item.state}</span>
                      </div>
                    </article>
                  );
                })}
              </div>
            ) : (
              <p className="mt-3 text-sm text-slate-500">暂无逐项状态。导入开始后，这里会显示最近处理的论文与失败原因。</p>
            )}
          </div>
        </section>
      </div>

      <MarkerArtifactPanel
        degraded={Boolean(importResult?.degraded)}
        fallbackReason={importResult?.fallback_reason}
        fallbackPath={importResult?.fallback_path}
        confidenceNote={importResult?.confidence_note}
        items={artifactItems}
        actionMessage={artifactActionMessage}
        onCopyPath={(path) => void handleCopyArtifactPath(path)}
        onDeleteArtifact={(item) => void handleDeleteArtifact(item)}
        onRebuildArtifact={handleRebuildArtifact}
      />

      {parserDiagnostics.length ? (
        <section className="mt-4 rounded-2xl border border-slate-200 bg-white p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h3 className="text-sm font-semibold text-slate-900">Marker 解析诊断</h3>
              <p className="mt-1 text-xs text-slate-600">最近一次导入的单篇 PDF 耗时与回退信息，按最慢条目排序。</p>
            </div>
            {importSubmitLoading ? (
              <span className="rounded-full border border-amber-200 bg-amber-50 px-2 py-1 text-[11px] text-amber-700">导入中，已暂停全局运行态轮询</span>
            ) : null}
          </div>
          <div className="mt-3 space-y-2" data-testid="pipeline-parser-diagnostics">
            {parserDiagnostics.map((item) => (
              <article key={`${item.paper_id}-${item.source_uri}`} className="rounded-xl border border-slate-200 bg-slate-50 p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="font-mono text-[11px] text-slate-700">{item.paper_id || item.source_uri || 'unknown-paper'}</p>
                  <span className="text-xs font-medium text-slate-900">{(item.marker_attempt_duration_sec ?? 0).toFixed(3)}s</span>
                </div>
                <p className="mt-1 text-xs text-slate-600">
                  parser: {item.parser_engine}
                  {item.parser_fallback ? ` -> legacy (${item.parser_fallback_stage || 'unknown'})` : ' -> marker'}
                </p>
                {item.parser_fallback_reason ? <p className="mt-1 text-[11px] text-rose-600">{item.parser_fallback_reason}</p> : null}
                {item.marker_stage_timings && Object.keys(item.marker_stage_timings).length ? (
                  <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-slate-500">
                    {Object.entries(item.marker_stage_timings).map(([key, value]) => (
                      <span key={key} className="rounded-full border border-slate-200 bg-white px-2 py-1">
                        {key}: {Number(value).toFixed(3)}s
                      </span>
                    ))}
                  </div>
                ) : null}
              </article>
            ))}
          </div>
        </section>
      ) : null}

      <section className="mt-4 rounded-2xl border border-slate-200 bg-white p-4">
        <h3 className="text-sm font-semibold text-slate-900">图构建任务中心</h3>
        <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-slate-600">
          <label htmlFor="llm-concurrency">实体抽取并发</label>
          <input
            id="llm-concurrency"
            type="number"
            min={1}
            max={32}
            value={llmConcurrency}
            onChange={(event) => setLlmConcurrency(Math.max(1, Math.min(32, Number(event.target.value || 1))))}
            className="w-20 rounded-lg border border-slate-200 px-2 py-1"
          />
          <span className="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-[11px]">当前状态: {taskPanel?.state ?? 'idle'}</span>
        </div>

        <div className="mt-3 flex flex-wrap gap-2">
          <button
            type="button"
            data-testid="pipeline-start-graph-build-btn"
            onClick={() => onStartGraphBuild({ llmMaxConcurrency: llmConcurrency })}
            disabled={taskPanel?.state === 'running' || statusText !== 'Connected'}
            className="rounded-xl bg-sky-600 px-3 py-2 text-xs font-medium text-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            {taskPanel?.state === 'running' ? '运行中...' : '启动 Graph Build'}
          </button>
          {taskPanel?.state === 'failed' ? (
            <button
              type="button"
              data-testid="pipeline-retry-graph-build-btn"
              onClick={() => onRetryGraphBuild({ llmMaxConcurrency: llmConcurrency })}
              disabled={statusText !== 'Connected'}
              className="rounded-xl bg-amber-500 px-3 py-2 text-xs font-medium text-white disabled:cursor-not-allowed disabled:opacity-50"
            >
              重试
            </button>
          ) : null}
          {taskPanel?.state === 'running' ? (
            <button
              type="button"
              data-testid="pipeline-cancel-graph-build-btn"
              onClick={onCancelGraphBuild}
              className="rounded-xl bg-rose-600 px-3 py-2 text-xs font-medium text-white"
            >
              取消
            </button>
          ) : null}
          <button
            type="button"
            data-testid="pipeline-go-chat-btn"
            onClick={onGoChat}
            className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-medium text-slate-700"
          >
            回到对话验证
          </button>
        </div>

        <div className="mt-3 h-2 overflow-hidden rounded bg-slate-100">
          <div className="h-full bg-sky-500 transition-all" style={{ width: `${taskProgressPercent}%` }} />
        </div>
        <div className="mt-1 flex items-center justify-between text-xs text-slate-600">
          <span data-testid="pipeline-progress-text">
            进度: {taskPanel ? `${taskPanel.processed}/${taskPanel.total || 0}` : '0/0'}
          </span>
          <span data-testid="pipeline-elapsed-text">耗时: {taskPanel?.elapsedMs ?? 0}ms</span>
        </div>
        <div className="mt-1 text-xs text-slate-600">
          <span data-testid="pipeline-stage-text">阶段: {taskPanel?.state ?? 'idle'} / {taskPanel?.stage ?? '-'}</span>
        </div>
        {taskPanel?.accepted === false && taskPanel.taskId ? (
          <p data-testid="pipeline-idempotent-hint" className="mt-1 text-xs text-amber-700">
            检测到幂等保护，复用任务 {taskPanel.taskId}
          </p>
        ) : null}
        {taskPanel?.error ? (
          <p className="mt-2 text-xs text-rose-600">
            {taskPanel.error.stage}: {taskPanel.error.message}（{taskPanel.error.recovery}）
          </p>
        ) : null}
      </section>

      <section className="mt-4 rounded-2xl border border-slate-200 bg-slate-950 p-4 text-slate-100">
        <div className="mb-2 flex items-center justify-between">
          <h3 className="text-sm font-semibold">Graph Build 日志流</h3>
          <span className="text-[11px] text-slate-400">{showTerminal ? '终端模式' : '等待任务'}</span>
        </div>
        <input
          type="text"
          value={terminalFilter}
          onChange={(event) => setTerminalFilter(event.target.value)}
          placeholder="按关键字筛选日志（持久化）"
          className="mb-2 w-full rounded-lg border border-slate-800 bg-slate-900 px-3 py-2 text-xs text-slate-200 placeholder:text-slate-500"
        />
        {showTerminal ? (
          <pre
            ref={terminalRef}
            onScroll={(event) => setTerminalScrollTop(event.currentTarget.scrollTop)}
            className="terminal-scrollbar h-52 overflow-auto rounded-xl border border-slate-800 bg-black/40 p-3 font-mono text-xs leading-relaxed"
          >
            {filteredTerminalLogs.length ? filteredTerminalLogs.join('\n') : '暂无日志输出...'}
          </pre>
        ) : (
          <div className="rounded-xl border border-dashed border-slate-700 p-6 text-center text-xs text-slate-400">
            尚未触发 Graph Build 任务，启动后将在此展示实时日志。
          </div>
        )}
      </section>

      <section className="mt-4 rounded-2xl border border-slate-200 bg-white p-4">
        <h3 className="text-sm font-semibold text-slate-900">最近导入记录</h3>
        {importLoading ? <p className="mt-2 text-xs text-slate-500">加载中...</p> : null}
        {importHistory.length ? (
          <div className="mt-2 overflow-x-auto rounded-lg border border-slate-200">
            <table className="min-w-full text-left text-xs">
              <thead className="bg-slate-50 text-slate-600">
                <tr>
                  <th className="px-3 py-2">时间</th>
                  <th className="px-3 py-2">Run</th>
                  <th className="px-3 py-2">候选</th>
                  <th className="px-3 py-2">新增</th>
                  <th className="px-3 py-2">跳过</th>
                  <th className="px-3 py-2">失败</th>
                </tr>
              </thead>
              <tbody>
                {importHistory.map((item) => (
                  <tr key={item.run_id} className="border-t border-slate-100">
                    <td className="px-3 py-2">{formatTime(item.updated_at)}</td>
                    <td className="px-3 py-2">
                      <div className="inline-flex items-center gap-1">
                        <span title={item.run_id} className="font-mono text-[11px] text-slate-700">
                          {shortRunId(item.run_id)}
                        </span>
                        <button
                          type="button"
                          aria-label={`复制 ${item.run_id}`}
                          onClick={async () => {
                            try {
                              await navigator.clipboard.writeText(item.run_id);
                              setCopiedRunId(item.run_id);
                              window.setTimeout(() => setCopiedRunId(''), 1200);
                            } catch {
                              setCopiedRunId('');
                            }
                          }}
                          className="rounded border border-slate-200 p-1 text-slate-500 hover:text-slate-700"
                        >
                          {copiedRunId === item.run_id ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
                        </button>
                      </div>
                    </td>
                    <td className="px-3 py-2">{item.total_candidates}</td>
                    <td className="px-3 py-2">{item.added}</td>
                    <td className="px-3 py-2">{item.skipped}</td>
                    <td className="px-3 py-2">{item.failed}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          !importLoading && <p className="mt-2 text-xs text-slate-500">暂无历史记录</p>
        )}
      </section>
    </section>
  );
}
