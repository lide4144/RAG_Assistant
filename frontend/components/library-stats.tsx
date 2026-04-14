'use client';

import { FileText, CheckCircle, XCircle, Loader2, Database } from 'lucide-react';
import type { LibraryStats as LibraryStatsType } from '../types/library';

interface LibraryStatsProps {
  stats: LibraryStatsType;
}

export function LibraryStats({ stats }: LibraryStatsProps) {
  const items = [
    { icon: FileText, label: '论文总数', value: stats.total, color: 'text-slate-900' },
    { icon: CheckCircle, label: '就绪', value: stats.ready, color: 'text-emerald-600' },
    { icon: XCircle, label: '失败', value: stats.failed, color: 'text-rose-600' },
    { icon: Loader2, label: '处理中', value: stats.processing, color: 'text-sky-600' },
  ];

  return (
    <div className="space-y-4">
      {/* Main Stats */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {items.map(({ icon: Icon, label, value, color }) => (
          <div
            key={label}
            className="rounded-[22px] border border-slate-200 bg-white p-4"
          >
            <div className="flex items-center gap-2">
              <Icon className="h-4 w-4 text-slate-400" />
              <span className="text-xs text-slate-500">{label}</span>
            </div>
            <p className={`mt-2 text-2xl font-semibold ${color}`}>{value}</p>
          </div>
        ))}
      </div>

      {/* Topics */}
      {Object.keys(stats.topics).length > 0 && (
        <div className="rounded-[22px] border border-slate-200 bg-white p-4">
          <h4 className="text-xs font-medium text-slate-500">专题分布</h4>
          <div className="mt-2 flex flex-wrap gap-2">
            {Object.entries(stats.topics)
              .sort(([, a], [, b]) => b - a)
              .slice(0, 10)
              .map(([topic, count]) => (
                <span
                  key={topic}
                  className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs text-slate-600"
                >
                  {topic}
                  <span className="text-slate-400">({count})</span>
                </span>
              ))}
          </div>
        </div>
      )}

      {/* Vector Backend */}
      {stats.vectorBackend && (
        <div className="rounded-[22px] border border-slate-200 bg-white p-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Database className="h-4 w-4 text-slate-400" />
              <span className="text-xs text-slate-500">向量后端</span>
            </div>
            <span
              className={`text-xs font-medium ${
                stats.vectorBackend.status === 'healthy'
                  ? 'text-emerald-600'
                  : stats.vectorBackend.status === 'degraded'
                  ? 'text-amber-600'
                  : 'text-rose-600'
              }`}
            >
              {stats.vectorBackend.backend_name === 'qdrant' ? 'Qdrant' : 'File'}
              {' '}
              {stats.vectorBackend.status === 'healthy'
                ? '✓'
                : stats.vectorBackend.status === 'degraded'
                ? '⚠'
                : '✗'}
            </span>
          </div>
          {stats.vectorBackend.metadata?.vector_count !== undefined && (
            <p className="mt-1 text-xs text-slate-400">
              {stats.vectorBackend.metadata.vector_count.toLocaleString()} 向量
            </p>
          )}
        </div>
      )}
    </div>
  );
}
