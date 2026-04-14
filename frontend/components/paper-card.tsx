'use client';

import { FileText, Trash2, RefreshCw, RotateCcw, Eye } from 'lucide-react';
import type { Paper } from '../types/library';
import { statusStyles } from '../types/library';

interface PaperCardProps {
  paper: Paper;
  selected: boolean;
  onSelect: (selected: boolean) => void;
  onView: () => void;
  onDelete: () => void;
  onRebuild: () => void;
  onRetry?: () => void;
}

export function PaperCard({
  paper,
  selected,
  onSelect,
  onView,
  onDelete,
  onRebuild,
  onRetry,
}: PaperCardProps) {
  const statusStyle = statusStyles[paper.status] || statusStyles.imported;

  const formatDate = (dateStr: string) => {
    if (!dateStr) return '-';
    const date = new Date(dateStr);
    if (isNaN(date.getTime())) return dateStr;
    return date.toLocaleDateString('zh-CN', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  };

  return (
    <article
      className={`relative rounded-[22px] border p-4 transition-all ${
        selected
          ? 'border-sky-400 bg-sky-50 shadow-[0_8px_32px_rgba(56,189,248,0.15)]'
          : 'border-slate-200 bg-white hover:border-slate-300 hover:shadow-sm'
      }`}
    >
      {/* Checkbox */}
      <div className="absolute left-4 top-4">
        <input
          type="checkbox"
          checked={selected}
          onChange={(e) => onSelect(e.target.checked)}
          className="h-4 w-4 rounded border-slate-300 text-sky-600 focus:ring-sky-500"
        />
      </div>

      {/* Content */}
      <div className="pl-8">
        {/* Title */}
        <h3 className="text-sm font-semibold text-slate-900 line-clamp-2 [overflow-wrap:anywhere]">
          {paper.title || '无标题'}
        </h3>

        {/* Status Badge */}
        <div className="mt-2 flex items-center gap-2">
          <span
            className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium ${statusStyle.border} ${statusStyle.bg} ${statusStyle.label === '失败' ? 'text-rose-700' : statusStyle.label === '就绪' ? 'text-emerald-700' : 'text-sky-700'}`}
          >
            <span>{statusStyle.icon}</span>
            {statusStyle.label}
          </span>
        </div>

        {/* Topics */}
        {paper.topics && paper.topics.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1">
            {paper.topics.slice(0, 3).map((topic) => (
              <span
                key={topic}
                className="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-[10px] text-slate-600"
              >
                {topic}
              </span>
            ))}
            {paper.topics.length > 3 && (
              <span className="text-[10px] text-slate-400">
                +{paper.topics.length - 3}
              </span>
            )}
          </div>
        )}

        {/* Date */}
        <p className="mt-2 text-[11px] text-slate-400">
          {formatDate(paper.imported_at)}
        </p>

        {/* Actions */}
        <div className="mt-3 flex items-center gap-1">
          <button
            type="button"
            onClick={onView}
            className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-[11px] font-medium text-slate-600 hover:bg-slate-100"
          >
            <Eye className="h-3 w-3" />
            查看
          </button>
          <button
            type="button"
            onClick={onDelete}
            className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-[11px] font-medium text-rose-600 hover:bg-rose-50"
          >
            <Trash2 className="h-3 w-3" />
            删除
          </button>
          {paper.status === 'failed' && onRetry ? (
            <button
              type="button"
              onClick={onRetry}
              className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-[11px] font-medium text-amber-600 hover:bg-amber-50"
            >
              <RotateCcw className="h-3 w-3" />
              重试
            </button>
          ) : (
            <button
              type="button"
              onClick={onRebuild}
              className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-[11px] font-medium text-sky-600 hover:bg-sky-50"
            >
              <RefreshCw className="h-3 w-3" />
              重建
            </button>
          )}
        </div>
      </div>
    </article>
  );
}
