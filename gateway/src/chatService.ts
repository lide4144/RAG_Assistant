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
import type { ChatMode, KernelChatRequest, KernelChatResponse } from './types/kernel.js';
import {
  requestKernelAnswer as requestKernelAnswerDefault,
  streamKernelAnswer as streamKernelAnswerDefault,
  type KernelStreamEvent
} from './adapters/pythonKernelClient.js';
import { searchWeb, WebProviderError, type WebSearchResult } from './web/providers.js';

export interface ChatServiceDeps {
  requestKernelAnswer: (payload: KernelChatRequest) => Promise<KernelChatResponse>;
  streamKernelAnswer: (
    payload: KernelChatRequest,
    onEvent: (event: KernelStreamEvent) => void
  ) => Promise<void>;
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

export function createChatService(overrides: Partial<ChatServiceDeps> = {}) {
  const deps: ChatServiceDeps = {
    requestKernelAnswer: overrides.requestKernelAnswer ?? requestKernelAnswerDefault,
    streamKernelAnswer: overrides.streamKernelAnswer ?? streamKernelAnswerDefault,
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
      const payload = {
        sessionId: event.payload.sessionId,
        query: event.payload.query,
        mode: event.payload.mode,
        history: event.payload.history,
        traceId: requestTraceId
      } as const;

      if (event.payload.mode === 'local') {
        let fullAnswer = '';
        let latestSources: ReturnType<typeof normalizeSources> = [];
        let lastTraceId = requestTraceId;
        let streamEnded = false;

        const handleKernelEvent = (kernelEvent: KernelStreamEvent) => {
          if (kernelEvent.type === 'message') {
            fullAnswer += kernelEvent.content;
            lastTraceId = kernelEvent.traceId;
            sendEvent(kernelEvent);
            return;
          }
          if (kernelEvent.type === 'sources') {
            latestSources = ensureStableSourceOrder(normalizeSources(kernelEvent.sources));
            lastTraceId = kernelEvent.traceId;
            sendEvent({
              type: 'sources',
              traceId: kernelEvent.traceId,
              mode: kernelEvent.mode,
              sources: latestSources
            });
            return;
          }
          if (kernelEvent.type === 'messageEnd') {
            streamEnded = true;
            lastTraceId = kernelEvent.traceId;
            return;
          }
          lastTraceId = kernelEvent.traceId;
          sendEvent(kernelEvent);
        };

        await deps.streamKernelAnswer(payload, handleKernelEvent);

        if (!streamEnded) {
          const fallback = await deps.requestKernelAnswer(payload);
          fullAnswer = fallback.answer;
          latestSources = ensureStableSourceOrder(normalizeSources(fallback.sources));
          lastTraceId = fallback.traceId;
          sendEvent({ type: 'sources', traceId: fallback.traceId, mode: event.payload.mode, sources: latestSources });
          await streamAnswerAsMessageEvents(sendEvent, fallback.traceId, event.payload.mode, fallback.answer, deps.sleep);
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
        meta: { webProvider: webMeta }
      });
      await streamAnswerAsMessageEvents(sendEvent, localResponse.traceId, 'hybrid', hybridAnswer, deps.sleep, webMeta);
      sendEvent({
        type: 'messageEnd',
        traceId: localResponse.traceId,
        mode: 'hybrid',
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
