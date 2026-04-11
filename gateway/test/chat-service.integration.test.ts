import { test } from 'node:test';
import assert from 'node:assert/strict';

import { createChatService } from '../src/chatService.js';
import { validateCitationMapping } from '../src/citation.js';
import { KernelClientError, KernelErrorCode } from '../src/errors.js';
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

function jobSubscribePayload(jobId: string, afterSeq = 0): string {
  return JSON.stringify({
    type: 'job_subscribe',
    payload: {
      jobId,
      afterSeq
    }
  });
}

function buildJobEvent(seq: number, payload: Record<string, unknown>) {
  return {
    job_id: 'job-1',
    seq,
    event_type: String(payload.type ?? 'unknown'),
    created_at: `2026-04-03T00:00:0${seq}Z`,
    payload
  };
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
    createKernelBackgroundJob: async () => {
      throw new KernelClientError(KernelErrorCode.BAD_RESPONSE, 'missing job endpoint', 404);
    },
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

test('local mode bridges kernel background jobs through job events', async () => {
  const emitted: OutboundEvent[] = [];
  let statusCalls = 0;
  const service = createChatService({
    now: () => 100,
    randomUUID: () => 'trace-local-job',
    sleep: async () => undefined,
    searchWeb: async () => ({ sources: [], providerUsed: 'mock', isMockFallback: false }),
    requestKernelAnswer: async () => {
      throw new Error('should not fallback when job endpoint is available');
    },
    streamKernelAnswer: async () => {
      throw new Error('should not use direct stream when job endpoint is available');
    },
    createKernelBackgroundJob: async () => ({
      job_id: 'job-1',
      kind: 'planner_chat',
      state: 'queued',
      created_at: '2026-04-03T00:00:00Z',
      updated_at: '2026-04-03T00:00:00Z',
      accepted: true,
      trace_id: 'trace-local-job'
    }),
    getKernelJobEvents: async (_jobId, afterSeq = 0) =>
      [
        buildJobEvent(1, {
          type: 'sources',
          traceId: 'trace-local-job',
          mode: 'local',
          runId: 'run-job-1',
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
        }),
        buildJobEvent(2, {
          type: 'message',
          traceId: 'trace-local-job',
          mode: 'local',
          content: 'Answer with citation [1].'
        }),
        buildJobEvent(3, {
          type: 'messageEnd',
          traceId: 'trace-local-job',
          mode: 'local',
          runId: 'run-job-1'
        })
      ].filter((item) => item.seq > afterSeq),
    getKernelJobStatus: async () => {
      statusCalls += 1;
      return {
        job_id: 'job-1',
        kind: 'planner_chat',
        state: 'succeeded',
        created_at: '2026-04-03T00:00:00Z',
        updated_at: '2026-04-03T00:00:01Z',
        accepted: true,
        trace_id: 'trace-local-job',
        run_id: 'run-job-1'
      };
    }
  });

  await service(eventPayload('local'), (event) => emitted.push(event));

  assert.deepEqual(emitted.map((event) => event.type), ['sources', 'message', 'messageEnd']);
  assert.equal(emitted[0]?.jobId, 'job-1');
  assert.equal(emitted[0]?.seq, 1);
  assert.equal(statusCalls >= 1, true);
  const sourcesEvent = emitted.find((event) => event.type === 'sources');
  assert.ok(sourcesEvent && sourcesEvent.type === 'sources');
  assert.equal(validateCitationMapping(collectText(emitted), sourcesEvent.sources).ok, true);
});

test('job_subscribe replays missing events after a cursor and keeps polling until terminal', async () => {
  const emitted: OutboundEvent[] = [];
  let poll = 0;
  const service = createChatService({
    now: () => 100,
    randomUUID: () => 'trace-subscribe',
    sleep: async () => undefined,
    requestKernelAnswer: async () => {
      throw new Error('not used');
    },
    streamKernelAnswer: async () => {
      throw new Error('not used');
    },
    createKernelBackgroundJob: async () => {
      throw new Error('not used');
    },
    startGraphBuildTask: async () => {
      throw new Error('not used');
    },
    getKernelTaskStatus: async () => {
      throw new Error('not used');
    },
    searchWeb: async () => ({ sources: [], providerUsed: 'mock', isMockFallback: false }),
    getKernelJobEvents: async (_jobId, afterSeq = 0) => {
      poll += 1;
      const allEvents = [
        buildJobEvent(1, { type: 'message', traceId: 'trace-subscribe', mode: 'local', content: 'first ' }),
        buildJobEvent(2, { type: 'message', traceId: 'trace-subscribe', mode: 'local', content: 'second' }),
        buildJobEvent(3, { type: 'messageEnd', traceId: 'trace-subscribe', mode: 'local', runId: 'run-subscribe' })
      ];
      if (poll === 1) {
        return allEvents.filter((item) => item.seq > afterSeq && item.seq < 3);
      }
      return allEvents.filter((item) => item.seq > afterSeq);
    },
    getKernelJobStatus: async () => ({
      job_id: 'job-1',
      kind: 'planner_chat',
      state: poll >= 2 ? 'succeeded' : 'running',
      created_at: '2026-04-03T00:00:00Z',
      updated_at: '2026-04-03T00:00:02Z',
      accepted: true,
      trace_id: 'trace-subscribe',
      run_id: 'run-subscribe'
    })
  });

  await service(jobSubscribePayload('job-1', 1), (event) => emitted.push(event));

  assert.deepEqual(
    emitted.map((event) => event.type),
    ['message', 'messageEnd']
  );
  assert.equal(emitted[0]?.jobId, 'job-1');
  assert.equal(emitted[0]?.seq, 2);
  assert.equal(collectText(emitted), 'second');
  assert.equal(poll >= 2, true);
});

test('local mode forwards agent execution events before standard chat closure', async () => {
  const emitted: OutboundEvent[] = [];
  const service = createChatService({
    now: () => 100,
    randomUUID: () => 'trace-agent',
    sleep: async () => undefined,
    searchWeb: async () => ({
      sources: [],
      providerUsed: 'mock',
      isMockFallback: false
    }),
    createKernelBackgroundJob: async () => {
      throw new KernelClientError(KernelErrorCode.BAD_RESPONSE, 'missing job endpoint', 404);
    },
    requestKernelAnswer: async () => {
      throw new Error('should not fallback when stream closes');
    },
    streamKernelAnswer: async (_payload, onEvent) => {
      onEvent({
        type: 'planning',
        traceId: 'trace-agent',
        mode: 'local',
        timestamp: '2026-03-16T10:00:00Z',
        phase: 'planning',
        decisionResult: 'local_execute',
        selectedPath: 'fact_qa',
        plannerSource: 'llm',
        plannerSourceMode: 'llm_primary',
        executionSource: 'llm'
      });
      onEvent({
        type: 'toolSelection',
        traceId: 'trace-agent',
        mode: 'local',
        timestamp: '2026-03-16T10:00:01Z',
        toolName: 'fact_qa',
        callId: 'tool-1',
        status: 'selected'
      });
      onEvent({
        type: 'toolRunning',
        traceId: 'trace-agent',
        mode: 'local',
        timestamp: '2026-03-16T10:00:02Z',
        toolName: 'fact_qa',
        callId: 'tool-1',
        status: 'running'
      });
      onEvent({
        type: 'toolResult',
        traceId: 'trace-agent',
        mode: 'local',
        timestamp: '2026-03-16T10:00:03Z',
        toolName: 'fact_qa',
        callId: 'tool-1',
        status: 'succeeded',
        resultKind: 'final',
        message: 'completed'
      });
      onEvent({
        type: 'sources',
        traceId: 'trace-agent',
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
        traceId: 'trace-agent',
        mode: 'local',
        content: 'Answer with citation [1].'
      });
      onEvent({
        type: 'messageEnd',
        traceId: 'trace-agent',
        mode: 'local',
        usage: { latencyMs: 1 }
      });
    }
  });

  await service(eventPayload('local'), (event) => emitted.push(event));

  assert.deepEqual(emitted.map((event) => event.type), [
    'planning',
    'toolSelection',
    'toolRunning',
    'toolResult',
    'sources',
    'message',
    'messageEnd'
  ]);
  const planning = emitted[0];
  assert.ok(planning && planning.type === 'planning');
  assert.equal(planning.plannerSourceMode, 'llm_primary');
  assert.equal(planning.executionSource, 'llm');
});

test('local mode preserves fallback events and still closes with standard message events', async () => {
  const emitted: OutboundEvent[] = [];
  const service = createChatService({
    now: () => 100,
    randomUUID: () => 'trace-fallback',
    sleep: async () => undefined,
    searchWeb: async () => ({
      sources: [],
      providerUsed: 'mock',
      isMockFallback: false
    }),
    createKernelBackgroundJob: async () => {
      throw new KernelClientError(KernelErrorCode.BAD_RESPONSE, 'missing job endpoint', 404);
    },
    requestKernelAnswer: async () => {
      throw new Error('should not fallback when stream closes');
    },
    streamKernelAnswer: async (_payload, onEvent) => {
      onEvent({
        type: 'planning',
        traceId: 'trace-fallback',
        mode: 'local',
        timestamp: '2026-03-16T10:00:00Z',
        phase: 'planning',
        decisionResult: 'legacy_fallback',
        selectedPath: 'legacy_fallback'
      });
      onEvent({
        type: 'fallback',
        traceId: 'trace-fallback',
        mode: 'local',
        timestamp: '2026-03-16T10:00:01Z',
        fallbackScope: 'legacy',
        reasonCode: 'legacy_fallback',
        continues: true,
        message: 'compatibility fallback'
      });
      onEvent({
        type: 'sources',
        traceId: 'trace-fallback',
        mode: 'local',
        sources: []
      });
      onEvent({
        type: 'message',
        traceId: 'trace-fallback',
        mode: 'local',
        content: 'Fallback answer'
      });
      onEvent({
        type: 'messageEnd',
        traceId: 'trace-fallback',
        mode: 'local',
        usage: { latencyMs: 1 }
      });
    }
  });

  await service(eventPayload('local'), (event) => emitted.push(event));

  assert.deepEqual(emitted.map((event) => event.type), ['planning', 'fallback', 'sources', 'message', 'messageEnd']);
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
    createKernelBackgroundJob: async () => {
      throw new KernelClientError(KernelErrorCode.BAD_RESPONSE, 'missing job endpoint', 404);
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

test('task events and agent events can coexist in parallel without cross-domain pollution', async () => {
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
        type: 'planning',
        traceId: 'trace-chat-1',
        mode: 'local',
        timestamp: '2026-03-16T10:00:00Z',
        phase: 'planning',
        decisionResult: 'local_execute',
        selectedToolsOrSkills: ['fact_qa']
      });
      onEvent({
        type: 'toolSelection',
        traceId: 'trace-chat-1',
        mode: 'local',
        timestamp: '2026-03-16T10:00:01Z',
        toolName: 'fact_qa',
        callId: 'tool-1',
        status: 'selected'
      });
      onEvent({
        type: 'toolRunning',
        traceId: 'trace-chat-1',
        mode: 'local',
        timestamp: '2026-03-16T10:00:02Z',
        toolName: 'fact_qa',
        callId: 'tool-1',
        status: 'running'
      });
      onEvent({
        type: 'toolResult',
        traceId: 'trace-chat-1',
        mode: 'local',
        timestamp: '2026-03-16T10:00:03Z',
        toolName: 'fact_qa',
        callId: 'tool-1',
        status: 'succeeded',
        resultKind: 'final',
        message: 'completed'
      });
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
    createKernelBackgroundJob: async () => {
      throw new KernelClientError(KernelErrorCode.BAD_RESPONSE, 'missing job endpoint', 404);
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

  const traceScopedEvents = emitted.filter(
    (event) =>
      event.type === 'planning' ||
      event.type === 'toolSelection' ||
      event.type === 'toolRunning' ||
      event.type === 'toolResult' ||
      event.type === 'message' ||
      event.type === 'sources' ||
      event.type === 'messageEnd' ||
      event.type === 'error'
  );
  const taskEvents = emitted.filter(
    (event) =>
      event.type === 'taskState' ||
      event.type === 'taskProgress' ||
      event.type === 'taskResult' ||
      event.type === 'taskError'
  );

  assert.deepEqual(
    traceScopedEvents.map((event) => event.type).filter((type) => type !== 'sources' && type !== 'message' && type !== 'messageEnd'),
    ['planning', 'toolSelection', 'toolRunning', 'toolResult']
  );
  assert.ok(traceScopedEvents.some((event) => event.type === 'sources'));
  assert.ok(traceScopedEvents.some((event) => event.type === 'message'));
  assert.ok(traceScopedEvents.some((event) => event.type === 'messageEnd'));
  assert.ok(taskEvents.length > 0);
  for (const event of taskEvents) {
    assert.ok('taskId' in event);
    assert.equal('traceId' in event, false);
  }
  for (const event of traceScopedEvents) {
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
