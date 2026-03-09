import type { RuntimeLevel } from './types';

export type RuntimeLevelView = {
  label: string;
  icon: string;
  tone: string;
};

export type PipelineStageView = {
  label: string;
  icon: string;
  tone: 'idle' | 'running' | 'success' | 'failed' | 'warning';
};

const runtimeLevelMap: Record<RuntimeLevel, RuntimeLevelView> = {
  READY: { label: '运行正常', icon: '🟢', tone: 'text-emerald-700 bg-emerald-50 border-emerald-200' },
  DEGRADED: { label: '降级运行', icon: '⚠️', tone: 'text-amber-800 bg-amber-50 border-amber-200' },
  BLOCKED: { label: '运行受阻', icon: '⛔', tone: 'text-rose-800 bg-rose-50 border-rose-200' },
  ERROR: { label: '状态异常', icon: '🚨', tone: 'text-slate-700 bg-slate-100 border-slate-300' }
};

const pipelineStateMap: Record<string, PipelineStageView> = {
  not_started: { label: '待处理', icon: '⚪️', tone: 'idle' },
  idle: { label: '待处理', icon: '⚪️', tone: 'idle' },
  queued: { label: '处理中', icon: '🔵', tone: 'running' },
  processing: { label: '处理中', icon: '🔵', tone: 'running' },
  running: { label: '处理中', icon: '🔵', tone: 'running' },
  degraded: { label: '降级完成', icon: '🟠', tone: 'warning' },
  failed_with_fallback: { label: '降级完成', icon: '🟠', tone: 'warning' },
  succeeded: { label: '已完成', icon: '🟢', tone: 'success' },
  success: { label: '已完成', icon: '🟢', tone: 'success' },
  failed: { label: '失败', icon: '🔴', tone: 'failed' },
  cancelled: { label: '已取消', icon: '🟠', tone: 'warning' },
  unknown: { label: '未知', icon: '🟡', tone: 'warning' }
};

export function mapRuntimeLevel(level: RuntimeLevel): RuntimeLevelView {
  return runtimeLevelMap[level] ?? runtimeLevelMap.ERROR;
}

export function mapPipelineStageState(raw: string | null | undefined): PipelineStageView {
  if (!raw) {
    return pipelineStateMap.not_started;
  }
  const normalized = raw.toLowerCase().trim();
  return pipelineStateMap[normalized] ?? pipelineStateMap.unknown;
}

export function mapConnectionStatus(statusText: string): { connected: boolean; label: string } {
  const normalized = statusText.toLowerCase().trim();
  if (normalized === 'connected') {
    return { connected: true, label: '已连接' };
  }
  if (normalized === 'connection error') {
    return { connected: false, label: '连接异常' };
  }
  return { connected: false, label: '未连接' };
}

export function shortRunId(runId: string, keep = 8): string {
  if (!runId) return '-';
  return runId.length <= keep ? runId : `${runId.slice(0, keep)}...`;
}
