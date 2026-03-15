import axios, { AxiosError } from 'axios';
import { config } from '../config.js';
import { KernelClientError, KernelErrorCode } from '../errors.js';
import type { KernelChatRequest, KernelChatResponse } from '../types/kernel.js';

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
      const parsed = JSON.parse(dataLines.join('\n')) as KernelStreamEvent;
      events.push(parsed);
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
