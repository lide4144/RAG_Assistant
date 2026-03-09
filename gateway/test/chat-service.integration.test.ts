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

test('task_start_graph_build emits task state/progress/result events', async () => {
  const emitted: OutboundEvent[] = [];
  let poll = 0;
  const service = createChatService({
    now: () => 100,
    randomUUID: () => 'trace-task',
    sleep: async () => undefined,
    requestKernelAnswer: async () => {
      throw new Error('not used for task');
    },
    streamKernelAnswer: async () => {
      throw new Error('not used for task');
    },
    searchWeb: async () => ({
      providerUsed: 'mock',
      isMockFallback: false,
      sources: []
    }),
    startGraphBuildTask: async () => ({
      task_id: 'task-1',
      task_kind: 'graph_build',
      state: 'queued',
      created_at: '2026-03-06T00:00:00Z',
      updated_at: '2026-03-06T00:00:00Z',
      accepted: true,
      progress: {
        stage: 'queued',
        processed: 0,
        total: 10,
        elapsed_ms: 0,
        message: 'queued'
      }
    }),
    getKernelTaskStatus: async () => {
      poll += 1;
      if (poll === 1) {
        return {
          task_id: 'task-1',
          task_kind: 'graph_build',
          state: 'running',
          created_at: '2026-03-06T00:00:00Z',
          updated_at: '2026-03-06T00:00:01Z',
          accepted: true,
          progress: {
            stage: 'extract_entities',
            processed: 5,
            total: 10,
            elapsed_ms: 1200,
            message: '5/10'
          }
        };
      }
      return {
        task_id: 'task-1',
        task_kind: 'graph_build',
        state: 'succeeded',
        created_at: '2026-03-06T00:00:00Z',
        updated_at: '2026-03-06T00:00:02Z',
        accepted: true,
        progress: {
          stage: 'done',
          processed: 10,
          total: 10,
          elapsed_ms: 2400,
          message: 'done'
        },
        result: { output_path: 'data/processed/graph.json', code: 0 }
      };
    }
  });

  await service(
    JSON.stringify({
      type: 'task_start_graph_build',
      payload: {}
    }),
    (event) => emitted.push(event)
  );

  const taskStateEvents = emitted.filter((event) => event.type === 'taskState');
  assert.ok(taskStateEvents.length >= 2);
  const progressEvents = emitted.filter((event) => event.type === 'taskProgress');
  assert.ok(progressEvents.length >= 1);
  const resultEvent = emitted.find((event) => event.type === 'taskResult');
  assert.ok(resultEvent && resultEvent.type === 'taskResult');
  assert.equal(resultEvent.state, 'succeeded');
});

test('failed graph task emits taskError before taskResult', async () => {
  const emitted: OutboundEvent[] = [];
  const service = createChatService({
    now: () => 100,
    randomUUID: () => 'trace-task-failed',
    sleep: async () => undefined,
    requestKernelAnswer: async () => {
      throw new Error('not used for task');
    },
    streamKernelAnswer: async () => {
      throw new Error('not used for task');
    },
    searchWeb: async () => ({
      providerUsed: 'mock',
      isMockFallback: false,
      sources: []
    }),
    startGraphBuildTask: async () => ({
      task_id: 'task-failed',
      task_kind: 'graph_build',
      state: 'queued',
      created_at: '2026-03-06T00:00:00Z',
      updated_at: '2026-03-06T00:00:00Z',
      accepted: true,
      progress: {
        stage: 'queued',
        processed: 0,
        total: 10,
        elapsed_ms: 0,
        message: 'queued'
      }
    }),
    getKernelTaskStatus: async () => ({
      task_id: 'task-failed',
      task_kind: 'graph_build',
      state: 'failed',
      created_at: '2026-03-06T00:00:00Z',
      updated_at: '2026-03-06T00:00:01Z',
      accepted: true,
      progress: {
        stage: 'extract_entities',
        processed: 3,
        total: 10,
        elapsed_ms: 800,
        message: '3/10'
      },
      error: {
        stage: 'extract_entities',
        message: 'boom',
        recovery: 'retry'
      }
    })
  });

  await service(
    JSON.stringify({
      type: 'task_start_graph_build',
      payload: {}
    }),
    (event) => emitted.push(event)
  );

  const taskErrorIndex = emitted.findIndex((event) => event.type === 'taskError');
  const taskResultIndex = emitted.findIndex((event) => event.type === 'taskResult');
  assert.ok(taskErrorIndex >= 0);
  assert.ok(taskResultIndex >= 0);
  assert.ok(taskErrorIndex < taskResultIndex);
});

test('task events and chat events can be consumed in parallel without cross-domain pollution', async () => {
  const emitted: OutboundEvent[] = [];
  let taskPoll = 0;
  const service = createChatService({
    now: () => 100,
    randomUUID: () => 'trace-parallel',
    sleep: async () => undefined,
    requestKernelAnswer: async () => ({
      traceId: 'trace-chat-1',
      answer: 'Parallel answer [1].',
      sources: [
        {
          source_type: 'local',
          source_id: 'p-1',
          title: 'Parallel Source',
          snippet: 'parallel evidence',
          locator: 'kb://parallel',
          score: 0.95
        }
      ]
    }),
    streamKernelAnswer: async (_payload, onEvent) => {
      onEvent({
        type: 'sources',
        traceId: 'trace-chat-1',
        mode: 'local',
        sources: [
          {
            source_type: 'local',
            source_id: 'p-1',
            title: 'Parallel Source',
            snippet: 'parallel evidence',
            locator: 'kb://parallel',
            score: 0.95
          }
        ]
      });
      onEvent({
        type: 'message',
        traceId: 'trace-chat-1',
        mode: 'local',
        content: 'Parallel answer [1].'
      });
      onEvent({
        type: 'messageEnd',
        traceId: 'trace-chat-1',
        mode: 'local',
        usage: { latencyMs: 1 }
      });
    },
    searchWeb: async () => ({
      providerUsed: 'mock',
      isMockFallback: false,
      sources: []
    }),
    startGraphBuildTask: async () => ({
      task_id: 'task-parallel',
      task_kind: 'graph_build',
      state: 'queued',
      created_at: '2026-03-06T00:00:00Z',
      updated_at: '2026-03-06T00:00:00Z',
      accepted: true,
      progress: {
        stage: 'queued',
        processed: 0,
        total: 1,
        elapsed_ms: 0,
        message: 'queued'
      }
    }),
    getKernelTaskStatus: async () => {
      taskPoll += 1;
      if (taskPoll === 1) {
        return {
          task_id: 'task-parallel',
          task_kind: 'graph_build',
          state: 'running',
          created_at: '2026-03-06T00:00:00Z',
          updated_at: '2026-03-06T00:00:01Z',
          accepted: true,
          progress: {
            stage: 'extract_entities',
            processed: 1,
            total: 2,
            elapsed_ms: 1200,
            message: '1/2'
          }
        };
      }
      return {
        task_id: 'task-parallel',
        task_kind: 'graph_build',
        state: 'succeeded',
        created_at: '2026-03-06T00:00:00Z',
        updated_at: '2026-03-06T00:00:02Z',
        accepted: true,
        progress: {
          stage: 'done',
          processed: 2,
          total: 2,
          elapsed_ms: 2400,
          message: 'done'
        }
      };
    }
  });

  await Promise.all([
    service(
      JSON.stringify({
        type: 'task_start_graph_build',
        payload: {}
      }),
      (event) => emitted.push(event)
    ),
    service(eventPayload('local', 'parallel'), (event) => emitted.push(event))
  ]);

  const chatEvents = emitted.filter(
    (event) => event.type === 'message' || event.type === 'sources' || event.type === 'messageEnd' || event.type === 'error'
  );
  const taskEvents = emitted.filter(
    (event) =>
      event.type === 'taskState' ||
      event.type === 'taskProgress' ||
      event.type === 'taskResult' ||
      event.type === 'taskError'
  );

  assert.ok(chatEvents.length > 0);
  assert.ok(taskEvents.length > 0);
  for (const event of taskEvents) {
    assert.ok('taskId' in event);
    assert.equal('traceId' in event, false);
  }
  for (const event of chatEvents) {
    assert.ok('traceId' in event);
    assert.equal('taskId' in event, false);
  }
});

test('gateway can continue processing next request after a protocol error', async () => {
  const emitted: OutboundEvent[] = [];
  const service = createChatService({
    now: () => 100,
    randomUUID: (() => {
      const ids = ['trace-error', 'trace-recover'];
      let idx = 0;
      return () => ids[idx++] ?? `trace-${idx}`;
    })(),
    sleep: async () => undefined,
    requestKernelAnswer: async () => {
      throw new Error('not used');
    },
    streamKernelAnswer: async () => {
      throw new Error('not used');
    },
    searchWeb: async () => ({
      providerUsed: 'mock',
      isMockFallback: false,
      sources: [
        {
          source_type: 'web',
          source_id: 'recover-1',
          title: 'Recover Source',
          snippet: 'recover evidence',
          locator: 'mock://recover',
          score: 0.8
        }
      ]
    })
  });

  await service('not-json-payload', (event) => emitted.push(event));
  await service(eventPayload('web', 'recover'), (event) => emitted.push(event));

  const first = emitted[0];
  assert.ok(first && first.type === 'error');
  assert.equal(first.traceId, 'trace-error');
  assert.ok(emitted.some((event) => event.type === 'messageEnd' && event.traceId === 'trace-recover'));
});
