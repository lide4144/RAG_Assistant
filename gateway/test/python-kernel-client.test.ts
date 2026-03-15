import { afterEach, test } from 'node:test';
import assert from 'node:assert/strict';
import axios, { AxiosError } from 'axios';

import { requestKernelAnswer, streamKernelAnswer } from '../src/adapters/pythonKernelClient.js';

const originalAxiosRequest = axios.Axios.prototype.request;
const originalFetch = global.fetch;

afterEach(() => {
  axios.Axios.prototype.request = originalAxiosRequest;
  global.fetch = originalFetch;
});

test('requestKernelAnswer falls back to legacy /qa when planner endpoint is unavailable', async () => {
  const seen: string[] = [];

  axios.Axios.prototype.request = async function request(config) {
    const normalized = typeof config === 'string' ? { url: config } : config;
    const url = String(normalized.url ?? '');
    seen.push(url);
    if (url === '/planner/qa') {
      throw new AxiosError(
        'missing',
        undefined,
        normalized,
        undefined,
        {
          status: 404,
          statusText: 'Not Found',
          headers: {},
          config: normalized,
          data: { detail: 'missing' },
        } as never
      );
    }
    if (url === '/qa') {
      return {
        status: 200,
        statusText: 'OK',
        headers: {},
        config: normalized,
        data: {
          traceId: 'trace-legacy',
          answer: 'legacy answer [1]',
          sources: [
            {
              source_type: 'local',
              source_id: 'chunk-1',
              title: 'Paper A',
              snippet: 'snippet',
              locator: 'p.1',
              score: 0.9,
            },
          ],
        },
      } as never;
    }
    throw new Error(`unexpected url: ${url}`);
  };

  const response = await requestKernelAnswer({
    sessionId: 's1',
    mode: 'local',
    query: 'q1',
    history: [],
    traceId: 'trace-1',
  });

  assert.equal(response.traceId, 'trace-legacy');
  assert.deepEqual(seen, ['/planner/qa', '/qa']);
});

test('requestKernelAnswer keeps hybrid mode on legacy /qa during phase one', async () => {
  const seen: string[] = [];

  axios.Axios.prototype.request = async function request(config) {
    const normalized = typeof config === 'string' ? { url: config } : config;
    const url = String(normalized.url ?? '');
    seen.push(url);
    if (url === '/qa') {
      return {
        status: 200,
        statusText: 'OK',
        headers: {},
        config: normalized,
        data: {
          traceId: 'trace-hybrid-legacy',
          answer: 'hybrid legacy [1]',
          sources: [],
        },
      } as never;
    }
    throw new Error(`unexpected url: ${url}`);
  };

  const response = await requestKernelAnswer({
    sessionId: 's1',
    mode: 'hybrid',
    query: 'q1',
    history: [],
    traceId: 'trace-1',
  });

  assert.equal(response.traceId, 'trace-hybrid-legacy');
  assert.deepEqual(seen, ['/qa']);
});

test('requestKernelAnswer keeps planner runtime errors inside the runtime unless compatibility fallback is allowed', async () => {
  const seen: string[] = [];

  axios.Axios.prototype.request = async function request(config) {
    const normalized = typeof config === 'string' ? { url: config } : config;
    const url = String(normalized.url ?? '');
    seen.push(url);
    if (url === '/planner/qa') {
      throw new AxiosError(
        'runtime boom',
        undefined,
        normalized,
        undefined,
        {
          status: 500,
          statusText: 'Internal Server Error',
          headers: {},
          config: normalized,
          data: { detail: 'runtime boom' },
        } as never
      );
    }
    throw new Error(`unexpected url: ${url}`);
  };

  await assert.rejects(
    () =>
      requestKernelAnswer({
        sessionId: 's1',
        mode: 'local',
        query: 'q1',
        history: [],
        traceId: 'trace-1',
      }),
    /Kernel returned 500/
  );

  assert.deepEqual(seen, ['/planner/qa']);
});

test('streamKernelAnswer falls back to legacy /qa/stream and preserves event contract', async () => {
  const seen: string[] = [];
  const events: Array<{ type: string }> = [];

  global.fetch = async (input) => {
    const url = String(input);
    seen.push(url);
    if (url.endsWith('/planner/qa/stream')) {
      return new Response(JSON.stringify({ detail: 'missing' }), {
        status: 404,
        headers: { 'content-type': 'application/json' },
      });
    }
    if (url.endsWith('/qa/stream')) {
      return new Response(
        'event: sources\n' +
          'data: {"type":"sources","traceId":"trace-legacy","mode":"local","sources":[]}\n\n' +
          'event: message\n' +
          'data: {"type":"message","traceId":"trace-legacy","mode":"local","content":"legacy stream"}\n\n' +
          'event: messageEnd\n' +
          'data: {"type":"messageEnd","traceId":"trace-legacy","mode":"local"}\n\n',
        {
          status: 200,
          headers: { 'content-type': 'text/event-stream' },
        }
      );
    }
    throw new Error(`unexpected url: ${url}`);
  };

  await streamKernelAnswer(
    {
      sessionId: 's1',
      mode: 'local',
      query: 'q1',
      history: [],
      traceId: 'trace-1',
    },
    (event) => events.push({ type: event.type })
  );

  assert.equal(seen[0]?.endsWith('/planner/qa/stream'), true);
  assert.equal(seen[1]?.endsWith('/qa/stream'), true);
  assert.deepEqual(
    events.map((event) => event.type),
    ['sources', 'message', 'messageEnd']
  );
});

test('streamKernelAnswer normalizes supported agent execution events and strips unsupported payload fields', async () => {
  const events: Array<Record<string, unknown>> = [];

  global.fetch = async () =>
    new Response(
      'event: planning\n' +
        'data: {"type":"planning","traceId":"trace-agent","mode":"local","timestamp":"2026-03-16T10:00:00Z","phase":"planning","decisionResult":"local_execute","selectedToolsOrSkills":["fact_qa"],"internalTrace":{"node":"secret"}}\n\n' +
        'event: toolSelection\n' +
        'data: {"type":"toolSelection","traceId":"trace-agent","mode":"local","timestamp":"2026-03-16T10:00:01Z","toolName":"fact_qa","callId":"tool-1","status":"selected","debug":"drop-me"}\n\n' +
        'event: toolRunning\n' +
        'data: {"type":"toolRunning","traceId":"trace-agent","mode":"local","timestamp":"2026-03-16T10:00:02Z","toolName":"fact_qa","callId":"tool-1","status":"running","prompt":"hidden"}\n\n' +
        'event: toolResult\n' +
        'data: {"type":"toolResult","traceId":"trace-agent","mode":"local","timestamp":"2026-03-16T10:00:03Z","toolName":"fact_qa","callId":"tool-1","status":"succeeded","resultKind":"final","message":"done","trace":["hidden"]}\n\n' +
        'event: unsupportedEvent\n' +
        'data: {"type":"unsupportedEvent","traceId":"trace-agent","mode":"local"}\n\n' +
        'event: messageEnd\n' +
        'data: {"type":"messageEnd","traceId":"trace-agent","mode":"local","usage":{"latencyMs":5}}\n\n',
      {
        status: 200,
        headers: { 'content-type': 'text/event-stream' }
      }
    );

  await streamKernelAnswer(
    {
      sessionId: 's1',
      mode: 'local',
      query: 'q1',
      history: [],
      traceId: 'trace-1'
    },
    (event) => events.push(event as unknown as Record<string, unknown>)
  );

  assert.deepEqual(
    events.map((event) => event.type),
    ['planning', 'toolSelection', 'toolRunning', 'toolResult', 'messageEnd']
  );
  assert.equal('internalTrace' in events[0], false);
  assert.equal('debug' in events[1], false);
  assert.equal('prompt' in events[2], false);
  assert.equal('trace' in events[3], false);
});

test('streamKernelAnswer preserves fallback events without mapping them to errors', async () => {
  const events: Array<{ type: string; reasonCode?: string; continues?: boolean }> = [];

  global.fetch = async () =>
    new Response(
      'event: planning\n' +
        'data: {"type":"planning","traceId":"trace-fallback","mode":"local","timestamp":"2026-03-16T10:00:00Z","phase":"planning","decisionResult":"legacy_fallback"}\n\n' +
        'event: fallback\n' +
        'data: {"type":"fallback","traceId":"trace-fallback","mode":"local","timestamp":"2026-03-16T10:00:01Z","fallbackScope":"legacy","reasonCode":"legacy_fallback","continues":true,"message":"fallback in use"}\n\n' +
        'event: message\n' +
        'data: {"type":"message","traceId":"trace-fallback","mode":"local","content":"legacy answer"}\n\n' +
        'event: messageEnd\n' +
        'data: {"type":"messageEnd","traceId":"trace-fallback","mode":"local"}\n\n',
      {
        status: 200,
        headers: { 'content-type': 'text/event-stream' }
      }
    );

  await streamKernelAnswer(
    {
      sessionId: 's1',
      mode: 'local',
      query: 'q1',
      history: [],
      traceId: 'trace-1'
    },
    (event) => events.push(event as { type: string; reasonCode?: string; continues?: boolean })
  );

  assert.deepEqual(
    events.map((event) => event.type),
    ['planning', 'fallback', 'message', 'messageEnd']
  );
  assert.equal(events[1]?.reasonCode, 'legacy_fallback');
  assert.equal(events[1]?.continues, true);
});

test('streamKernelAnswer keeps hybrid mode on legacy /qa/stream during phase one', async () => {
  const seen: string[] = [];
  const events: Array<{ type: string }> = [];

  global.fetch = async (input) => {
    const url = String(input);
    seen.push(url);
    if (url.endsWith('/qa/stream')) {
      return new Response(
        'event: sources\n' +
          'data: {"type":"sources","traceId":"trace-hybrid","mode":"hybrid","sources":[]}\n\n' +
          'event: message\n' +
          'data: {"type":"message","traceId":"trace-hybrid","mode":"hybrid","content":"hybrid stream"}\n\n' +
          'event: messageEnd\n' +
          'data: {"type":"messageEnd","traceId":"trace-hybrid","mode":"hybrid"}\n\n',
        {
          status: 200,
          headers: { 'content-type': 'text/event-stream' },
        }
      );
    }
    throw new Error(`unexpected url: ${url}`);
  };

  await streamKernelAnswer(
    {
      sessionId: 's1',
      mode: 'hybrid',
      query: 'q1',
      history: [],
      traceId: 'trace-1',
    },
    (event) => events.push({ type: event.type })
  );

  assert.equal(seen.length, 1);
  assert.equal(seen[0]?.endsWith('/qa/stream'), true);
  assert.deepEqual(
    events.map((event) => event.type),
    ['sources', 'message', 'messageEnd']
  );
});
