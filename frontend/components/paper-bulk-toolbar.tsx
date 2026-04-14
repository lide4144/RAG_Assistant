'use client';

import { Trash2, RefreshCw, X } from 'lucide-react';

interface PaperBulkToolbarProps {
  selectedCount: number;
  onDelete: () => void;
  onRebuild: () => void;
  onClear: () => void;
}

export function PaperBulkToolbar({
  selectedCount,
  onDelete,
  onRebuild,
  onClear,
}: PaperBulkToolbarProps) {
  if (selectedCount === 0) return null;

  return (
    <div className="fixed bottom-6 left-1/2 z-40 w-full max-w-2xl -translate-x-1/2 px-4">
      <div className="flex items-center justify-between rounded-2xl border border-slate-200 bg-white px-4 py-3 shadow-lg">
        <div className="flex items-center gap-3">
          <span className="flex h-6 w-6 items-center justify-center rounded-full bg-sky-100 text-xs font-medium text-sky-700">
            {selectedCount}
          </span>
          <span className="text-sm text-slate-700">已选择</span>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onRebuild}
            className="inline-flex items-center gap-1.5 rounded-xl bg-sky-600 px-3 py-2 text-xs font-medium text-white hover:bg-sky-700"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            批量重建
          </button>
          <button
            type="button"
            onClick={onDelete}
            className="inline-flex items-center gap-1.5 rounded-xl bg-rose-600 px-3 py-2 text-xs font-medium text-white hover:bg-rose-700"
          >
            <Trash2 className="h-3.5 w-3.5" />
            批量删除
          </button>
          <button
            type="button"
            onClick={onClear}
            className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-medium text-slate-600 hover:bg-slate-50"
          >
            <X className="h-3.5 w-3.5" />
            清空
          </button>
        </div>
      </div>
    </div>
  );
}
