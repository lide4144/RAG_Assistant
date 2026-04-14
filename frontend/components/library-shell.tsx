'use client';

import { useState, useMemo, useCallback, useEffect } from 'react';
import { toast } from 'sonner';
import { usePapersPoll } from '../lib/use-papers-poll';
import { PaperList } from './paper-list';
import { PaperFilters } from './paper-filters';
import { LibraryStats } from './library-stats';
import { PaperDetailModal } from './paper-detail-modal';
import { PaperBulkToolbar } from './paper-bulk-toolbar';
import { ConfirmDialog } from './confirm-dialog';
import {
  deletePaper,
  rebuildPaper,
  retryPaper,
  bulkDeletePapers,
  bulkRebuildPapers,
} from '../lib/library-api';
import type { Paper } from '../types/library';

const PAGE_SIZE = 12;

export function LibraryShell() {
  // Filters
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<string | null>(null);
  const [topicFilter, setTopicFilter] = useState<string | null>(null);

  // Pagination
  const [page, setPage] = useState(1);

  // Selection
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  // Modal
  const [detailPaper, setDetailPaper] = useState<Paper | null>(null);

  // Dialogs
  const [deletePaperData, setDeletePaperData] = useState<Paper | null>(null);
  const [rebuildPaperData, setRebuildPaperData] = useState<Paper | null>(null);
  const [showBulkDeleteDialog, setShowBulkDeleteDialog] = useState(false);
  const [showBulkRebuildDialog, setShowBulkRebuildDialog] = useState(false);

  // Fetch papers
  const params = useMemo(
    () => ({
      limit: 500,
      status: statusFilter || undefined,
      topic: topicFilter || undefined,
      q: searchQuery || undefined,
    }),
    [searchQuery, statusFilter, topicFilter]
  );

  const { papers, loading, error, refresh } = usePapersPoll({
    intervalMs: 10000,
    params,
  });

  // Filter papers client-side for search
  const filteredPapers = useMemo(() => {
    let result = [...papers];

    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      result = result.filter(
        (p) =>
          p.title?.toLowerCase().includes(query) ||
          p.source_uri?.toLowerCase().includes(query)
      );
    }

    if (statusFilter) {
      result = result.filter((p) => p.status === statusFilter);
    }

    if (topicFilter) {
      result = result.filter((p) => p.topics?.includes(topicFilter));
    }

    return result;
  }, [papers, searchQuery, statusFilter, topicFilter]);

  // Debug: 监听 page 变化
  useEffect(() => {
    console.log('[Debug] Page changed to:', page, 'at', new Date().toLocaleTimeString());
  }, [page]);

  // 自动调整页码：如果当前页超过总页数，回到最后一页
  useEffect(() => {
    const totalPages = Math.ceil(filteredPapers.length / PAGE_SIZE);
    if (totalPages > 0 && page > totalPages) {
      console.log('[Debug] Auto-adjusting page from', page, 'to', totalPages);
      setPage(totalPages);
    }
  }, [filteredPapers.length, page]);

  // Stats
  const stats = useMemo(() => {
    const topics: Record<string, number> = {};
    papers.forEach((p) => {
      p.topics?.forEach((t) => {
        topics[t] = (topics[t] || 0) + 1;
      });
    });

    return {
      total: papers.length,
      ready: papers.filter((p) => p.status === 'ready').length,
      failed: papers.filter((p) => p.status === 'failed').length,
      processing: papers.filter((p) =>
        ['imported', 'parsed', 'cleaned', 'rebuild_pending'].includes(p.status)
      ).length,
      topics,
      vectorBackend: null, // TODO: fetch from API
    };
  }, [papers]);

  // Available topics
  const availableTopics = useMemo(() => {
    const topics = new Set<string>();
    papers.forEach((p) => p.topics?.forEach((t) => topics.add(t)));
    return Array.from(topics).sort();
  }, [papers]);

  // Handlers
  const handleSelect = useCallback((id: string, selected: boolean) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (selected) next.add(id);
      else next.delete(id);
      return next;
    });
  }, []);

  // Debug: 包装 setPage 以追踪调用来源
  const setPageDebug = useCallback((newPage: number | ((prev: number) => number)) => {
    console.log('[Debug] setPage called with:', newPage, 'at', new Date().toLocaleTimeString());
    console.log('[Debug] Stack trace:', new Error().stack);
    setPage(newPage);
  }, []);

  const handleSelectAll = useCallback(() => {
    const startIndex = (page - 1) * PAGE_SIZE;
    const pagePapers = filteredPapers.slice(startIndex, startIndex + PAGE_SIZE);
    const allSelected = pagePapers.every((p) => selectedIds.has(p.paper_id));

    setSelectedIds((prev) => {
      const next = new Set(prev);
      pagePapers.forEach((p) => {
        if (allSelected) next.delete(p.paper_id);
        else next.add(p.paper_id);
      });
      return next;
    });
  }, [filteredPapers, page, selectedIds]);

  const handleClearSelection = useCallback(() => {
    setSelectedIds(new Set());
  }, []);

  const handleDelete = useCallback(async (paper: Paper) => {
    try {
      await deletePaper(paper.paper_id);
      toast.success('论文已删除');
      setDeletePaperData(null);
      handleSelect(paper.paper_id, false);
      void refresh();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '删除失败');
    }
  }, [handleSelect, refresh]);

  const handleRebuild = useCallback(async (paper: Paper) => {
    try {
      await rebuildPaper(paper.paper_id);
      toast.success('已标记重建');
      setRebuildPaperData(null);
      void refresh();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '重建失败');
    }
  }, [refresh]);

  const handleRetry = useCallback(async (paper: Paper) => {
    try {
      await retryPaper(paper.paper_id);
      toast.success('已进入重试队列');
      void refresh();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '重试失败');
    }
  }, [refresh]);

  const handleBulkDelete = useCallback(async () => {
    const ids = Array.from(selectedIds);
    if (ids.length === 0) return;

    try {
      const result = await bulkDeletePapers(ids);
      if (result.ok) {
        toast.success(`成功删除 ${result.succeeded} 篇论文`);
      } else {
        toast.error(`${result.failed} 篇删除失败`);
      }
      setShowBulkDeleteDialog(false);
      handleClearSelection();
      void refresh();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '批量删除失败');
    }
  }, [selectedIds, handleClearSelection, refresh]);

  const handleBulkRebuild = useCallback(async () => {
    const ids = Array.from(selectedIds);
    if (ids.length === 0) return;

    try {
      const result = await bulkRebuildPapers(ids);
      if (result.ok) {
        toast.success(`成功标记 ${result.succeeded} 篇论文重建`);
      } else {
        toast.error(`${result.failed} 篇重建失败`);
      }
      setShowBulkRebuildDialog(false);
      handleClearSelection();
      void refresh();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '批量重建失败');
    }
  }, [selectedIds, handleClearSelection, refresh]);

  // 筛选回调函数 - 使用 useCallback 避免不必要的重渲染
  const handleSearchChange = useCallback((q: string) => {
    setSearchQuery(q);
    setPage(1);
  }, []);

  const handleStatusChange = useCallback((s: string | null) => {
    setStatusFilter(s);
    setPage(1);
  }, []);

  const handleTopicChange = useCallback((t: string | null) => {
    setTopicFilter(t);
    setPage(1);
  }, []);

  const handlePageChange = useCallback((newPage: number) => {
    setPage(newPage);
  }, []);

  // Selected papers for bulk dialog
  const selectedPapers = useMemo(
    () => papers.filter((p) => selectedIds.has(p.paper_id)),
    [papers, selectedIds]
  );

  return (
    <section className="glass-card rounded-[34px] p-5 md:p-6">
      {/* Header */}
      <header className="mb-5 flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">
            知识库
          </p>
          <h2 className="mt-2 text-[32px] font-semibold tracking-tight text-slate-950">
            知识库管理
          </h2>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
            查看、搜索、删除和重建已导入的论文。支持批量操作。
          </p>
        </div>
        <button
          type="button"
          onClick={() => void refresh()}
          disabled={loading}
          className="rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm text-slate-600 hover:bg-slate-50 disabled:opacity-50"
        >
          {loading ? '刷新中...' : '刷新'}
        </button>
      </header>

      <div className="grid gap-4 lg:grid-cols-[280px_1fr]">
        {/* Sidebar - Stats */}
        <aside className="space-y-4">
          <LibraryStats stats={stats} />
        </aside>

        {/* Main Content */}
        <div className="space-y-4">
          {/* Filters */}
          <PaperFilters
            searchQuery={searchQuery}
            onSearchChange={handleSearchChange}
            statusFilter={statusFilter}
            onStatusChange={handleStatusChange}
            topicFilter={topicFilter}
            onTopicChange={handleTopicChange}
            availableTopics={availableTopics}
          />

          {/* Error */}
          {error && (
            <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
              {error}
            </div>
          )}

          {/* Paper List */}
          <PaperList
            papers={filteredPapers}
            selectedIds={selectedIds}
            onSelect={handleSelect}
            onSelectAll={handleSelectAll}
            onView={setDetailPaper}
            onDelete={setDeletePaperData}
            onRebuild={setRebuildPaperData}
            onRetry={handleRetry}
            page={page}
            pageSize={PAGE_SIZE}
            onPageChange={handlePageChange}
          />
        </div>
      </div>

      {/* Bulk Toolbar */}
      <PaperBulkToolbar
        selectedCount={selectedIds.size}
        onDelete={() => setShowBulkDeleteDialog(true)}
        onRebuild={() => setShowBulkRebuildDialog(true)}
        onClear={handleClearSelection}
      />

      {/* Detail Modal */}
      <PaperDetailModal
        paper={detailPaper}
        isOpen={!!detailPaper}
        onClose={() => setDetailPaper(null)}
      />

      {/* Delete Confirm */}
      <ConfirmDialog
        isOpen={!!deletePaperData}
        title="确认删除"
        message={`确定要删除《${deletePaperData?.title || '这篇论文'}》吗？\n\n这将移除：\n• 论文元数据\n• 向量索引\n• 专题关联\n• 处理产物`}
        confirmLabel="删除"
        confirmVariant="danger"
        onConfirm={() => deletePaperData && void handleDelete(deletePaperData)}
        onCancel={() => setDeletePaperData(null)}
      />

      {/* Rebuild Confirm */}
      <ConfirmDialog
        isOpen={!!rebuildPaperData}
        title="确认重建"
        message={`确定要重建《${rebuildPaperData?.title || '这篇论文'}》的索引吗？\n\n这将重新构建该论文的向量索引。`}
        confirmLabel="重建"
        onConfirm={() => rebuildPaperData && void handleRebuild(rebuildPaperData)}
        onCancel={() => setRebuildPaperData(null)}
      />

      {/* Bulk Delete Confirm */}
      <ConfirmDialog
        isOpen={showBulkDeleteDialog}
        title="确认批量删除"
        message={`即将删除 ${selectedIds.size} 篇论文：\n\n${selectedPapers
          .slice(0, 5)
          .map((p) => `• ${p.title || p.paper_id}`)
          .join('\n')}${selectedPapers.length > 5 ? `\n等 ${selectedPapers.length - 5} 篇...` : ''}\n\n警告：此操作不可恢复！`}
        confirmLabel="批量删除"
        confirmVariant="danger"
        onConfirm={() => void handleBulkDelete()}
        onCancel={() => setShowBulkDeleteDialog(false)}
      />

      {/* Bulk Rebuild Confirm */}
      <ConfirmDialog
        isOpen={showBulkRebuildDialog}
        title="确认批量重建"
        message={`确定要重建 ${selectedIds.size} 篇论文的索引吗？`}
        confirmLabel="批量重建"
        onConfirm={() => void handleBulkRebuild()}
        onCancel={() => setShowBulkRebuildDialog(false)}
      />
    </section>
  );
}
