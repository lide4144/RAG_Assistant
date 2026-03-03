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

export async function healthcheckKernel(): Promise<boolean> {
  try {
    const response = await client.get('/health');
    return response.status >= 200 && response.status < 300;
  } catch {
    return false;
  }
}

export async function requestKernelAnswer(payload: KernelChatRequest): Promise<KernelChatResponse> {
  try {
    const response = await client.post<KernelChatResponse>('/qa', payload);
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
  const response = await fetch(`${config.kernelBaseUrl}/qa/stream`, {
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
