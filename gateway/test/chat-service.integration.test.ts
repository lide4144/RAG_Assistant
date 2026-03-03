import { test } from 'node:test';
import assert from 'node:assert/strict';

import { createChatService } from '../src/chatService.js';
import { validateCitationMapping } from '../src/citation.js';
import type { OutboundEvent } from '../src/types/events.js';

function eventPayload(mode: 'local' | 'web' | 'hybrid', query = 'q'): string {
  return JSON.stringify({
    type: 'chat',
    payload: {
      sessionId: 's1',
      mode,
      query
    }
  });
}

function collectText(events: OutboundEvent[]): string {
  return events
    .filter((event) => event.type === 'message')
    .map((event) => event.content)
    .join('');
}

test('local mode emits sources -> message stream -> messageEnd closure', async () => {
  const emitted: OutboundEvent[] = [];
  const service = createChatService({
    now: () => 100,
    randomUUID: () => 'trace-local',
    sleep: async () => undefined,
    searchWeb: async () => ({
      sources: [],
      providerUsed: 'mock',
      isMockFallback: false
    }),
    requestKernelAnswer: async () => {
      throw new Error('should not fallback when stream closes');
    },
    streamKernelAnswer: async (_payload, onEvent) => {
      onEvent({
        type: 'sources',
        traceId: 'trace-local',
        mode: 'local',
        sources: [
          {
            source_type: 'local',
            source_id: 's-local-1',
            title: 'local source',
            snippet: 'local evidence',
            locator: 'kb://1',
            score: 0.9
          }
        ]
      });
      onEvent({
        type: 'message',
        traceId: 'trace-local',
        mode: 'local',
        content: 'Answer with citation [1].'
      });
      onEvent({
        type: 'messageEnd',
        traceId: 'trace-local',
        mode: 'local',
        usage: { latencyMs: 1 }
      });
    }
  });

  await service(eventPayload('local'), (event) => emitted.push(event));

  const types = emitted.map((event) => event.type);
  assert.deepEqual(types, ['sources', 'message', 'messageEnd']);

  const sourcesEvent = emitted.find((event) => event.type === 'sources');
  assert.ok(sourcesEvent && sourcesEvent.type === 'sources');
  const answer = collectText(emitted);
  assert.equal(validateCitationMapping(answer, sourcesEvent.sources).ok, true);
  assert.equal(emitted.at(-1)?.type, 'messageEnd');
});

test('web mode includes provider metadata and citation closure', async () => {
  const emitted: OutboundEvent[] = [];
  const service = createChatService({
    now: () => 100,
    randomUUID: () => 'trace-web',
    sleep: async () => undefined,
    requestKernelAnswer: async () => {
      throw new Error('not used in web mode');
    },
    streamKernelAnswer: async () => {
      throw new Error('not used in web mode');
    },
    searchWeb: async () => ({
      providerUsed: 'duckduckgo',
      isMockFallback: false,
      sources: [
        {
          source_type: 'web',
          source_id: 'w-1',
          title: 'Duck result',
          snippet: 'live web evidence',
          locator: 'https://example.com',
          score: 0.8
        }
      ]
    })
  });

  await service(eventPayload('web', 'openai'), (event) => emitted.push(event));

  assert.equal(emitted[0]?.type, 'sources');
  assert.equal(emitted.at(-1)?.type, 'messageEnd');

  const sourcesEvent = emitted[0];
  assert.ok(sourcesEvent && sourcesEvent.type === 'sources');
  assert.equal(sourcesEvent.meta?.webProvider?.providerUsed, 'duckduckgo');
  assert.equal(sourcesEvent.meta?.webProvider?.isMockFallback, false);

  const answer = collectText(emitted);
  assert.equal(validateCitationMapping(answer, sourcesEvent.sources).ok, true);
});

test('hybrid mode preserves event order and surfaces mock fallback metadata', async () => {
  const emitted: OutboundEvent[] = [];
  const service = createChatService({
    now: () => 100,
    randomUUID: () => 'trace-hybrid',
    sleep: async () => undefined,
    requestKernelAnswer: async () => ({
      traceId: 'trace-hybrid',
      answer: 'Local answer [1].',
      sources: [
        {
          source_type: 'local',
          source_id: 'l-1',
          title: 'Local A',
          snippet: 'Local proof',
          locator: 'kb://a',
          score: 0.9
        }
      ]
    }),
    streamKernelAnswer: async () => {
      throw new Error('not used in hybrid mode');
    },
    searchWeb: async () => ({
      providerUsed: 'mock',
      isMockFallback: true,
      fallbackReason: 'duckduckgo timeout',
      sources: [
        {
          source_type: 'web',
          source_id: 'w-2',
          title: 'Web B',
          snippet: 'Web proof',
          locator: 'mock://2',
          score: 0.7
        }
      ]
    })
  });

  await service(eventPayload('hybrid', 'fusion'), (event) => emitted.push(event));

  const types = emitted.map((event) => event.type);
  assert.equal(types[0], 'sources');
  assert.equal(types.at(-1), 'messageEnd');

  const sourcesEvent = emitted.find((event) => event.type === 'sources');
  assert.ok(sourcesEvent && sourcesEvent.type === 'sources');
  assert.equal(sourcesEvent.sources.length, 2);
  assert.equal(sourcesEvent.meta?.webProvider?.providerUsed, 'mock');
  assert.equal(sourcesEvent.meta?.webProvider?.isMockFallback, true);
  assert.equal(sourcesEvent.meta?.webProvider?.fallbackReason, 'duckduckgo timeout');

  const answer = collectText(emitted);
  assert.equal(validateCitationMapping(answer, sourcesEvent.sources).ok, true);
});
