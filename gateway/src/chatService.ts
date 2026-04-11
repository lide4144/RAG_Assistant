import { config } from './config.js';
import {
  appendCitationToSources,
  ensureStableSourceOrder,
  stripCitations,
  validateCitationMapping
} from './citation.js';
import { KernelClientError } from './errors.js';
import { normalizeSources, parseClientEvent } from './protocol.js';
import type { OutboundEvent, WebProviderMeta } from './types/events.js';
import type { ChatMode, KernelChatRequest, KernelChatResponse, KernelJobEvent, KernelJobStatus } from './types/kernel.js';
import {
  createKernelBackgroundJob as createKernelBackgroundJobDefault,
  getKernelJobEvents as getKernelJobEventsDefault,
  getKernelJobStatus as getKernelJobStatusDefault,
  getKernelTaskStatus as getKernelTaskStatusDefault,
  requestKernelAnswer as requestKernelAnswerDefault,
  startGraphBuildTask as startGraphBuildTaskDefault,
  streamKernelAnswer as streamKernelAnswerDefault,
  type KernelStreamEvent,
  type KernelTaskStatus
} from './adapters/pythonKernelClient.js';
import { searchWeb, WebProviderError, type WebSearchResult } from './web/providers.js';

export interface ChatServiceDeps {
  requestKernelAnswer: (payload: KernelChatRequest) => Promise<KernelChatResponse>;
  createKernelBackgroundJob: (payload: KernelChatRequest) => Promise<KernelJobStatus>;
  getKernelJobStatus: (jobId: string) => Promise<KernelJobStatus>;
  getKernelJobEvents: (jobId: string, afterSeq?: number) => Promise<KernelJobEvent[]>;
  streamKernelAnswer: (
    payload: KernelChatRequest,
    onEvent: (event: KernelStreamEvent) => void
  ) => Promise<void>;
  startGraphBuildTask: (
    payload?: {
      input_path?: string;
      output_path?: string;
      threshold?: number;
      top_m?: number;
      include_front_matter?: boolean;
      force_new?: boolean;
    }
  ) => Promise<KernelTaskStatus>;
  getKernelTaskStatus: (taskId: string) => Promise<KernelTaskStatus>;
  searchWeb: (query: string) => Promise<WebSearchResult>;
  sleep: (ms: number) => Promise<void>;
  now: () => number;
  randomUUID: () => string;
}

export function chunkText(text: string): string[] {
  const size = Math.max(8, config.streamChunkSize);
  const chunks: string[] = [];
  for (let i = 0; i < text.length; i += size) {
    chunks.push(text.slice(i, i + size));
  }
  return chunks.length ? chunks : [''];
}

function buildWebAnswer(query: string, webSources: ReturnType<typeof normalizeSources>): string {
  const cited = appendCitationToSources(webSources, 1, 5);
  if (cited.length === 0) {
    return `No web evidence found for query: ${query}.`;
  }

  const lines = cited.map(({ source, citation }) => `- ${source.title}: ${source.snippet} [${citation}]`);
  return `Web findings for \"${query}\":\n${lines.join('\n')}`;
}

function buildHybridAnswer(
  localAnswer: string,
  localSources: ReturnType<typeof normalizeSources>,
  webSources: ReturnType<typeof normalizeSources>,
  query: string
): string {
  const localCitationCheck = validateCitationMapping(localAnswer, localSources);
  const localPart = localCitationCheck.ok ? localAnswer.trim() : stripCitations(localAnswer);
  const localFallback =
    localPart ||
    appendCitationToSources(localSources, 1, 2)
      .map(({ source, citation }) => `${source.title} [${citation}]`)
      .join('; ');

  const webStart = localSources.length + 1;
  const webCited = appendCitationToSources(webSources, webStart, 4);
  const webPart = webCited.length
    ? webCited.map(({ source, citation }) => `- ${source.title}: ${source.snippet} [${citation}]`).join('\n')
    : '- No external web evidence returned.';

  return [
    `Hybrid response for \"${query}\":`,
    '',
    'Local evidence:',
    localFallback,
    '',
    'Web evidence:',
    webPart
  ].join('\n');
}

async function streamAnswerAsMessageEvents(
  sendEvent: (event: OutboundEvent) => void,
  traceId: string,
  mode: ChatMode,
  answer: string,
  sleepFn: (ms: number) => Promise<void>,
  meta?: WebProviderMeta
): Promise<void> {
  for (const piece of chunkText(answer)) {
    sendEvent({
      type: 'message',
      traceId,
      mode,
      content: piece,
      meta: meta ? { webProvider: meta } : undefined
    });
    if (piece.length > 0) {
      await sleepFn(config.streamChunkDelayMs);
    }
  }
}

function toWebProviderMeta(result: WebSearchResult): WebProviderMeta {
  const meta: WebProviderMeta = {
    providerUsed: result.providerUsed,
    isMockFallback: result.isMockFallback
  };
  if (result.fallbackReason) {
    meta.fallbackReason = result.fallbackReason;
  }
  return meta;
}

const terminalJobStates = new Set(['succeeded', 'failed', 'cancelled']);

function readString(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim().length > 0 ? value : undefined;
}

function toErrorEventFromJobPayload(
  jobId: string,
  payload: Record<string, unknown>,
  fallbackTraceId?: string,
  jobSeq?: number,
  createdAt?: string
): OutboundEvent {
  const detail = payload.detail && typeof payload.detail === 'object' && !Array.isArray(payload.detail)
    ? (payload.detail as Record<string, unknown>)
    : payload;
  const code = readString(detail.code) ?? readString(payload.code) ?? `JOB_${jobId}_FAILED`;
  const message =
    readString(detail.message) ??
    readString(payload.message) ??
    readString(detail.detail) ??
    readString(payload.detail) ??
    'Kernel job failed';
  return {
    type: 'error',
    jobId,
    seq: jobSeq,
    createdAt,
    traceId: readString(payload.traceId) ?? fallbackTraceId ?? 'unknown',
    code,
    message
  };
}

function mapJobEventToOutbound(event: KernelJobEvent): OutboundEvent | null {
  const payload = event.payload ?? {};
  if (payload.type === 'message') {
    const traceId = readString(payload.traceId);
    const mode = payload.mode;
    const content = readString(payload.content);
    if (!traceId || (mode !== 'local' && mode !== 'web' && mode !== 'hybrid') || content === undefined) {
      return null;
    }
    return { type: 'message', jobId: event.job_id, seq: event.seq, createdAt: event.created_at, traceId, mode, content };
  }
  if (payload.type === 'sources') {
    const traceId = readString(payload.traceId);
    const mode = payload.mode;
    if (!traceId || (mode !== 'local' && mode !== 'web' && mode !== 'hybrid') || !Array.isArray(payload.sources)) {
      return null;
    }
    return {
      type: 'sources',
      jobId: event.job_id,
      seq: event.seq,
      createdAt: event.created_at,
      traceId,
      mode,
      sources: ensureStableSourceOrder(normalizeSources(payload.sources)),
      runId: readString(payload.runId)
    };
  }
  if (payload.type === 'messageEnd') {
    const traceId = readString(payload.traceId);
    const mode = payload.mode;
    if (!traceId || (mode !== 'local' && mode !== 'web' && mode !== 'hybrid')) {
      return null;
    }
    return {
      type: 'messageEnd',
      jobId: event.job_id,
      seq: event.seq,
      createdAt: event.created_at,
      traceId,
      mode,
      runId: readString(payload.runId)
    };
  }
  if (payload.type === 'error') {
    return toErrorEventFromJobPayload(event.job_id, payload, readString(payload.traceId), event.seq, event.created_at);
  }
  return null;
}

async function relayKernelJobEvents(
  jobId: string,
  afterSeq: number,
  sendEvent: (event: OutboundEvent) => void,
  deps: ChatServiceDeps,
  options?: { latencyStartedAt?: number }
): Promise<void> {
  let lastSeq = Math.max(0, afterSeq);
  let latestStatus = await deps.getKernelJobStatus(jobId);
  let messageEnded = false;
  let lastTraceId = latestStatus.trace_id ?? 'unknown';
  let lastMode: ChatMode = 'local';

  while (true) {
    const jobEvents = await deps.getKernelJobEvents(jobId, lastSeq);
    for (const jobEvent of jobEvents) {
      lastSeq = Math.max(lastSeq, jobEvent.seq);
      const outbound = mapJobEventToOutbound(jobEvent);
      if (!outbound) {
        continue;
      }
      if (outbound.type === 'messageEnd') {
        messageEnded = true;
        lastTraceId = outbound.traceId;
        lastMode = outbound.mode;
      } else if (outbound.type === 'message' || outbound.type === 'sources') {
        lastTraceId = outbound.traceId;
        lastMode = outbound.mode;
      }
      if (outbound.type === 'error') {
        lastTraceId = outbound.traceId;
      }
      sendEvent(outbound);
      if (outbound.type === 'error') {
        return;
      }
    }

    latestStatus = await deps.getKernelJobStatus(jobId);
    if (!terminalJobStates.has(latestStatus.state)) {
      await deps.sleep(250);
      continue;
    }

    if (latestStatus.state === 'failed') {
      sendEvent(toErrorEventFromJobPayload(jobId, latestStatus.error ?? {}, latestStatus.trace_id ?? lastTraceId));
      return;
    }

    if (!messageEnded) {
      sendEvent({
        type: 'messageEnd',
        traceId: latestStatus.trace_id ?? lastTraceId,
        mode: lastMode,
        runId: latestStatus.run_id,
        usage: options?.latencyStartedAt !== undefined ? { latencyMs: deps.now() - options.latencyStartedAt } : undefined
      });
    }
    return;
  }
}

export function createChatService(overrides: Partial<ChatServiceDeps> = {}) {
  const deps: ChatServiceDeps = {
    requestKernelAnswer: overrides.requestKernelAnswer ?? requestKernelAnswerDefault,
    createKernelBackgroundJob: overrides.createKernelBackgroundJob ?? createKernelBackgroundJobDefault,
    getKernelJobStatus: overrides.getKernelJobStatus ?? getKernelJobStatusDefault,
    getKernelJobEvents: overrides.getKernelJobEvents ?? getKernelJobEventsDefault,
    streamKernelAnswer: overrides.streamKernelAnswer ?? streamKernelAnswerDefault,
    startGraphBuildTask: overrides.startGraphBuildTask ?? startGraphBuildTaskDefault,
    getKernelTaskStatus: overrides.getKernelTaskStatus ?? getKernelTaskStatusDefault,
    searchWeb: overrides.searchWeb ?? searchWeb,
    sleep: overrides.sleep ?? ((ms: number) => new Promise((resolve) => setTimeout(resolve, ms))),
    now: overrides.now ?? Date.now,
    randomUUID: overrides.randomUUID ?? (() => crypto.randomUUID())
  };

  return async function handleRawClientEvent(raw: string, sendEvent: (event: OutboundEvent) => void): Promise<void> {
    const startedAt = deps.now();
    const requestTraceId = deps.randomUUID();

    try {
      const event = parseClientEvent(raw);
      if (event.type === 'job_subscribe') {
        await relayKernelJobEvents(event.payload.jobId, event.payload.afterSeq ?? 0, sendEvent, deps);
        return;
      }
      if (event.type === 'task_start_graph_build') {
        const startedTask = await deps.startGraphBuildTask(event.payload);
        sendEvent({
          type: 'taskState',
          taskId: startedTask.task_id,
          taskKind: startedTask.task_kind,
          state: startedTask.state,
          accepted: startedTask.accepted,
          updatedAt: startedTask.updated_at
        });

        const terminal = new Set(['succeeded', 'failed', 'cancelled']);
        let current = startedTask;
        while (!terminal.has(current.state)) {
          await deps.sleep(250);
          current = await deps.getKernelTaskStatus(current.task_id);
          sendEvent({
            type: 'taskState',
            taskId: current.task_id,
            taskKind: current.task_kind,
            state: current.state,
            accepted: current.accepted,
            updatedAt: current.updated_at
          });
          if (current.progress) {
            sendEvent({
              type: 'taskProgress',
              taskId: current.task_id,
              taskKind: current.task_kind,
              state: current.state,
              stage: current.progress.stage,
              processed: current.progress.processed,
              total: current.progress.total,
              elapsedMs: current.progress.elapsed_ms,
              message: current.progress.message,
              updatedAt: current.updated_at
            });
          }
        }
        if (current.state === 'failed' && current.error) {
          sendEvent({
            type: 'taskError',
            taskId: current.task_id,
            taskKind: current.task_kind,
            state: 'failed',
            error: current.error,
            updatedAt: current.updated_at
          });
        }
        sendEvent({
          type: 'taskResult',
          taskId: current.task_id,
          taskKind: current.task_kind,
          state: current.state,
          result: current.result,
          error: current.error,
          updatedAt: current.updated_at
        });
        return;
      }

      const payload = {
        sessionId: event.payload.sessionId,
        query: event.payload.query,
        mode: event.payload.mode,
        history: event.payload.history,
        traceId: requestTraceId
      } as const;

      if (event.payload.mode === 'local') {
        try {
          const job = await deps.createKernelBackgroundJob(payload);
          await relayKernelJobEvents(job.job_id, 0, sendEvent, deps, { latencyStartedAt: startedAt });
          return;
        } catch (error) {
          if (!(error instanceof KernelClientError) || (error.status !== 404 && error.status !== 405)) {
            throw error;
          }
        }

        let fullAnswer = '';
        let latestSources: ReturnType<typeof normalizeSources> = [];
        let lastTraceId = requestTraceId;
        let lastRunId: string | undefined;
        let streamEnded = false;
        let streamBlocked = false;

        const handleKernelEvent = (kernelEvent: KernelStreamEvent) => {
          if (kernelEvent.type === 'serviceBlocked') {
            streamBlocked = true;
            lastTraceId = kernelEvent.traceId;
            sendEvent(kernelEvent);
            return;
          }
          if (kernelEvent.type === 'message') {
            fullAnswer += kernelEvent.content;
            lastTraceId = kernelEvent.traceId;
            sendEvent(kernelEvent);
            return;
          }
          if (kernelEvent.type === 'sources') {
            latestSources = ensureStableSourceOrder(normalizeSources(kernelEvent.sources));
            lastTraceId = kernelEvent.traceId;
            lastRunId = kernelEvent.runId;
            sendEvent({
              type: 'sources',
              traceId: kernelEvent.traceId,
              mode: kernelEvent.mode,
              sources: latestSources,
              runId: kernelEvent.runId
            });
            return;
          }
          if (kernelEvent.type === 'messageEnd') {
            streamEnded = true;
            lastTraceId = kernelEvent.traceId;
            lastRunId = kernelEvent.runId;
            return;
          }
          lastTraceId = kernelEvent.traceId;
          sendEvent(kernelEvent);
        };

        await deps.streamKernelAnswer(payload, handleKernelEvent);

        if (!streamEnded && !streamBlocked) {
          const fallback = await deps.requestKernelAnswer(payload);
          fullAnswer = fallback.answer;
          latestSources = ensureStableSourceOrder(normalizeSources(fallback.sources));
          lastTraceId = fallback.traceId;
          lastRunId = fallback.runId;
          sendEvent({
            type: 'sources',
            traceId: fallback.traceId,
            mode: event.payload.mode,
            sources: latestSources,
            runId: fallback.runId
          });
          await streamAnswerAsMessageEvents(sendEvent, fallback.traceId, event.payload.mode, fallback.answer, deps.sleep);
        }

        if (streamBlocked) {
          return;
        }

        const citationMapping = validateCitationMapping(fullAnswer, latestSources);
        if (!citationMapping.ok) {
          sendEvent({
            type: 'error',
            traceId: lastTraceId,
            code: 'CITATION_MAPPING_INVALID',
            message: `Invalid citations: ${citationMapping.invalidCitations.join(', ')}`
          });
          return;
        }

        sendEvent({
          type: 'messageEnd',
          traceId: lastTraceId,
          mode: event.payload.mode,
          runId: lastRunId,
          usage: { latencyMs: deps.now() - startedAt }
        });
        return;
      }

      if (event.payload.mode === 'web') {
        const webResult = await deps.searchWeb(event.payload.query);
        const webMeta = toWebProviderMeta(webResult);
        const webSources = ensureStableSourceOrder(normalizeSources(webResult.sources));
        const answer = buildWebAnswer(event.payload.query, webSources);
        const mapping = validateCitationMapping(answer, webSources);
        if (!mapping.ok) {
          sendEvent({
            type: 'error',
            traceId: requestTraceId,
            code: 'CITATION_MAPPING_INVALID',
            message: `Invalid citations: ${mapping.invalidCitations.join(', ')}`,
            meta: { webProvider: webMeta }
          });
          return;
        }

        sendEvent({ type: 'sources', traceId: requestTraceId, mode: 'web', sources: webSources, meta: { webProvider: webMeta } });
        await streamAnswerAsMessageEvents(sendEvent, requestTraceId, 'web', answer, deps.sleep, webMeta);
        sendEvent({
          type: 'messageEnd',
          traceId: requestTraceId,
          mode: 'web',
          usage: { latencyMs: deps.now() - startedAt },
          meta: { webProvider: webMeta }
        });
        return;
      }

      const [localResponse, webResult] = await Promise.all([
        deps.requestKernelAnswer({ ...payload, mode: 'local' }),
        deps.searchWeb(event.payload.query)
      ]);

      const webMeta = toWebProviderMeta(webResult);
      const localSources = ensureStableSourceOrder(normalizeSources(localResponse.sources));
      const webSources = ensureStableSourceOrder(normalizeSources(webResult.sources));
      const mergedSources = ensureStableSourceOrder([...localSources, ...webSources]);
      const hybridAnswer = buildHybridAnswer(localResponse.answer, localSources, webSources, event.payload.query);
      const mapping = validateCitationMapping(hybridAnswer, mergedSources);
      if (!mapping.ok) {
        sendEvent({
          type: 'error',
          traceId: localResponse.traceId,
          code: 'CITATION_MAPPING_INVALID',
          message: `Invalid citations: ${mapping.invalidCitations.join(', ')}`,
          meta: { webProvider: webMeta }
        });
        return;
      }

      sendEvent({
        type: 'sources',
        traceId: localResponse.traceId,
        mode: 'hybrid',
        sources: mergedSources,
        runId: localResponse.runId,
        meta: { webProvider: webMeta }
      });
      await streamAnswerAsMessageEvents(sendEvent, localResponse.traceId, 'hybrid', hybridAnswer, deps.sleep, webMeta);
      sendEvent({
        type: 'messageEnd',
        traceId: localResponse.traceId,
        mode: 'hybrid',
        runId: localResponse.runId,
        usage: { latencyMs: deps.now() - startedAt },
        meta: { webProvider: webMeta }
      });
    } catch (error) {
      let eventCode = 'GATEWAY_PROTOCOL_ERROR';
      if (error instanceof KernelClientError) {
        eventCode = error.code;
      } else if (error instanceof WebProviderError) {
        eventCode = 'WEB_PROVIDER_FAILED';
      }

      sendEvent({
        type: 'error',
        traceId: requestTraceId,
        code: eventCode,
        message: error instanceof Error ? error.message : 'Unknown websocket error'
      });
    }
  };
}
