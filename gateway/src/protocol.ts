import type { KernelSource } from './types/kernel.js';
import type { ClientChatRequestEvent } from './types/events.js';

const allowedModes = new Set(['local', 'web', 'hybrid']);

export function parseClientEvent(raw: string): ClientChatRequestEvent {
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    throw new Error('Client event must be valid JSON');
  }

  if (!parsed || typeof parsed !== 'object') {
    throw new Error('Client event must be an object');
  }

  const maybeEvent = parsed as Partial<ClientChatRequestEvent>;
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
