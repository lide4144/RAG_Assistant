import type { KernelSource } from './types/kernel.js';
import type { ClientInboundEvent, ClientChatRequestEvent, ClientJobSubscribeEvent, ClientTaskStartGraphBuildEvent } from './types/events.js';

const allowedModes = new Set(['local', 'web', 'hybrid']);

function parseChatEvent(maybeEvent: Partial<ClientChatRequestEvent>): ClientChatRequestEvent {
  if (maybeEvent.type !== 'chat' || !maybeEvent.payload) {
    throw new Error('Client event must use type=chat and include payload');
  }

  const { sessionId, mode, query, history } = maybeEvent.payload;
  if (!sessionId || typeof sessionId !== 'string') {
    throw new Error('payload.sessionId is required');
  }
  if (!mode || typeof mode !== 'string' || !allowedModes.has(mode)) {
    throw new Error('payload.mode must be one of local/web/hybrid');
  }
  if (!query || typeof query !== 'string') {
    throw new Error('payload.query is required');
  }

  return {
    type: 'chat',
    payload: {
      sessionId,
      mode,
      query,
      history
    }
  };
}

function parseTaskStartEvent(maybeEvent: Partial<ClientTaskStartGraphBuildEvent>): ClientTaskStartGraphBuildEvent {
  const payload = maybeEvent.payload ?? {};
  if (payload && typeof payload !== 'object') {
    throw new Error('payload for task_start_graph_build must be an object');
  }
  return {
    type: 'task_start_graph_build',
    payload: payload as ClientTaskStartGraphBuildEvent['payload']
  };
}

function parseJobSubscribeEvent(maybeEvent: Partial<ClientJobSubscribeEvent>): ClientJobSubscribeEvent {
  if (maybeEvent.type !== 'job_subscribe' || !maybeEvent.payload) {
    throw new Error('Client event must use type=job_subscribe and include payload');
  }
  const { jobId, afterSeq } = maybeEvent.payload;
  if (!jobId || typeof jobId !== 'string') {
    throw new Error('payload.jobId is required');
  }
  if (afterSeq !== undefined && (!Number.isInteger(afterSeq) || afterSeq < 0)) {
    throw new Error('payload.afterSeq must be a non-negative integer');
  }
  return {
    type: 'job_subscribe',
    payload: {
      jobId,
      afterSeq
    }
  };
}

export function parseClientEvent(raw: string): ClientInboundEvent {
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    throw new Error('Client event must be valid JSON');
  }

  if (!parsed || typeof parsed !== 'object') {
    throw new Error('Client event must be an object');
  }

  const maybeEvent = parsed as Partial<ClientInboundEvent>;
  if (maybeEvent.type === 'chat') {
    return parseChatEvent(maybeEvent as Partial<ClientChatRequestEvent>);
  }
  if (maybeEvent.type === 'task_start_graph_build') {
    return parseTaskStartEvent(maybeEvent as Partial<ClientTaskStartGraphBuildEvent>);
  }
  if (maybeEvent.type === 'job_subscribe') {
    return parseJobSubscribeEvent(maybeEvent as Partial<ClientJobSubscribeEvent>);
  }
  throw new Error('Client event type must be chat, task_start_graph_build, or job_subscribe');
}

export function normalizeSources(sources: KernelSource[]): KernelSource[] {
  return sources.map((source, index) => ({
    source_type: source.source_type,
    source_id: source.source_id || `source-${index + 1}`,
    title: source.title || 'Untitled source',
    snippet: source.snippet || '',
    locator: source.locator || source.source_id || `item-${index + 1}`,
    score: Number.isFinite(source.score) ? source.score : 0
  }));
}
