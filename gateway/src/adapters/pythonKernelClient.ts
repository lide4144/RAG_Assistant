import axios, { AxiosError } from 'axios';
import { config } from '../config.js';
import { KernelClientError, KernelErrorCode } from '../errors.js';
import type { KernelChatRequest, KernelChatResponse } from '../types/kernel.js';
import type { AgentEvent } from '../types/agent-events.js';

const client = axios.create({
  baseURL: config.kernelBaseUrl,
  timeout: config.requestTimeoutMs,
  headers: {
    'content-type': 'application/json'
  }
});

const PLANNER_QA_PATH = '/planner/qa';
const PLANNER_QA_STREAM_PATH = '/planner/qa/stream';
const LEGACY_QA_PATH = '/qa';
const LEGACY_QA_STREAM_PATH = '/qa/stream';

// Gateway only owns transport compatibility; planner/runtime semantics remain in Python kernel.
function shouldFallbackPlannerRuntime(status: number | undefined): boolean {
  return status === 404 || status === 405 || status === 501 || status === 502 || status === 503;
}

export type KernelStreamEvent =
  | AgentEvent
  | { type: 'message'; traceId: string; mode: 'local' | 'web' | 'hybrid'; content: string }
  | {
      type: 'sources';
      traceId: string;
      mode: 'local' | 'web' | 'hybrid';
      sources: KernelChatResponse['sources'];
    }
  | {
      type: 'messageEnd';
      traceId: string;
      mode: 'local' | 'web' | 'hybrid';
      usage?: { latencyMs: number };
    }
  | { type: 'error'; traceId: string; code: string; message: string };

const allowedModes = new Set(['local', 'web', 'hybrid']);
const allowedToolResultStatuses = new Set(['succeeded', 'failed', 'clarify_required', 'blocked', 'skipped']);
const allowedToolResultKinds = new Set(['final', 'intermediate', 'empty', 'failed', 'clarify_required']);
const allowedFallbackScopes = new Set(['planner', 'tool', 'legacy']);

export type KernelTaskState = 'idle' | 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled';

export interface KernelTaskProgress {
  stage: string;
  processed: number;
  total: number;
  elapsed_ms: number;
  message: string;
}

export interface KernelTaskError {
  stage: string;
  message: string;
  recovery: string;
}

export interface KernelTaskStatus {
  task_id: string;
  task_kind: 'graph_build';
  state: KernelTaskState;
  created_at: string;
  updated_at: string;
  accepted: boolean;
  progress?: KernelTaskProgress;
  error?: KernelTaskError;
  result?: Record<string, unknown>;
}

export async function healthcheckKernel(): Promise<boolean> {
  try {
    const response = await client.get('/health');
    return response.status >= 200 && response.status < 300;
  } catch {
    return false;
  }
}

export async function requestKernelAnswer(payload: KernelChatRequest): Promise<KernelChatResponse> {
  if (payload.mode !== 'local') {
    return requestKernelAnswerLegacy(payload);
  }
  try {
    const response = await client.post<KernelChatResponse>(PLANNER_QA_PATH, payload);
    if (!response.data?.answer || !Array.isArray(response.data?.sources)) {
      throw new KernelClientError(
        KernelErrorCode.BAD_RESPONSE,
        'Kernel response missing required fields',
        response.status
      );
    }
    return response.data;
  } catch (error) {
    if (error instanceof KernelClientError) {
      throw error;
    }

    if (error instanceof AxiosError) {
      if (shouldFallbackPlannerRuntime(error.response?.status)) {
        return requestKernelAnswerLegacy(payload);
      }
      if (error.code === 'ECONNABORTED') {
        throw new KernelClientError(KernelErrorCode.TIMEOUT, 'Kernel request timed out');
      }
      if (error.response) {
        throw new KernelClientError(
          KernelErrorCode.BAD_RESPONSE,
          `Kernel returned ${error.response.status}`,
          error.response.status
        );
      }
      throw new KernelClientError(KernelErrorCode.NETWORK, 'Kernel request failed due to network error');
    }

    throw new KernelClientError(KernelErrorCode.UNKNOWN, 'Kernel request failed with unknown error');
  }
}

async function requestKernelAnswerLegacy(payload: KernelChatRequest): Promise<KernelChatResponse> {
  try {
    const response = await client.post<KernelChatResponse>(LEGACY_QA_PATH, payload);
    if (!response.data?.answer || !Array.isArray(response.data?.sources)) {
      throw new KernelClientError(
        KernelErrorCode.BAD_RESPONSE,
        'Kernel response missing required fields',
        response.status
      );
    }
    return response.data;
  } catch (error) {
    if (error instanceof KernelClientError) {
      throw error;
    }

    if (error instanceof AxiosError) {
      if (error.code === 'ECONNABORTED') {
        throw new KernelClientError(KernelErrorCode.TIMEOUT, 'Kernel request timed out');
      }
      if (error.response) {
        throw new KernelClientError(
          KernelErrorCode.BAD_RESPONSE,
          `Kernel returned ${error.response.status}`,
          error.response.status
        );
      }
      throw new KernelClientError(KernelErrorCode.NETWORK, 'Kernel request failed due to network error');
    }

    throw new KernelClientError(KernelErrorCode.UNKNOWN, 'Kernel request failed with unknown error');
  }
}

export async function startGraphBuildTask(payload?: {
  input_path?: string;
  output_path?: string;
  threshold?: number;
  top_m?: number;
  include_front_matter?: boolean;
  force_new?: boolean;
  llm_max_concurrency?: number;
}): Promise<KernelTaskStatus> {
  try {
    const response = await client.post<KernelTaskStatus>('/api/tasks/graph-build/start', payload ?? {});
    return response.data;
  } catch (error) {
    if (error instanceof AxiosError) {
      if (error.response) {
        throw new KernelClientError(
          KernelErrorCode.BAD_RESPONSE,
          `Kernel task start returned ${error.response.status}`,
          error.response.status
        );
      }
      throw new KernelClientError(KernelErrorCode.NETWORK, 'Kernel task start failed due to network error');
    }
    throw new KernelClientError(KernelErrorCode.UNKNOWN, 'Kernel task start failed with unknown error');
  }
}

export async function getKernelTaskStatus(taskId: string): Promise<KernelTaskStatus> {
  try {
    const response = await client.get<KernelTaskStatus>(`/api/tasks/${taskId}`);
    return response.data;
  } catch (error) {
    if (error instanceof AxiosError) {
      if (error.response) {
        throw new KernelClientError(
          KernelErrorCode.BAD_RESPONSE,
          `Kernel task status returned ${error.response.status}`,
          error.response.status
        );
      }
      throw new KernelClientError(KernelErrorCode.NETWORK, 'Kernel task status failed due to network error');
    }
    throw new KernelClientError(KernelErrorCode.UNKNOWN, 'Kernel task status failed with unknown error');
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function normalizeMode(value: unknown): 'local' | 'web' | 'hybrid' | null {
  return typeof value === 'string' && allowedModes.has(value) ? (value as 'local' | 'web' | 'hybrid') : null;
}

function normalizeTimestamp(value: unknown): string {
  return typeof value === 'string' && value.trim().length > 0 ? value : new Date(0).toISOString();
}

function normalizeKernelStreamEvent(eventType: string, payload: unknown): KernelStreamEvent | null {
  if (!isRecord(payload)) {
    return null;
  }

  const type = typeof payload.type === 'string' ? payload.type : eventType;
  if (type !== eventType) {
    return null;
  }

  const traceId = typeof payload.traceId === 'string' && payload.traceId.trim().length > 0 ? payload.traceId : null;
  if (!traceId && type !== 'error') {
    return null;
  }

  if (type === 'error') {
    return {
      type: 'error',
      traceId: traceId ?? 'unknown',
      code: typeof payload.code === 'string' && payload.code.trim().length > 0 ? payload.code : 'KERNEL_BAD_RESPONSE',
      message: typeof payload.message === 'string' && payload.message.trim().length > 0 ? payload.message : 'Kernel error'
    };
  }

  const mode = normalizeMode(payload.mode);
  if (!mode || !traceId) {
    return null;
  }

  if (type === 'message') {
    if (typeof payload.content !== 'string') {
      return null;
    }
    return { type: 'message', traceId, mode, content: payload.content };
  }

  if (type === 'sources') {
    if (!Array.isArray(payload.sources)) {
      return null;
    }
    return {
      type: 'sources',
      traceId,
      mode,
      sources: payload.sources as KernelChatResponse['sources']
    };
  }

  if (type === 'messageEnd') {
    const usage = isRecord(payload.usage) && typeof payload.usage.latencyMs === 'number'
      ? { latencyMs: payload.usage.latencyMs }
      : undefined;
    return {
      type: 'messageEnd',
      traceId,
      mode,
      usage
    };
  }

  if (type === 'planning') {
    const plannerSource =
      typeof payload.plannerSource === 'string' && ['rule', 'llm', 'fallback'].includes(payload.plannerSource)
        ? (payload.plannerSource as 'rule' | 'llm' | 'fallback')
        : undefined;
    const plannerSourceMode =
      typeof payload.plannerSourceMode === 'string' &&
      ['rule_only', 'shadow_compare', 'llm_primary_with_rule_fallback'].includes(payload.plannerSourceMode)
        ? (payload.plannerSourceMode as 'rule_only' | 'shadow_compare' | 'llm_primary_with_rule_fallback')
        : undefined;
    const executionSource =
      typeof payload.executionSource === 'string' && ['rule', 'llm', 'fallback'].includes(payload.executionSource)
        ? (payload.executionSource as 'rule' | 'llm' | 'fallback')
        : undefined;
    return {
      type: 'planning',
      traceId,
      mode,
      timestamp: normalizeTimestamp(payload.timestamp),
      phase: 'planning',
      decisionResult: typeof payload.decisionResult === 'string' ? payload.decisionResult : undefined,
      selectedPath: typeof payload.selectedPath === 'string' ? payload.selectedPath : undefined,
      selectedToolsOrSkills: Array.isArray(payload.selectedToolsOrSkills)
        ? payload.selectedToolsOrSkills.filter((item): item is string => typeof item === 'string' && item.trim().length > 0)
        : undefined,
      plannerSource,
      plannerSourceMode,
      executionSource
    };
  }

  if (type === 'toolSelection') {
    const toolName = typeof payload.toolName === 'string' && payload.toolName.trim().length > 0 ? payload.toolName : null;
    const callId = typeof payload.callId === 'string' && payload.callId.trim().length > 0 ? payload.callId : null;
    if (!toolName || !callId) {
      return null;
    }
    return {
      type: 'toolSelection',
      traceId,
      mode,
      timestamp: normalizeTimestamp(payload.timestamp),
      toolName,
      callId,
      status: 'selected'
    };
  }

  if (type === 'toolRunning') {
    const toolName = typeof payload.toolName === 'string' && payload.toolName.trim().length > 0 ? payload.toolName : null;
    const callId = typeof payload.callId === 'string' && payload.callId.trim().length > 0 ? payload.callId : null;
    if (!toolName || !callId) {
      return null;
    }
    return {
      type: 'toolRunning',
      traceId,
      mode,
      timestamp: normalizeTimestamp(payload.timestamp),
      toolName,
      callId,
      status: 'running'
    };
  }

  if (type === 'toolResult') {
    const toolName = typeof payload.toolName === 'string' && payload.toolName.trim().length > 0 ? payload.toolName : null;
    const callId = typeof payload.callId === 'string' && payload.callId.trim().length > 0 ? payload.callId : null;
    const status =
      typeof payload.status === 'string' && allowedToolResultStatuses.has(payload.status) ? payload.status : null;
    if (!toolName || !callId || !status) {
      return null;
    }
    return {
      type: 'toolResult',
      traceId,
      mode,
      timestamp: normalizeTimestamp(payload.timestamp),
      toolName,
      callId,
      status: status as 'succeeded' | 'failed' | 'clarify_required' | 'blocked' | 'skipped',
      resultKind:
        typeof payload.resultKind === 'string' && allowedToolResultKinds.has(payload.resultKind)
          ? (payload.resultKind as 'final' | 'intermediate' | 'empty' | 'failed' | 'clarify_required')
          : undefined,
      message: typeof payload.message === 'string' ? payload.message : undefined
    };
  }

  if (type === 'fallback') {
    const fallbackScope =
      typeof payload.fallbackScope === 'string' && allowedFallbackScopes.has(payload.fallbackScope)
        ? payload.fallbackScope
        : null;
    const reasonCode = typeof payload.reasonCode === 'string' && payload.reasonCode.trim().length > 0 ? payload.reasonCode : null;
    if (!fallbackScope || !reasonCode || typeof payload.continues !== 'boolean') {
      return null;
    }
    return {
      type: 'fallback',
      traceId,
      mode,
      timestamp: normalizeTimestamp(payload.timestamp),
      fallbackScope: fallbackScope as 'planner' | 'tool' | 'legacy',
      reasonCode,
      failedTool: typeof payload.failedTool === 'string' ? payload.failedTool : undefined,
      continues: payload.continues,
      message: typeof payload.message === 'string' ? payload.message : undefined
    };
  }

  return null;
}

function parseSseData(buffer: string): { consumed: number; events: KernelStreamEvent[] } {
  const events: KernelStreamEvent[] = [];
  let consumed = 0;

  while (true) {
    const boundary = buffer.indexOf('\n\n', consumed);
    if (boundary === -1) {
      break;
    }
    const frame = buffer.slice(consumed, boundary);
    consumed = boundary + 2;

    const lines = frame.split('\n');
    let eventType = '';
    const dataLines: string[] = [];

    for (const line of lines) {
      if (line.startsWith('event:')) {
        eventType = line.slice('event:'.length).trim();
      } else if (line.startsWith('data:')) {
        dataLines.push(line.slice('data:'.length).trim());
      }
    }

    if (!eventType || dataLines.length === 0) {
      continue;
    }

    try {
      const parsed = JSON.parse(dataLines.join('\n')) as unknown;
      const normalized = normalizeKernelStreamEvent(eventType, parsed);
      if (normalized) {
        events.push(normalized);
      }
    } catch {
      events.push({
        type: 'error',
        traceId: 'unknown',
        code: 'KERNEL_BAD_RESPONSE',
        message: `Invalid SSE payload for event ${eventType}`
      });
    }
  }

  return { consumed, events };
}

export async function streamKernelAnswer(
  payload: KernelChatRequest,
  onEvent: (event: KernelStreamEvent) => void
): Promise<void> {
  if (payload.mode !== 'local') {
    return streamKernelAnswerLegacy(payload, onEvent);
  }
  let response = await fetch(`${config.kernelBaseUrl}${PLANNER_QA_STREAM_PATH}`, {
    method: 'POST',
    headers: {
      'content-type': 'application/json'
    },
    body: JSON.stringify(payload)
  });

  if ((!response.ok || !response.body) && shouldFallbackPlannerRuntime(response.status)) {
    response = await fetch(`${config.kernelBaseUrl}${LEGACY_QA_STREAM_PATH}`, {
      method: 'POST',
      headers: {
        'content-type': 'application/json'
      },
      body: JSON.stringify(payload)
    });
  }

  if (!response.ok || !response.body) {
    throw new KernelClientError(
      KernelErrorCode.BAD_RESPONSE,
      `Kernel stream returned ${response.status}`,
      response.status
    );
  }

  const decoder = new TextDecoder();
  const reader = response.body.getReader();
  let buffer = '';

  while (true) {
    const { value, done } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });

    const parsed = parseSseData(buffer);
    buffer = buffer.slice(parsed.consumed);
    for (const event of parsed.events) {
      onEvent(event);
      if (event.type === 'error') {
        return;
      }
    }
  }

  if (buffer.trim()) {
    const parsed = parseSseData(`${buffer}\n\n`);
    for (const event of parsed.events) {
      onEvent(event);
    }
  }
}

async function streamKernelAnswerLegacy(
  payload: KernelChatRequest,
  onEvent: (event: KernelStreamEvent) => void
): Promise<void> {
  const response = await fetch(`${config.kernelBaseUrl}${LEGACY_QA_STREAM_PATH}`, {
    method: 'POST',
    headers: {
      'content-type': 'application/json'
    },
    body: JSON.stringify(payload)
  });

  if (!response.ok || !response.body) {
    throw new KernelClientError(
      KernelErrorCode.BAD_RESPONSE,
      `Kernel stream returned ${response.status}`,
      response.status
    );
  }

  const decoder = new TextDecoder();
  const reader = response.body.getReader();
  let buffer = '';

  while (true) {
    const { value, done } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });

    const parsed = parseSseData(buffer);
    buffer = buffer.slice(parsed.consumed);
    for (const event of parsed.events) {
      onEvent(event);
      if (event.type === 'error') {
        return;
      }
    }
  }

  if (buffer.trim()) {
    const parsed = parseSseData(`${buffer}\n\n`);
    for (const event of parsed.events) {
      onEvent(event);
    }
  }
}
