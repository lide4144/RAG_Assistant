'use client';

import { useState, useEffect } from 'react';
import { Search, Filter } from 'lucide-react';
import { statusOptions } from '../types/library';

interface PaperFiltersProps {
  searchQuery: string;
  onSearchChange: (query: string) => void;
  statusFilter: string | null;
  onStatusChange: (status: string | null) => void;
  topicFilter: string | null;
  onTopicChange: (topic: string | null) => void;
  availableTopics: string[];
}

export function PaperFilters({
  searchQuery,
  onSearchChange,
  statusFilter,
  onStatusChange,
  topicFilter,
  onTopicChange,
  availableTopics,
}: PaperFiltersProps) {
  const [localQuery, setLocalQuery] = useState(searchQuery);

  useEffect(() => {
    const timer = setTimeout(() => {
      onSearchChange(localQuery);
    }, 300);
    return () => clearTimeout(timer);
  }, [localQuery, onSearchChange]);

  return (
    <div className="flex flex-wrap items-center gap-3">
      {/* Search */}
      <div className="relative flex-1 min-w-[200px]">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
        <input
          type="text"
          value={localQuery}
          onChange={(e) => setLocalQuery(e.target.value)}
          placeholder="搜索标题或来源..."
          className="w-full rounded-xl border border-slate-200 bg-white pl-10 pr-4 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
        />
      </div>

      {/* Status Filter */}
      <div className="relative">
        <Filter className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
        <select
          value={statusFilter || ''}
          onChange={(e) => onStatusChange(e.target.value || null)}
          className="appearance-none rounded-xl border border-slate-200 bg-white pl-10 pr-8 py-2 text-sm text-slate-900 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
        >
          {statusOptions.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </div>

      {/* Topic Filter */}
      {availableTopics.length > 0 && (
        <div className="relative">
          <Filter className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <select
            value={topicFilter || ''}
            onChange={(e) => onTopicChange(e.target.value || null)}
            className="appearance-none rounded-xl border border-slate-200 bg-white pl-10 pr-8 py-2 text-sm text-slate-900 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
          >
            <option value="">全部专题</option>
            {availableTopics.map((topic) => (
              <option key={topic} value={topic}>
                {topic}
              </option>
            ))}
          </select>
        </div>
      )}
    </div>
  );
}
