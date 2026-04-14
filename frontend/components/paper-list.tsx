'use client';

import { ChevronLeft, ChevronRight } from 'lucide-react';
import { PaperCard } from './paper-card';
import type { Paper } from '../types/library';

interface PaperListProps {
  papers: Paper[];
  selectedIds: Set<string>;
  onSelect: (id: string, selected: boolean) => void;
  onSelectAll: () => void;
  onView: (paper: Paper) => void;
  onDelete: (paper: Paper) => void;
  onRebuild: (paper: Paper) => void;
  onRetry?: (paper: Paper) => void;
  page: number;
  pageSize: number;
  onPageChange: (page: number) => void;
}

export function PaperList({
  papers,
  selectedIds,
  onSelect,
  onSelectAll,
  onView,
  onDelete,
  onRebuild,
  onRetry,
  page,
  pageSize,
  onPageChange,
}: PaperListProps) {
  const totalPages = Math.ceil(papers.length / pageSize);
  const startIndex = (page - 1) * pageSize;
  const paginatedPapers = papers.slice(startIndex, startIndex + pageSize);

  const allSelected = paginatedPapers.length > 0 && paginatedPapers.every((p) => selectedIds.has(p.paper_id));

  const getPageNumbers = () => {
    const pages: (number | string)[] = [];
    const maxVisible = 5;

    if (totalPages <= maxVisible) {
      for (let i = 1; i <= totalPages; i++) pages.push(i);
    } else {
      if (page <= 3) {
        for (let i = 1; i <= 4; i++) pages.push(i);
        pages.push('...');
        pages.push(totalPages);
      } else if (page >= totalPages - 2) {
        pages.push(1);
        pages.push('...');
        for (let i = totalPages - 3; i <= totalPages; i++) pages.push(i);
      } else {
        pages.push(1);
        pages.push('...');
        pages.push(page - 1);
        pages.push(page);
        pages.push(page + 1);
        pages.push('...');
        pages.push(totalPages);
      }
    }
    return pages;
  };

  if (papers.length === 0) {
    return (
      <div className="rounded-[22px] border border-slate-200 bg-slate-50/50 p-8 text-center">
        <p className="text-sm text-slate-500">暂无论文数据</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Select All */}
      <div className="flex items-center justify-between px-1">
        <label className="flex items-center gap-2 text-sm text-slate-600">
          <input
            type="checkbox"
            checked={allSelected}
            onChange={onSelectAll}
            className="h-4 w-4 rounded border-slate-300 text-sky-600 focus:ring-sky-500"
          />
          全选本页
        </label>
        <span className="text-xs text-slate-400">
          共 {papers.length} 篇，第 {page}/{totalPages} 页
        </span>
      </div>

      {/* Cards Grid */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {paginatedPapers.map((paper) => (
          <PaperCard
            key={paper.paper_id}
            paper={paper}
            selected={selectedIds.has(paper.paper_id)}
            onSelect={(selected) => onSelect(paper.paper_id, selected)}
            onView={() => onView(paper)}
            onDelete={() => onDelete(paper)}
            onRebuild={() => onRebuild(paper)}
            onRetry={onRetry ? () => onRetry(paper) : undefined}
          />
        ))}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-2 pt-4">
          <button
            type="button"
            onClick={() => onPageChange(page - 1)}
            disabled={page <= 1}
            className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-600 hover:bg-slate-50 disabled:opacity-50"
          >
            <ChevronLeft className="h-4 w-4" />
          </button>

          {getPageNumbers().map((p, i) => (
            p === '...' ? (
              <span key={`ellipsis-${i}`} className="px-2 text-slate-400">...</span>
            ) : (
              <button
                key={p}
                type="button"
                onClick={() => onPageChange(p as number)}
                className={`h-8 w-8 rounded-lg text-sm font-medium ${
                  page === p
                    ? 'bg-slate-900 text-white'
                    : 'border border-slate-200 bg-white text-slate-600 hover:bg-slate-50'
                }`}
              >
                {p}
              </button>
            )
          ))}

          <button
            type="button"
            onClick={() => onPageChange(page + 1)}
            disabled={page >= totalPages}
            className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-600 hover:bg-slate-50 disabled:opacity-50"
          >
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      )}
    </div>
  );
}
