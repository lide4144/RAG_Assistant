import { config } from '../config.js';
import type { KernelSource } from '../types/kernel.js';
import {
  recordWebProviderFailure,
  recordWebProviderFallback,
  recordWebProviderSuccess,
  setConfiguredProvider
} from './telemetry.js';

export interface WebSearchResult {
  sources: KernelSource[];
  providerUsed: 'mock' | 'duckduckgo';
  isMockFallback: boolean;
  fallbackReason?: string;
}

export class WebProviderError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'WebProviderError';
  }
}

function toSourceId(provider: string, idx: number, seed: string): string {
  const suffix = seed.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '').slice(0, 24) || 'query';
  return `web-${provider}-${idx + 1}-${suffix}`;
}

function createMockSources(query: string, limit: number): KernelSource[] {
  const items = [
    {
      title: `Web briefing: ${query}`,
      snippet: `Mock web result for \"${query}\". Replace provider with real search backend in production.`
    },
    {
      title: 'Implementation note',
      snippet: 'Gateway currently supports configurable web provider and unified source schema.'
    },
    {
      title: 'Follow-up suggestion',
      snippet: 'Use Hybrid mode to compare local corpus evidence with web-time signals.'
    }
  ];

  return items.slice(0, limit).map((item, idx) => ({
    source_type: 'web',
    source_id: toSourceId('mock', idx, query),
    title: item.title,
    snippet: item.snippet,
    locator: `mock://${idx + 1}`,
    score: Number((0.9 - idx * 0.1).toFixed(3))
  }));
}

async function searchDuckDuckGo(query: string, limit: number): Promise<KernelSource[]> {
  const url = new URL('https://api.duckduckgo.com/');
  url.searchParams.set('q', query);
  url.searchParams.set('format', 'json');
  url.searchParams.set('no_redirect', '1');
  url.searchParams.set('no_html', '1');

  const response = await fetch(url, {
    headers: {
      accept: 'application/json'
    }
  });

  if (!response.ok) {
    throw new Error(`duckduckgo provider failed: ${response.status}`);
  }

  const data = (await response.json()) as {
    AbstractURL?: string;
    AbstractText?: string;
    Heading?: string;
    RelatedTopics?: Array<
      | { Text?: string; FirstURL?: string }
      | { Name?: string; Topics?: Array<{ Text?: string; FirstURL?: string }> }
    >;
  };

  const sources: KernelSource[] = [];
  if (data.AbstractText) {
    sources.push({
      source_type: 'web',
      source_id: toSourceId('ddg', 0, query),
      title: data.Heading || 'DuckDuckGo abstract',
      snippet: data.AbstractText,
      locator: data.AbstractURL || 'https://duckduckgo.com',
      score: 0.92
    });
  }

  const related = data.RelatedTopics || [];
  for (const row of related) {
    if (sources.length >= limit) {
      break;
    }
    if ('Topics' in row && Array.isArray(row.Topics)) {
      for (const sub of row.Topics) {
        if (sources.length >= limit) {
          break;
        }
        if (!sub.Text) {
          continue;
        }
        sources.push({
          source_type: 'web',
          source_id: toSourceId('ddg', sources.length, query),
          title: row.Name || 'DuckDuckGo topic',
          snippet: sub.Text,
          locator: sub.FirstURL || 'https://duckduckgo.com',
          score: Number((0.85 - sources.length * 0.04).toFixed(3))
        });
      }
      continue;
    }

    if (!('Text' in row) || !row.Text) {
      continue;
    }
    sources.push({
      source_type: 'web',
      source_id: toSourceId('ddg', sources.length, query),
      title: 'DuckDuckGo related',
      snippet: row.Text,
      locator: row.FirstURL || 'https://duckduckgo.com',
      score: Number((0.85 - sources.length * 0.04).toFixed(3))
    });
  }

  if (sources.length === 0) {
    throw new Error('duckduckgo provider returned no usable sources');
  }
  return sources.slice(0, limit);
}

export async function checkWebProviderHealth(): Promise<{ ok: boolean; error?: string }> {
  setConfiguredProvider(config.webProvider);
  if (config.webProvider === 'mock') {
    return { ok: true };
  }

  try {
    await searchDuckDuckGo('openai', 1);
    return { ok: true };
  } catch (error) {
    return {
      ok: false,
      error: error instanceof Error ? error.message : 'duckduckgo healthcheck failed'
    };
  }
}

export async function searchWeb(query: string): Promise<WebSearchResult> {
  const limit = Math.max(1, config.webTopK);
  setConfiguredProvider(config.webProvider);

  if (config.webProvider === 'duckduckgo') {
    try {
      const sources = await searchDuckDuckGo(query, limit);
      recordWebProviderSuccess('duckduckgo');
      return {
        sources,
        providerUsed: 'duckduckgo',
        isMockFallback: false
      };
    } catch (error) {
      const reason = error instanceof Error ? error.message : 'duckduckgo provider failed';
      if (config.webProviderStrict) {
        recordWebProviderFailure(reason);
        throw new WebProviderError(reason);
      }

      recordWebProviderFallback(reason);
      return {
        sources: createMockSources(query, limit),
        providerUsed: 'mock',
        isMockFallback: true,
        fallbackReason: reason
      };
    }
  }

  recordWebProviderSuccess('mock');
  return {
    sources: createMockSources(query, limit),
    providerUsed: 'mock',
    isMockFallback: false
  };
}
