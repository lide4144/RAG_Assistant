import type { KernelSource } from './types/kernel.js';

const CITATION_REGEX = /\[(\d+)\]/g;

export function ensureStableSourceOrder(sources: KernelSource[]): KernelSource[] {
  const seen = new Set<string>();
  const normalized: KernelSource[] = [];

  for (const source of sources) {
    const sourceId = source.source_id.trim();
    if (!sourceId || seen.has(sourceId)) {
      continue;
    }
    seen.add(sourceId);
    normalized.push({
      source_type: source.source_type,
      source_id: sourceId,
      title: source.title,
      snippet: source.snippet,
      locator: source.locator,
      score: source.score
    });
  }

  return normalized;
}

export function validateCitationMapping(answer: string, sources: KernelSource[]): {
  ok: boolean;
  invalidCitations: number[];
} {
  const max = sources.length;
  const invalid = new Set<number>();

  for (const match of answer.matchAll(CITATION_REGEX)) {
    const idx = Number(match[1]);
    if (!Number.isInteger(idx) || idx < 1 || idx > max) {
      invalid.add(idx);
    }
  }

  return {
    ok: invalid.size === 0,
    invalidCitations: Array.from(invalid).sort((a, b) => a - b)
  };
}

export function appendCitationToSources(
  sources: KernelSource[],
  startIndex = 1,
  maxItems = 5
): Array<{ source: KernelSource; citation: number }> {
  return sources.slice(0, maxItems).map((source, idx) => ({
    source,
    citation: startIndex + idx
  }));
}

export function stripCitations(text: string): string {
  return text.replace(CITATION_REGEX, '').replace(/\s+/g, ' ').trim();
}
