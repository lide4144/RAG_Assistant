'use client';

import { Copy, RotateCcw, ShieldAlert, Trash2 } from 'lucide-react';
import type { MarkerArtifactItem } from '../lib/types';

type MarkerArtifactPanelProps = {
  degraded: boolean;
  fallbackReason?: string | null;
  fallbackPath?: string | null;
  confidenceNote?: string | null;
  items: MarkerArtifactItem[];
  actionMessage?: string;
  onCopyPath: (path: string) => void;
  onDeleteArtifact: (item: MarkerArtifactItem) => void;
  onRebuildArtifact: (item: MarkerArtifactItem) => void;
};

const groupLabels: Record<'indexes' | 'processed', string> = {
  indexes: 'Index Artifacts',
  processed: 'Processed Artifacts'
};

const statusTone: Record<MarkerArtifactItem['status'], string> = {
  healthy: 'border-emerald-200 bg-emerald-50 text-emerald-800',
  missing: 'border-rose-200 bg-rose-50 text-rose-800',
  stale: 'border-amber-200 bg-amber-50 text-amber-900'
};

const toArtifactTestId = (key: string) => key.replace(/[^a-z0-9]+/gi, '-').replace(/^-+|-+$/g, '').toLowerCase();

export function MarkerArtifactPanel({
  degraded,
  fallbackReason,
  fallbackPath,
  confidenceNote,
  items,
  actionMessage,
  onCopyPath,
  onDeleteArtifact,
  onRebuildArtifact
}: MarkerArtifactPanelProps) {
  const grouped = {
    indexes: items.filter((item) => item.group === 'indexes'),
    processed: items.filter((item) => item.group === 'processed')
  };

  return (
    <section className="mt-4 overflow-hidden rounded-[28px] border border-[#d7d0c7] bg-[linear-gradient(145deg,#fffdf8_0%,#f5efe4_55%,#ebe3d5_100%)] shadow-[0_20px_80px_rgba(97,76,41,0.12)]">
      <div className="grid gap-0 lg:grid-cols-[1.2fr_1.8fr]">
        <div className="relative overflow-hidden border-b border-[#d7d0c7] p-5 lg:border-b-0 lg:border-r">
          <div className="absolute inset-x-0 top-0 h-20 bg-[radial-gradient(circle_at_top_left,rgba(167,139,84,0.22),transparent_65%)]" />
          <p className="relative text-[11px] font-semibold uppercase tracking-[0.28em] text-[#7a6341]">Marker Watch</p>
          <div
            className={`relative mt-4 rounded-[22px] border px-4 py-4 ${
              degraded ? 'border-amber-300 bg-[rgba(255,244,214,0.8)]' : 'border-emerald-200 bg-[rgba(236,253,245,0.86)]'
            }`}
          >
            <div className="flex items-start gap-3">
              <div className="rounded-2xl bg-[#1f1a14] p-2 text-white shadow-sm">
                <ShieldAlert className="h-4 w-4" />
              </div>
              <div>
                <p className="text-sm font-semibold text-[#2f2417]">{degraded ? 'Import degraded but completed' : 'Import path healthy'}</p>
                <p className="mt-1 text-xs leading-5 text-[#6c5840]">{fallbackReason || '最近一次导入没有暴露 Marker 降级原因。'}</p>
              </div>
            </div>
            <div className="mt-3 grid gap-2 text-[11px] text-[#5c4a35]">
              <p>Fallback path: {fallbackPath || '-'}</p>
              <p>{confidenceNote || '暂无可信度附注。'}</p>
            </div>
          </div>
          {actionMessage ? <p className="relative mt-3 text-xs text-[#5c4a35]">{actionMessage}</p> : null}
        </div>

        <div className="p-5">
          <div className="mb-4 flex items-center justify-between gap-3">
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.28em] text-[#7a6341]">Artifact Management</p>
              <h3 className="mt-1 text-xl font-semibold tracking-tight text-[#2c2218]">Index / processed 产物总览</h3>
            </div>
            <div className="rounded-full border border-[#d7d0c7] bg-white/70 px-3 py-1 text-[11px] font-medium text-[#6c5840]">
              {items.length} items
            </div>
          </div>

          <div className="grid gap-4 xl:grid-cols-2">
            {(Object.keys(grouped) as Array<keyof typeof grouped>).map((group) => (
              <article key={group} className="rounded-[24px] border border-[#d7d0c7] bg-white/75 p-3 backdrop-blur">
                <p className="mb-3 text-xs font-semibold uppercase tracking-[0.18em] text-[#7a6341]">{groupLabels[group]}</p>
                <div className="space-y-3">
                  {grouped[group].length ? (
                    grouped[group].map((item) => {
                      const testId = toArtifactTestId(item.key);
                      return (
                      <div
                        key={item.key}
                        data-testid={`artifact-card-${testId}`}
                        className="rounded-[20px] border border-[#ece3d5] bg-[#fffdfa] p-3 shadow-[0_8px_24px_rgba(97,76,41,0.06)]"
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <p className="text-sm font-semibold text-[#2c2218]">{item.file_name}</p>
                            <p className="mt-1 text-[11px] text-[#6c5840]">
                              {item.artifact_type} · {item.related_stage} · {item.updated_at || 'unknown time'}
                            </p>
                          </div>
                          <span className={`rounded-full border px-2 py-1 text-[10px] font-semibold uppercase ${statusTone[item.status]}`}>
                            {item.status}
                          </span>
                        </div>
                        <p className="mt-2 line-clamp-2 text-[11px] leading-5 text-[#6c5840]">{item.health_message || item.path}</p>
                        <div className="mt-3 flex flex-wrap gap-2">
                          <button
                            type="button"
                            data-testid={`artifact-copy-${testId}`}
                            onClick={() => onCopyPath(item.path)}
                            className="inline-flex items-center gap-1 rounded-full border border-[#d7d0c7] bg-white px-3 py-1.5 text-[11px] font-medium text-[#4e3e2c]"
                          >
                            <Copy className="h-3.5 w-3.5" />
                            Copy path
                          </button>
                          <button
                            type="button"
                            data-testid={`artifact-rebuild-${testId}`}
                            onClick={() => onRebuildArtifact(item)}
                            className="inline-flex items-center gap-1 rounded-full border border-[#d5c2a0] bg-[#f7ecd8] px-3 py-1.5 text-[11px] font-medium text-[#6a4d1f]"
                          >
                            <RotateCcw className="h-3.5 w-3.5" />
                            Rebuild
                          </button>
                          <button
                            type="button"
                            data-testid={`artifact-delete-${testId}`}
                            onClick={() => onDeleteArtifact(item)}
                            className="inline-flex items-center gap-1 rounded-full border border-[#e8c5bf] bg-[#fff1ee] px-3 py-1.5 text-[11px] font-medium text-[#9a3d2e]"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                            Delete
                          </button>
                        </div>
                      </div>
                    );
                    })
                  ) : (
                    <div className="rounded-[18px] border border-dashed border-[#d7d0c7] bg-white/60 p-4 text-xs text-[#75624d]">
                      当前分组暂无可展示产物。
                    </div>
                  )}
                </div>
              </article>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
