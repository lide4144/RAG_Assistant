import { useEffect, useRef, useState, useCallback } from 'react';
import { listPapers } from './library-api';
import type { Paper, ListPapersParams } from '../types/library';

interface UsePapersPollOptions {
  intervalMs?: number;
  params?: ListPapersParams;
  enabled?: boolean;
}

interface UsePapersPollReturn {
  papers: Paper[];
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  lastUpdated: Date | null;
}

export function usePapersPoll(options: UsePapersPollOptions = {}): UsePapersPollReturn {
  const { intervalMs = 10000, params = {}, enabled = true } = options;

  const [papers, setPapers] = useState<Paper[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const intervalRef = useRef<NodeJS.Timeout | null>(null);
  const paramsRef = useRef(params);

  // Keep params ref updated
  useEffect(() => {
    paramsRef.current = params;
  }, [params]);

  const fetchPapers = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await listPapers(paramsRef.current);
      setPapers(data);
      setLastUpdated(new Date());
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载失败');
    } finally {
      setLoading(false);
    }
  }, []);

  const refresh = useCallback(async () => {
    await fetchPapers();
  }, [fetchPapers]);

  useEffect(() => {
    if (!enabled) {
      return;
    }

    // Initial fetch
    void fetchPapers();

    // Set up interval
    intervalRef.current = setInterval(() => {
      void fetchPapers();
    }, intervalMs);

    // Handle visibility change
    const handleVisibilityChange = () => {
      if (document.hidden) {
        // Pause polling when page is hidden
        if (intervalRef.current) {
          clearInterval(intervalRef.current);
          intervalRef.current = null;
        }
      } else {
        // Resume polling when page is visible
        void fetchPapers();
        intervalRef.current = setInterval(() => {
          void fetchPapers();
        }, intervalMs);
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, [enabled, intervalMs, fetchPapers]);

  return {
    papers,
    loading,
    error,
    refresh,
    lastUpdated,
  };
}
