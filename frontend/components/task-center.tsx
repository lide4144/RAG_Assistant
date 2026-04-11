'use client';

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { fetchAdminJson } from '../lib/admin-http';
import { resolveGatewayWebSocketUrl, resolveKernelApiUrl } from '../lib/deployment-endpoints';
import type { JobEvent, JobStatus } from '../lib/types';

type TaskCenterContextValue = {
  activeJobs: JobStatus[];
  ensureTrackedJobs: (jobIds: string[]) => void;
  jobEventsById: Record<string, JobEvent[]>;
  jobsById: Record<string, JobStatus>;
  refreshJob: (jobId: string) => Promise<void>;
  registerJob: (job: JobStatus) => void;
};

const trackedJobsStorageKey = 'rag-workbench-task-center-v1';
const pollIntervalMs = 2000;
const websocketReconnectDelayMs = 1000;

const TaskCenterContext = createContext<TaskCenterContextValue | null>(null);

type GatewayJobStreamEvent =
  | {
      type: 'message';
      jobId?: string;
      seq?: number;
      createdAt?: string;
      traceId: string;
      mode: 'local' | 'web' | 'hybrid';
      content: string;
    }
  | {
      type: 'sources';
      jobId?: string;
      seq?: number;
      createdAt?: string;
      traceId: string;
      mode: 'local' | 'web' | 'hybrid';
      runId?: string;
      sources: Array<Record<string, unknown>>;
    }
  | {
      type: 'messageEnd';
      jobId?: string;
      seq?: number;
      createdAt?: string;
      traceId: string;
      mode: 'local' | 'web' | 'hybrid';
      runId?: string;
    }
  | {
      type: 'error';
      jobId?: string;
      seq?: number;
      createdAt?: string;
      traceId: string;
      code: string;
      message: string;
    };

export function TaskCenterProvider({ children }: { children: ReactNode }) {
  const [jobsById, setJobsById] = useState<Record<string, JobStatus>>({});
  const [jobEventsById, setJobEventsById] = useState<Record<string, JobEvent[]>>({});
  const [trackedJobIds, setTrackedJobIds] = useState<string[]>([]);
  const [hydrated, setHydrated] = useState(false);

  const lastSeqByJobIdRef = useRef<Record<string, number>>({});
  const trackedJobIdsRef = useRef<string[]>([]);
  const wsRef = useRef<WebSocket | null>(null);
  const wsReconnectTimerRef = useRef<number | null>(null);
  const wsSubscriptionsRef = useRef<Set<string>>(new Set());
  const gatewayWsUrl = useMemo(() => resolveGatewayWebSocketUrl(), []);

  useEffect(() => {
    trackedJobIdsRef.current = trackedJobIds;
  }, [trackedJobIds]);

  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(trackedJobsStorageKey);
      if (!raw) {
        setHydrated(true);
        return;
      }
      const parsed = JSON.parse(raw) as { trackedJobIds?: string[] };
      const nextTracked = Array.isArray(parsed.trackedJobIds)
        ? [...new Set(parsed.trackedJobIds.filter((item) => typeof item === 'string' && item.trim().length > 0))]
        : [];
      setTrackedJobIds(nextTracked);
    } catch {
      setTrackedJobIds([]);
    } finally {
      setHydrated(true);
    }
  }, []);

  useEffect(() => {
    if (!hydrated) {
      return;
    }
    try {
      window.localStorage.setItem(trackedJobsStorageKey, JSON.stringify({ trackedJobIds }));
    } catch {
      // ignore storage failures
    }
  }, [hydrated, trackedJobIds]);

  const ensureTrackedJobs = useCallback((jobIds: string[]) => {
    const normalized = [...new Set(jobIds.map((item) => item.trim()).filter(Boolean))];
    if (!normalized.length) {
      return;
    }
    setTrackedJobIds((prev) => {
      const merged = [...new Set([...prev, ...normalized])];
      return merged.length === prev.length ? prev : merged;
    });
  }, []);

  const stopTrackingJobs = useCallback((jobIds: string[]) => {
    const normalized = [...new Set(jobIds.map((item) => item.trim()).filter(Boolean))];
    if (!normalized.length) {
      return;
    }
    setTrackedJobIds((prev) => {
      const next = prev.filter((item) => !normalized.includes(item));
      return next.length === prev.length ? prev : next;
    });
  }, []);

  const registerJob = useCallback(
    (job: JobStatus) => {
      setJobsById((prev) => ({ ...prev, [job.job_id]: job }));
      ensureTrackedJobs([job.job_id]);
    },
    [ensureTrackedJobs]
  );

  const appendJobEvents = useCallback((jobId: string, incomingEvents: JobEvent[]) => {
    if (!incomingEvents.length) {
      return;
    }
    setJobEventsById((prev) => {
      const existing = prev[jobId] ?? [];
      const seen = new Set(existing.map((item) => item.seq));
      const nextEvents = incomingEvents
        .filter((item) => Number.isInteger(item.seq) && item.seq > 0 && !seen.has(item.seq))
        .sort((left, right) => left.seq - right.seq);
      if (!nextEvents.length) {
        return prev;
      }
      const merged = [...existing, ...nextEvents].sort((left, right) => left.seq - right.seq);
      lastSeqByJobIdRef.current[jobId] = merged[merged.length - 1]?.seq ?? lastSeqByJobIdRef.current[jobId] ?? 0;
      return { ...prev, [jobId]: merged };
    });
  }, []);

  const refreshJob = useCallback(async (jobId: string) => {
    const normalizedJobId = jobId.trim();
    if (!normalizedJobId) {
      return;
    }

    const [jobResult, eventsResult] = await Promise.all([
      fetchAdminJson<JobStatus>(resolveKernelApiUrl(`/api/jobs/${encodeURIComponent(normalizedJobId)}`)),
      fetchAdminJson<JobEvent[]>(
        resolveKernelApiUrl(
          `/api/jobs/${encodeURIComponent(normalizedJobId)}/events?after_seq=${lastSeqByJobIdRef.current[normalizedJobId] ?? 0}&limit=500`
        )
      )
    ]);

    if (jobResult.ok) {
      setJobsById((prev) => ({ ...prev, [normalizedJobId]: jobResult.data }));
      if (jobResult.data.state !== 'queued' && jobResult.data.state !== 'running') {
        stopTrackingJobs([normalizedJobId]);
      }
    } else if (jobResult.status === 404) {
      stopTrackingJobs([normalizedJobId]);
    }

    if (eventsResult.ok && eventsResult.data.length > 0) {
      appendJobEvents(normalizedJobId, eventsResult.data);
    }
  }, [appendJobEvents, stopTrackingJobs]);

  const subscribeJobStream = useCallback((jobId: string) => {
    const ws = wsRef.current;
    const normalizedJobId = jobId.trim();
    if (!normalizedJobId || !ws || ws.readyState !== WebSocket.OPEN || wsSubscriptionsRef.current.has(normalizedJobId)) {
      return;
    }
    ws.send(
      JSON.stringify({
        type: 'job_subscribe',
        payload: {
          jobId: normalizedJobId,
          afterSeq: lastSeqByJobIdRef.current[normalizedJobId] ?? 0
        }
      })
    );
    wsSubscriptionsRef.current.add(normalizedJobId);
  }, []);

  const handleGatewayEvent = useCallback(
    (event: GatewayJobStreamEvent) => {
      const seq = event.seq;
      if (!event.jobId || typeof seq !== 'number' || !Number.isInteger(seq) || seq <= 0) {
        return;
      }
      const createdAt = typeof event.createdAt === 'string' && event.createdAt ? event.createdAt : new Date().toISOString();
      let nextEvent: JobEvent | null = null;
      if (event.type === 'message') {
        nextEvent = {
          job_id: event.jobId,
          seq,
          event_type: 'message',
          created_at: createdAt,
          payload: { type: 'message', traceId: event.traceId, mode: event.mode, content: event.content }
        };
      } else if (event.type === 'sources') {
        nextEvent = {
          job_id: event.jobId,
          seq,
          event_type: 'sources',
          created_at: createdAt,
          payload: { type: 'sources', traceId: event.traceId, mode: event.mode, runId: event.runId, sources: event.sources }
        };
      } else if (event.type === 'messageEnd') {
        nextEvent = {
          job_id: event.jobId,
          seq,
          event_type: 'messageEnd',
          created_at: createdAt,
          payload: { type: 'messageEnd', traceId: event.traceId, mode: event.mode, runId: event.runId }
        };
      } else if (event.type === 'error') {
        nextEvent = {
          job_id: event.jobId,
          seq,
          event_type: 'error',
          created_at: createdAt,
          payload: { type: 'error', traceId: event.traceId, code: event.code, message: event.message }
        };
      }
      if (!nextEvent) {
        return;
      }
      appendJobEvents(event.jobId, [nextEvent]);
      if (event.type === 'messageEnd' || event.type === 'error') {
        void refreshJob(event.jobId);
      }
    },
    [appendJobEvents, refreshJob]
  );

  useEffect(() => {
    if (!hydrated || !gatewayWsUrl) {
      return;
    }
    let disposed = false;

    const clearReconnectTimer = () => {
      if (wsReconnectTimerRef.current !== null) {
        window.clearTimeout(wsReconnectTimerRef.current);
        wsReconnectTimerRef.current = null;
      }
    };

    const connect = () => {
      if (disposed) {
        return;
      }
      const ws = new WebSocket(gatewayWsUrl);
      wsRef.current = ws;
      wsSubscriptionsRef.current = new Set();

      ws.onopen = () => {
        trackedJobIdsRef.current.forEach((jobId) => subscribeJobStream(jobId));
      };

      ws.onmessage = (messageEvent) => {
        try {
          const parsed = JSON.parse(messageEvent.data) as GatewayJobStreamEvent;
          handleGatewayEvent(parsed);
        } catch {
          // ignore malformed websocket payloads
        }
      };

      ws.onclose = () => {
        if (wsRef.current === ws) {
          wsRef.current = null;
        }
        wsSubscriptionsRef.current = new Set();
        if (disposed) {
          return;
        }
        clearReconnectTimer();
        wsReconnectTimerRef.current = window.setTimeout(connect, websocketReconnectDelayMs);
      };

      ws.onerror = () => {
        ws.close();
      };
    };

    connect();
    return () => {
      disposed = true;
      clearReconnectTimer();
      wsSubscriptionsRef.current = new Set();
      const ws = wsRef.current;
      wsRef.current = null;
      ws?.close();
    };
  }, [gatewayWsUrl, handleGatewayEvent, hydrated, subscribeJobStream]);

  useEffect(() => {
    if (!hydrated) {
      return;
    }
    trackedJobIds.forEach((jobId) => subscribeJobStream(jobId));
  }, [hydrated, subscribeJobStream, trackedJobIds]);

  useEffect(() => {
    if (!hydrated) {
      return;
    }
    let cancelled = false;

    const syncActiveJobs = async () => {
      const result = await fetchAdminJson<JobStatus[]>(resolveKernelApiUrl('/api/jobs?state=queued,running&limit=100'));
      if (!result.ok || cancelled) {
        return;
      }
      const activeIds = result.data.map((item) => item.job_id).filter(Boolean);
      if (activeIds.length) {
        setJobsById((prev) => {
          const next = { ...prev };
          result.data.forEach((item) => {
            next[item.job_id] = item;
          });
          return next;
        });
        ensureTrackedJobs(activeIds);
      }
    };

    void syncActiveJobs();
    const timer = window.setInterval(() => void syncActiveJobs(), 5000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [ensureTrackedJobs, hydrated]);

  useEffect(() => {
    if (!hydrated || !trackedJobIds.length) {
      return;
    }
    let cancelled = false;

    const syncTrackedJobs = async () => {
      const ids = trackedJobIdsRef.current;
      if (!ids.length) {
        return;
      }
      await Promise.all(
        ids.map(async (jobId) => {
          try {
            await refreshJob(jobId);
          } catch {
            if (cancelled) {
              return;
            }
          }
        })
      );
    };

    void syncTrackedJobs();
    const timer = window.setInterval(() => void syncTrackedJobs(), pollIntervalMs);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [hydrated, refreshJob, trackedJobIds]);

  const activeJobs = useMemo(
    () =>
      Object.values(jobsById)
        .filter((item) => item.state === 'queued' || item.state === 'running')
        .sort((a, b) => +new Date(b.updated_at) - +new Date(a.updated_at)),
    [jobsById]
  );

  const value = useMemo<TaskCenterContextValue>(
    () => ({
      activeJobs,
      ensureTrackedJobs,
      jobEventsById,
      jobsById,
      refreshJob,
      registerJob
    }),
    [activeJobs, ensureTrackedJobs, jobEventsById, jobsById, refreshJob, registerJob]
  );

  return <TaskCenterContext.Provider value={value}>{children}</TaskCenterContext.Provider>;
}

export function useTaskCenter(): TaskCenterContextValue {
  const context = useContext(TaskCenterContext);
  if (context === null) {
    throw new Error('useTaskCenter must be used within TaskCenterProvider');
  }
  return context;
}
