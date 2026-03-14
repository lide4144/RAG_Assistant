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
