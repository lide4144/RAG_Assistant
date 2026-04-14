'use client';

import { X, FileText, Clock, Tag, Activity } from 'lucide-react';
import type { Paper } from '../types/library';
import { statusStyles } from '../types/library';

interface PaperDetailModalProps {
  paper: Paper | null;
  isOpen: boolean;
  onClose: () => void;
}

export function PaperDetailModal({ paper, isOpen, onClose }: PaperDetailModalProps) {
  if (!isOpen || !paper) return null;

  const statusStyle = statusStyles[paper.status] || statusStyles.imported;

  const formatDate = (dateStr: string) => {
    if (!dateStr) return '-';
    const date = new Date(dateStr);
    if (isNaN(date.getTime())) return dateStr;
    return date.toLocaleString('zh-CN', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const stages = [
    { key: 'import', label: '导入' },
    { key: 'parse', label: '解析' },
    { key: 'clean', label: '清洗' },
    { key: 'index', label: '索引' },
    { key: 'graph', label: '图谱' },
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-slate-900/50 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="relative w-full max-w-lg rounded-[28px] border border-slate-200 bg-white p-6 shadow-2xl">
        {/* Header */}
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-slate-100">
              <FileText className="h-5 w-5 text-slate-600" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-slate-900">论文详情</h2>
              <p className="text-xs text-slate-500">ID: {paper.paper_id}</p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-2 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Content */}
        <div className="mt-6 space-y-4">
          {/* Title */}
          <div>
            <h3 className="text-sm font-medium text-slate-900">
              {paper.title || '无标题'}
            </h3>
            <p className="mt-1 text-xs text-slate-500 break-all">
              {paper.source_uri}
            </p>
          </div>

          {/* Status */}
          <div className="flex items-center gap-2">
            <span
              className={`inline-flex items-center gap-1 rounded-full border px-3 py-1 text-xs font-medium ${statusStyle.border} ${statusStyle.bg}`}
            >
              <span>{statusStyle.icon}</span>
              {statusStyle.label}
            </span>
          </div>

          {/* Topics */}
          {paper.topics && paper.topics.length > 0 && (
            <div className="flex items-start gap-2">
              <Tag className="mt-0.5 h-4 w-4 text-slate-400" />
              <div className="flex flex-wrap gap-1">
                {paper.topics.map((topic) => (
                  <span
                    key={topic}
                    className="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-xs text-slate-600"
                  >
                    {topic}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Date */}
          <div className="flex items-center gap-2 text-sm text-slate-600">
            <Clock className="h-4 w-4 text-slate-400" />
            <span>导入时间: {formatDate(paper.imported_at)}</span>
          </div>

          {/* Stage Statuses */}
          {paper.stage_statuses && Object.keys(paper.stage_statuses).length > 0 && (
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
              <div className="flex items-center gap-2 mb-3">
                <Activity className="h-4 w-4 text-slate-400" />
                <span className="text-xs font-medium text-slate-700">处理阶段</span>
              </div>
              <div className="grid grid-cols-5 gap-2">
                {stages.map(({ key, label }) => {
                  const stageStatus = paper.stage_statuses?.[key];
                  const state = stageStatus?.state?.toLowerCase() || 'pending';
                  const isDone = state === 'done' || state === 'succeeded';
                  const isFailed = state === 'failed';
                  const isRunning = state === 'running' || state === 'queued';

                  return (
                    <div
                      key={key}
                      className={`rounded-lg border px-2 py-2 text-center ${
                        isDone
                          ? 'border-emerald-200 bg-emerald-50'
                          : isFailed
                          ? 'border-rose-200 bg-rose-50'
                          : isRunning
                          ? 'border-sky-200 bg-sky-50'
                          : 'border-slate-200 bg-white'
                      }`}
                    >
                      <p
                        className={`text-[10px] font-medium ${
                          isDone
                            ? 'text-emerald-700'
                            : isFailed
                            ? 'text-rose-700'
                            : isRunning
                            ? 'text-sky-700'
                            : 'text-slate-500'
                        }`}
                      >
                        {isDone ? '✓' : isFailed ? '✗' : isRunning ? '⏳' : '○'} {label}
                      </p>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="mt-6 flex justify-end">
          <button
            type="button"
            onClick={onClose}
            className="rounded-xl bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800"
          >
            关闭
          </button>
        </div>
      </div>
    </div>
  );
}
