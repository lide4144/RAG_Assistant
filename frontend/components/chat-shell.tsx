'use client';

import Link from 'next/link';
import {
  Bot,
  ChevronRight,
  Clock3,
  Globe,
  History,
  MessageSquarePlus,
  Network,
  SearchCheck,
  Sparkles,
  Trash2
} from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import type { AgentEvent, ChatMessage, ChatMode, JobCreateResponse, JobEvent, JobStatus, LlmDebugTrace, RuntimeOverview, SourceItem, ViewMode } from '../lib/types';
import { fetchAdminJson } from '../lib/admin-http';
import { resolveAdminUrl, resolveKernelApiUrl } from '../lib/deployment-endpoints';
import { buildGraphSubgraph } from '../lib/graph';
import { mapConnectionStatus, mapRuntimeLevel } from '../lib/status-mapper';
import { GraphSubgraphPanel } from './graph-subgraph';
import { useTaskCenter } from './task-center';
import { StructuredAnswer } from './structured-answer';

type SendErrorState = {
  message: string;
  code?: string;
  detail?: string;
};

type LlmDebugState = {
  loading: boolean;
  records: LlmDebugTrace['records'];
  error?: string;
};

type ExecutionTimelineStep = {
  key: string;
  label: string;
  description: string;
  status: 'done' | 'active' | 'pending';
  meta?: string;
};

type ChatSessionSummary = {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  preview: string;
  messageCount: number;
};

type StoredChatSession = ChatSessionSummary & { messages?: ChatMessage[] };

const modeOptions: Array<{ key: ChatMode; label: string; hint: string; icon: typeof SearchCheck }> = [
  { key: 'local', label: '仅知识库', hint: '只看已导入资料', icon: SearchCheck },
  { key: 'web', label: '联网补充', hint: '补一点公开信息', icon: Globe },
  { key: 'hybrid', label: '混合回答', hint: '资料和网络一起看', icon: Network }
];

const viewModeOptions: Array<{ key: ViewMode; label: string }> = [
  { key: 'user', label: '简洁视图' },
  { key: 'developer', label: '排障视图' }
];

const promptSuggestions = [
  '总结当前知识库里关于 GraphRAG 的核心方法差异',
  '给我一份最近导入论文的关键贡献对比表',
  '基于现有证据回答：为什么这套方案更稳健？',
  '列出可直接落地到生产环境的三项改进建议'
];

const waitingMoments = [
  '顺手想想下一句要不要限定输出格式，比如“按表格列出”。',
  '如果你只想看资料内结论，下一轮可以直接补一句“不要联网”。',
  '回答太散时，继续追问“只保留 3 个最重要结论”通常会更清楚。',
  '想更稳一点，可以让它“先列证据，再给结论”。'
];

const storageKey = 'rag-workbench-chat-history-v1';
const activeSessionStorageKey = 'rag-workbench-chat-active-session-v1';
const defaultConfigPath = 'configs/default.yaml';

export function ChatShell() {
  const [mode, setMode] = useState<ChatMode>('local');
  const [viewMode, setViewMode] = useState<ViewMode>('user');
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [selectedCitation, setSelectedCitation] = useState<number | null>(null);
  const [expandedGraphByMessage, setExpandedGraphByMessage] = useState<Record<string, boolean>>({});
  const [sendError, setSendError] = useState<SendErrorState | null>(null);
  const [isSending, setIsSending] = useState(false);
  const [runtimeOverview, setRuntimeOverview] = useState<RuntimeOverview | null>(null);
  const [runtimeOverviewError, setRuntimeOverviewError] = useState('');
  const [lastFailedQuery, setLastFailedQuery] = useState('');
  const [sessionHistory, setSessionHistory] = useState<ChatSessionSummary[]>([]);
  const [activeSessionId, setActiveSessionId] = useState('');
  const [historyHydrated, setHistoryHydrated] = useState(false);
  const [llmDebugByTrace, setLlmDebugByTrace] = useState<Record<string, LlmDebugState>>({});
  const [loadingBeat, setLoadingBeat] = useState(0);
  const { ensureTrackedJobs, jobEventsById, jobsById, refreshJob, registerJob } = useTaskCenter();

  const messageBottomRef = useRef<HTMLDivElement | null>(null);
  const sessionIdRef = useRef(crypto.randomUUID());

  const runtimeOverviewUrl = useMemo(() => resolveAdminUrl('/api/admin/runtime-overview'), []);
  const statusLevel = runtimeOverview?.status?.level ?? 'ERROR';
  const answerConfigured = Boolean(runtimeOverview?.llm?.answer?.configured);
  const plannerChatAvailable = runtimeOverview?.planner?.formal_chat_available === true;
  const plannerBlockMessage = runtimeOverview?.planner?.block_reason_message || 'Planner Runtime 当前不可服务，请先修复规划模型配置。';
  const plannerRequired = mode === 'local';
  const plannerReady = !plannerRequired || plannerChatAvailable;
  const statusText = runtimeOverviewError ? 'Connection error' : 'Connected';
  const canSend = input.trim().length > 0 && answerConfigured && statusLevel !== 'BLOCKED' && plannerReady;
  const connection = mapConnectionStatus(statusText);
  const runtimeView = mapRuntimeLevel(statusLevel);

  useEffect(() => {
    let mounted = true;
    const loadRuntimeOverview = async () => {
      try {
        const result = await fetchAdminJson<RuntimeOverview>(runtimeOverviewUrl);
        if (!result.ok || !mounted) {
          setRuntimeOverview(null);
          setRuntimeOverviewError('运行态概览不可用，请检查内核服务。');
          return;
        }
        setRuntimeOverview(result.data);
        setRuntimeOverviewError('');
      } catch {
        if (mounted) {
          setRuntimeOverview(null);
          setRuntimeOverviewError('运行态概览不可用，请检查内核服务。');
        }
      }
    };

    void loadRuntimeOverview();
    return () => {
      mounted = false;
    };
  }, [runtimeOverviewUrl]);

  useEffect(() => {
    const trackedJobIds = messages.map((item) => item.jobId).filter((item): item is string => Boolean(item));
    if (!trackedJobIds.length) {
      return;
    }
    ensureTrackedJobs(trackedJobIds);
  }, [ensureTrackedJobs, messages]);

  useEffect(() => {
    setMessages((prev) => {
      let changed = false;
      const next = prev.map((item) => {
        if (item.role !== 'assistant' || !item.jobId) {
          return item;
        }
        const materialized = materializeJobBackedAssistantMessage(item, jobsById[item.jobId], jobEventsById[item.jobId] ?? []);
        if (chatMessageEquals(item, materialized)) {
          return item;
        }
        changed = true;
        return materialized;
      });
      return changed ? next : prev;
    });
  }, [jobEventsById, jobsById]);

  useEffect(() => {
    const activeStreaming = messages.some((item) => {
      if (item.role !== 'assistant' || !item.jobId) {
        return false;
      }
      const state = jobsById[item.jobId]?.state;
      return state === 'queued' || state === 'running' || item.status === 'streaming';
    });
    setIsSending(activeStreaming);
  }, [jobsById, messages]);

  useEffect(() => {
    if (!isSending) {
      setLoadingBeat(0);
      return;
    }
    const timer = window.setInterval(() => {
      setLoadingBeat((prev) => prev + 1);
    }, 2200);
    return () => window.clearInterval(timer);
  }, [isSending]);

  useEffect(() => {
    if (viewMode !== 'developer') {
      return;
    }
    const pendingTraceIds = [
      ...new Set(
        messages
          .filter((item) => item.role === 'assistant' && (item.jobId || item.traceId))
          .map((item) => buildLlmDebugKey(item))
          .filter((key) => key.length > 0 && llmDebugByTrace[key] === undefined)
      ),
    ];
    if (!pendingTraceIds.length) {
      return;
    }
    let cancelled = false;
    pendingTraceIds.forEach((debugKey) => {
      setLlmDebugByTrace((prev) => ({ ...prev, [debugKey]: { loading: true, records: [] } }));
      const endpoint = debugKey.startsWith('job:')
        ? resolveAdminUrl(`/api/jobs/${encodeURIComponent(debugKey.slice(4))}/llm-debug`)
        : resolveAdminUrl(`/api/admin/llm-debug/${encodeURIComponent(debugKey.slice(6))}`);
      void fetchAdminJson<LlmDebugTrace>(endpoint).then((result) => {
        if (cancelled) {
          return;
        }
        if (result.ok) {
          setLlmDebugByTrace((prev) => ({
            ...prev,
            [debugKey]: { loading: false, records: result.data.records }
          }));
          return;
        }
        setLlmDebugByTrace((prev) => ({
          ...prev,
          [debugKey]: {
            loading: false,
            records: [],
            error: result.status === 404 ? '暂无模型调试记录。' : result.message
          }
        }));
      });
    });
    return () => {
      cancelled = true;
    };
  }, [llmDebugByTrace, messages, viewMode]);

  useEffect(() => {
    try {
      const sessions = loadStoredSessions();
      if (!sessions.length) {
        const newId = sessionIdRef.current;
        setActiveSessionId(newId);
        setHistoryHydrated(true);
        return;
      }
      const sorted = sortSessionsByUpdatedAt(sessions);
      const persistedActiveSessionId = loadStoredActiveSessionId();
      const current = sorted.find((item) => item.id === persistedActiveSessionId) ?? sorted[0];
      sessionIdRef.current = current.id;
      setActiveSessionId(current.id);
      setSessionHistory(sorted.map(toSessionSummary));
      setMessages(Array.isArray(current.messages) ? current.messages : []);
      setHistoryHydrated(true);
    } catch {
      setActiveSessionId(sessionIdRef.current);
      setHistoryHydrated(true);
    }
  }, []);

  useEffect(() => {
    if (!historyHydrated || !activeSessionId) {
      return;
    }
    saveStoredActiveSessionId(activeSessionId);
  }, [activeSessionId, historyHydrated]);

  useEffect(() => {
    messageBottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages]);

  useEffect(() => {
    if (!historyHydrated) {
      return;
    }
    const sessionId = activeSessionId || sessionIdRef.current;
    if (!sessionId) {
      return;
    }
    const storedSessions = loadStoredSessions();

    if (!messages.length) {
      const nextStored = storedSessions.filter((item) => item.id !== sessionId);
      saveStoredSessions(nextStored);
      setSessionHistory(sortSessionsByUpdatedAt(nextStored).map(toSessionSummary));
      return;
    }

    const existing = storedSessions.find((item) => item.id === sessionId);
    const summary = buildSessionSummary(sessionId, messages, existing?.createdAt);
    const nextStored = sortSessionsByUpdatedAt([
      { ...summary, messages },
      ...storedSessions.filter((item) => item.id !== sessionId)
    ]).slice(0, 24);

    saveStoredSessions(nextStored);
    setSessionHistory(nextStored.map(toSessionSummary));
  }, [activeSessionId, historyHydrated, messages]);

  const sendQuery = async (query: string) => {
    if (!query.trim()) {
      return;
    }
    if (!answerConfigured || statusLevel === 'BLOCKED' || !plannerReady) {
      setSendError({
        message: plannerReady ? '当前推理模型未就绪，请先前往“模型设置”完成配置。' : plannerBlockMessage,
        code: plannerReady ? 'ANSWER_MODEL_NOT_READY' : 'PLANNER_SYSTEM_BLOCKED'
      });
      return;
    }

    const userMessage: ChatMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      content: query,
      mode,
      status: 'done'
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput('');
    setSendError(null);
    setIsSending(true);
    try {
      const endpoint = mode === 'local' ? '/api/jobs/planner' : '/api/jobs/chat';
      const result = await fetchAdminJson<JobCreateResponse>(resolveKernelApiUrl(endpoint), {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          sessionId: sessionIdRef.current,
          query,
          mode,
          configPath: defaultConfigPath,
          history: messages.slice(-8).map((item) => ({
            role: item.role,
            content: item.content
          }))
        })
      });
      if (!result.ok) {
        const failure = normalizeJobCreateFailure(result.data, result.message);
        setMessages((prev) => [
          ...prev,
          {
            id: crypto.randomUUID(),
            role: 'assistant',
            content: `请求失败：${failure.code} - ${failure.message}`,
            mode,
            status: 'error',
            sources: [],
            errorMeta: {
              code: failure.code,
              detail: failure.detail
            }
          }
        ]);
        setSendError({
          message: failure.message,
          code: failure.code,
          detail: failure.detail
        });
        setIsSending(false);
        return;
      }
      registerJob(result.data.job);
      setMessages((prev) => [
        ...prev,
        materializeJobBackedAssistantMessage(
          {
            id: crypto.randomUUID(),
            jobId: result.data.job.job_id,
            traceId: result.data.job.trace_id ?? undefined,
            role: 'assistant',
            content: '',
            mode,
            status: 'streaming',
            sources: []
          },
          result.data.job,
          []
        )
      ]);
      await refreshJob(result.data.job.job_id);
    } catch (error) {
      const message = error instanceof Error ? error.message : '创建后台任务失败';
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: 'assistant',
          content: `请求失败：JOB_CREATE_FAILED - ${message}`,
          mode,
          status: 'error',
          sources: [],
          errorMeta: { code: 'JOB_CREATE_FAILED', detail: message }
        }
      ]);
      setSendError({
        message,
        code: 'JOB_CREATE_FAILED',
        detail: message
      });
      setIsSending(false);
    }
  };

  const handleSend = () => {
    const query = input.trim();
    if (!query) {
      return;
    }
    setLastFailedQuery(query);
    void sendQuery(query);
  };

  const createNewSession = () => {
    const nextId = crypto.randomUUID();
    sessionIdRef.current = nextId;
    setActiveSessionId(nextId);
    setMessages([]);
    setExpandedGraphByMessage({});
    setSelectedCitation(null);
    setSendError(null);
    setLastFailedQuery('');
    setInput('');
    setHistoryHydrated(true);
  };

  const openSession = (sessionId: string) => {
    const stored = loadStoredMessages(sessionId);
    sessionIdRef.current = sessionId;
    setActiveSessionId(sessionId);
    setMessages(stored);
    setExpandedGraphByMessage({});
    setSelectedCitation(null);
    setSendError(null);
  };

  const deleteSession = (sessionId: string) => {
    const nextStored = sortSessionsByUpdatedAt(loadStoredSessions().filter((item) => item.id !== sessionId));
    saveStoredSessions(nextStored);
    setSessionHistory(nextStored.map(toSessionSummary));

    if (sessionId !== activeSessionId) {
      return;
    }

    const nextSession = nextStored[0];
    if (nextSession) {
      sessionIdRef.current = nextSession.id;
      setActiveSessionId(nextSession.id);
      setMessages(Array.isArray(nextSession.messages) ? nextSession.messages : []);
      setExpandedGraphByMessage({});
      setSelectedCitation(null);
      setSendError(null);
      setLastFailedQuery('');
      return;
    }

    createNewSession();
  };

  const historyGroups = useMemo(() => groupSessionsByTime(sessionHistory), [sessionHistory]);
  const hasMessages = messages.length > 0;
  const latestAssistantMessage = [...messages].reverse().find((item) => item.role === 'assistant');
  const activeStreamingMessage = [...messages].reverse().find((item) => {
    if (item.role !== 'assistant') {
      return false;
    }
    if (item.status === 'streaming') {
      return true;
    }
    if (!item.jobId) {
      return false;
    }
    const state = jobsById[item.jobId]?.state;
    return state === 'queued' || state === 'running';
  });
  const activeStreamingJob = activeStreamingMessage?.jobId ? jobsById[activeStreamingMessage.jobId] : undefined;
  const activeStreamingEvents = activeStreamingMessage?.jobId ? jobEventsById[activeStreamingMessage.jobId] ?? [] : [];
  const executionTimeline = useMemo(
    () => buildExecutionTimeline(activeStreamingJob, activeStreamingEvents, activeStreamingMessage?.mode ?? mode),
    [activeStreamingEvents, activeStreamingJob, activeStreamingMessage?.mode, mode]
  );
  const waitingStage = describeWaitingStage(executionTimeline.activeKey || activeStreamingJob?.progress_stage, activeStreamingMessage?.mode ?? mode, loadingBeat);
  const waitingMoment = waitingMoments[loadingBeat % waitingMoments.length];


  return (
    <section className="grid items-start gap-5 lg:grid-cols-[220px_minmax(0,1fr)]">
      <aside className="order-2 rounded-[28px] border border-white/70 bg-[linear-gradient(180deg,rgba(255,255,255,0.96),rgba(244,247,251,0.92))] p-3 shadow-[0_20px_80px_rgba(15,23,42,0.08)] backdrop-blur lg:order-1 lg:sticky lg:top-6">
        <div className="rounded-[24px] border border-slate-200/80 bg-[radial-gradient(circle_at_top_left,rgba(14,165,233,0.14),transparent_48%),linear-gradient(135deg,#fffdf8,#ffffff_46%,#f4f7fb)] p-4">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.28em] text-slate-500">会话历史</p>
              <h2 data-testid="chat-shell-title" className="mt-2 text-[24px] font-semibold tracking-tight text-slate-950">
                研究对话
              </h2>
            </div>
            <span
              className={`inline-flex items-center gap-2 rounded-full px-2.5 py-1 text-[11px] font-medium ${
                connection.connected ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-500'
              }`}
            >
              <span className={`h-2 w-2 rounded-full ${connection.connected ? 'bg-emerald-500' : 'bg-slate-400'}`} />
              {connection.connected ? '连接正常' : '连接中断'}
            </span>
          </div>
          <p className="mt-3 text-sm leading-6 text-slate-600">把问答沉淀成可回看的研究会话，方便继续追问、回溯与验证。</p>
          <button
            data-testid="chat-new-session-btn"
            type="button"
            onClick={createNewSession}
            className="mt-4 inline-flex w-full items-center justify-center gap-2 rounded-2xl bg-slate-950 px-4 py-3 text-sm font-medium text-white shadow-[0_16px_40px_rgba(15,23,42,0.22)] transition hover:-translate-y-0.5 hover:bg-slate-900"
          >
            <MessageSquarePlus className="h-4 w-4" />
            + 新建对话
          </button>
        </div>

        <div className="mt-4 grid grid-cols-3 gap-2">
          {modeOptions.map((item) => {
            const Icon = item.icon;
            const active = mode === item.key;
            return (
              <button
                key={item.key}
                type="button"
                onClick={() => setMode(item.key)}
                className={`rounded-2xl border px-3 py-2 text-left transition ${
                  active
                    ? 'border-sky-200 bg-sky-50 text-sky-800 shadow-[0_12px_32px_rgba(56,189,248,0.14)]'
                    : 'border-slate-200 bg-white/80 text-slate-600 hover:border-slate-300'
                }`}
              >
                <Icon className="h-4 w-4" />
                <p className="mt-2 text-xs font-semibold">{item.label}</p>
                <p className="mt-1 text-[10px] leading-4 opacity-80">{item.hint}</p>
              </button>
            );
          })}
        </div>

        <div className="mt-4 rounded-[24px] border border-slate-200 bg-white/85 p-3">
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">
            <History className="h-3.5 w-3.5" />
            历史会话
          </div>
          <div data-testid="chat-history-groups" className="mt-3 max-h-[46vh] space-y-4 overflow-y-auto pr-1">
            {historyGroups.map((group) => (
              <div key={group.label}>
                <p className="mb-2 text-[11px] font-semibold text-slate-400">{group.label}</p>
                <div className="space-y-2">
                  {group.items.map((session) => {
                    const active = session.id === activeSessionId;
                    return (
                      <div
                        key={session.id}
                        className={`w-full rounded-2xl border px-3 py-3 text-left transition ${
                          active
                            ? 'border-slate-900 bg-slate-950 text-white shadow-[0_18px_38px_rgba(15,23,42,0.24)]'
                            : 'border-slate-200 bg-slate-50/80 text-slate-700 hover:bg-white'
                        }`}
                      >
                        <div className="flex items-start justify-between gap-2">
                          <button type="button" onClick={() => openSession(session.id)} className="min-w-0 flex-1 text-left">
                            <div className="flex items-center justify-between gap-3">
                              <p className="line-clamp-1 text-sm font-medium">{session.title}</p>
                              <ChevronRight className={`h-4 w-4 shrink-0 ${active ? 'text-slate-300' : 'text-slate-400'}`} />
                            </div>
                            <p className={`mt-1 line-clamp-2 text-xs leading-5 ${active ? 'text-slate-300' : 'text-slate-500'}`}>
                              {session.preview || '等待第一条提问'}
                            </p>
                            <p className="mt-2 text-[11px] text-slate-400">
                              {formatRelativeTime(session.updatedAt)} · {session.messageCount} 条消息
                            </p>
                          </button>
                          <button
                            type="button"
                            data-testid={`chat-delete-session-${session.id}`}
                            aria-label={`删除${session.title}`}
                            onClick={() => deleteSession(session.id)}
                            className={`inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-xl border transition ${
                              active
                                ? 'border-white/15 bg-white/10 text-slate-200 hover:bg-white/15'
                                : 'border-slate-200 bg-white text-slate-400 hover:border-rose-200 hover:bg-rose-50 hover:text-rose-600'
                            }`}
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            ))}
            {!sessionHistory.length ? (
              <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-3 py-4 text-xs leading-5 text-slate-500">
                还没有历史对话。你发出的第一条问题会自动出现在这里。
              </div>
            ) : null}
          </div>
        </div>
      </aside>

      <div className="order-1 rounded-[34px] border border-white/70 bg-[linear-gradient(180deg,rgba(255,255,255,0.96),rgba(246,248,252,0.92))] p-4 shadow-[0_24px_80px_rgba(15,23,42,0.08)] backdrop-blur md:p-5 2xl:order-2">
        <header className="rounded-[26px] border border-slate-200 bg-[radial-gradient(circle_at_top_left,rgba(14,165,233,0.12),transparent_38%),linear-gradient(135deg,#fffdf9,#ffffff_46%,#f3f8ff)] p-4 md:p-5">
          <div className="flex flex-col gap-4">
            <div className="flex flex-col gap-3 xl:flex-row xl:items-start xl:justify-between">
              <div className="max-w-3xl">
                <p className="text-[11px] font-semibold uppercase tracking-[0.28em] text-slate-500">研究问答工作区</p>
                <h3 className="mt-2 text-[24px] font-semibold tracking-tight text-slate-950 md:text-[28px]">带历史记录的知识问答工作区</h3>
                <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">
                  把提问、引用和依据放在同一个页面里，首屏先服务于发问、看回答和继续追问。
                </p>
              </div>
              <div className="flex flex-wrap gap-2 xl:max-w-[420px] xl:justify-end">
                <div className={`min-w-[180px] rounded-2xl border px-4 py-3 text-sm ${runtimeView.tone}`}>
                  <p className="text-[11px] font-semibold uppercase tracking-[0.2em]">当前状态</p>
                  <p className="mt-1 font-medium">
                    {runtimeView.icon} {runtimeView.label}
                  </p>
                  <p className="mt-1 text-xs">{runtimeOverview?.status.reasons?.[0] || '运行正常，可直接发起问答。'}</p>
                </div>
                <div className="min-w-[220px] max-w-full rounded-2xl border border-slate-200 bg-white/80 px-4 py-3 text-sm text-slate-700 xl:min-w-[260px]">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-slate-500">当前使用模型</p>
                  <p className="mt-1 break-all">推理：{runtimeOverview?.llm.answer.model || '未配置'}</p>
                  <p className="mt-1 break-all">重排：{runtimeOverview?.llm.rerank.model || '未配置'}</p>
                  <p className="mt-1 break-all">改写：{runtimeOverview?.llm.rewrite.model || '未配置'}</p>
                </div>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              {viewModeOptions.map((item) => (
                <button
                  key={item.key}
                  type="button"
                  onClick={() => setViewMode(item.key)}
                  className={`rounded-full border px-3 py-1.5 text-xs font-medium transition ${
                    viewMode === item.key ? 'border-slate-900 bg-slate-900 text-white' : 'border-slate-200 bg-white text-slate-600'
                  }`}
                >
                  {item.label}
                </button>
              ))}
              <span className="rounded-full border border-slate-200 bg-white/90 px-3 py-1.5 text-xs text-slate-600">左侧会自动保存历史，这里专心提问就行。</span>
              {runtimeOverviewError ? <span className="text-xs text-rose-600">{runtimeOverviewError}</span> : null}
            </div>
          </div>

          {!answerConfigured || statusLevel === 'BLOCKED' || !plannerReady ? (
            <div className="mt-4 rounded-2xl border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900">
              {plannerReady ? '当前推理模型不可用。请先前往' : `${plannerBlockMessage} 请先前往`}
              <Link href="/settings" className="mx-1 font-semibold underline underline-offset-2">
                模型设置
              </Link>
              完成配置后再开始问答。
            </div>
          ) : null}
        </header>

        <div className="mt-5 grid gap-4">
          <div className="rounded-[28px] border border-slate-200 bg-white/80 p-3 shadow-[0_12px_36px_rgba(15,23,42,0.05)]">
            <div className="mb-3 flex items-center justify-between gap-3 px-2">
              <div>
                <p className="text-sm font-semibold text-slate-900">{buildSessionSummary(activeSessionId || sessionIdRef.current, messages).title}</p>
                <p className="mt-1 text-xs text-slate-500">
                  这是一段可持续追问的对话，左侧会自动保存历史。
                </p>
              </div>
              <span className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-[11px] text-slate-500">
                {messages.length} 条消息
              </span>
            </div>

            <div
              className={`overflow-y-auto rounded-[24px] bg-[linear-gradient(180deg,#f7fbff_0%,#ffffff_20%,#f8fafc_100%)] p-3 ${
                hasMessages ? 'h-[66vh] md:h-[70vh]' : 'h-[62vh] md:h-[68vh]'
              }`}
            >
              {!hasMessages ? (
                <div className="flex h-full min-h-[320px] flex-col items-center justify-center rounded-[24px] border border-dashed border-slate-200 bg-white/80 px-5 py-6 text-center">
                  <div className="rounded-full bg-sky-50 p-3 text-sky-700">
                    <Sparkles className="h-5 w-5" />
                  </div>
                  <p className="mt-4 text-xs font-semibold uppercase tracking-[0.28em] text-slate-400">对话问答</p>
                  <h3 className="mt-3 text-2xl font-semibold tracking-tight text-slate-950 md:text-[34px]">向你的研究知识库提问</h3>
                  <p className="mt-3 max-w-xl text-sm leading-6 text-slate-600">
                    系统会尽量给出中文解释、证据来源和关键对比，适合非技术用户直接阅读。
                  </p>
                  <div className="mt-5 grid w-full max-w-3xl gap-2 md:grid-cols-2">
                    {promptSuggestions.map((item) => (
                      <button
                        key={item}
                        type="button"
                        onClick={() => void sendQuery(item)}
                        className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-left text-sm text-slate-700 transition hover:border-sky-300 hover:bg-sky-50"
                      >
                        {item}
                      </button>
                    ))}
                  </div>
                </div>
              ) : (
                <div className="space-y-3">
                  {messages.map((message) => {
                    const graph = buildGraphSubgraph(message.sources ?? []);
                    const showGraphPanel =
                      (message.sources ?? []).some((source) => source.source_type === 'graph') || viewMode === 'developer';

                    return (
                      <article
                        key={message.id}
                        className={`max-w-[92%] rounded-[24px] border px-4 py-4 shadow-sm ${
                          message.role === 'user'
                            ? 'ml-auto border-sky-100 bg-[linear-gradient(135deg,#dff4ff,#eef9ff)] text-slate-900'
                            : 'border-white bg-white text-slate-900'
                        }`}
                      >
                        <div className="mb-3 flex items-center gap-2 text-[11px] uppercase tracking-[0.18em] text-slate-400">
                          <span className="inline-flex items-center gap-1">
                            {message.role === 'user' ? <History className="h-3.5 w-3.5" /> : <Bot className="h-3.5 w-3.5" />}
                            {message.role === 'user' ? '你' : '研究助手'}
                          </span>
                          {message.mode ? <span>{modeOptions.find((item) => item.key === message.mode)?.label || message.mode}</span> : null}
                          {message.status === 'streaming' ? <span>整理回答中</span> : null}
                        </div>

                        <div className="prose prose-sm max-w-none prose-headings:text-slate-900 prose-p:text-slate-700 prose-pre:bg-slate-950 prose-pre:text-slate-100 prose-code:text-slate-900">
                          {message.status === 'streaming' && !message.content.trim() ? (
                            <StreamingPlaceholder stage={waitingStage} moment={waitingMoment} timeline={executionTimeline.steps} />
                          ) : (
                            <StructuredAnswer content={message.content} />
                          )}
                        </div>

                        {viewMode === 'developer' && message.role === 'assistant' && message.errorMeta ? (
                          <div className="mt-4 rounded-[20px] border border-rose-200 bg-rose-50/90 p-3 text-xs text-rose-900">
                            <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-rose-700">
                              <Bot className="h-3.5 w-3.5" />
                              错误详情
                            </div>
                            <p className="mt-2 font-mono leading-5">
                              code={message.errorMeta.code || '-'}
                              {message.errorMeta.detail ? ` · detail=${message.errorMeta.detail}` : ''}
                            </p>
                          </div>
                        ) : null}

                        {viewMode === 'developer' && message.role === 'assistant' && (message.jobId || message.traceId) ? (
                          <div className="mt-4 rounded-[20px] border border-slate-200 bg-slate-50/90 p-3 text-xs text-slate-800">
                            <div className="mb-2 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">
                              <Bot className="h-3.5 w-3.5" />
                              模型上下文与回复
                            </div>
                            {llmDebugByTrace[buildLlmDebugKey(message)]?.loading ? (
                              <p className="text-xs text-slate-500">正在加载模型调试记录…</p>
                            ) : llmDebugByTrace[buildLlmDebugKey(message)]?.error ? (
                              <p className="text-xs text-slate-500">{llmDebugByTrace[buildLlmDebugKey(message)]?.error}</p>
                            ) : (llmDebugByTrace[buildLlmDebugKey(message)]?.records.length ?? 0) > 0 ? (
                              <div className="space-y-3">
                                {llmDebugByTrace[buildLlmDebugKey(message)]?.records.map((record, index) => (
                                  <details
                                    key={`${message.id}-llm-${index}`}
                                    className="rounded-2xl border border-slate-200 bg-white px-3 py-2"
                                  >
                                    <summary className="cursor-pointer list-none font-medium text-slate-700">
                                      {record.debug_stage || record.stage || 'llm'} · {record.provider || '-'} / {record.model || '-'}
                                      {record.elapsed_ms ? ` · ${record.elapsed_ms}ms` : ''}
                                    </summary>
                            <div className="mt-3 space-y-3">
                              <p className="font-mono text-[11px] text-slate-500">
                                        event={record.event} · route={record.route_id || '-'} · api_base={record.api_base || '-'} · endpoint={record.endpoint || '-'} · transport={record.transport || '-'}
                                      </p>
                                      <DebugBlock title="System Prompt" content={record.system_prompt} />
                                      <DebugBlock title="User Prompt" content={record.user_prompt} />
                                      <DebugBlock title="Request Payload" content={record.request_payload} />
                                      <DebugBlock title="Raw Response Payload" content={record.response_payload} />
                                      <DebugBlock title="Model Response" content={record.response_text} />
                                      {(record.reason || record.status_code || record.error_category) ? (
                                        <p className="font-mono text-[11px] text-rose-700">
                                          reason={record.reason || '-'} · status={record.status_code ?? '-'} · category={record.error_category || '-'}
                                        </p>
                                      ) : null}
                                    </div>
                                  </details>
                                ))}
                              </div>
                            ) : (
                              <p className="text-xs text-slate-500">暂无模型调试记录。</p>
                            )}
                          </div>
                        ) : null}

                        {viewMode === 'developer' && message.role === 'assistant' && (message.agentEvents?.length ?? 0) > 0 ? (
                          <div className="mt-4 rounded-[20px] border border-slate-200 bg-slate-50/90 p-3" data-testid={`agent-events-${message.id}`}>
                            <div className="mb-2 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">
                              <Bot className="h-3.5 w-3.5" />
                              Agent 事件
                            </div>
                            <div className="space-y-2">
                              {message.agentEvents?.map((agentEvent, index) => (
                                <div
                                  key={`${message.id}-agent-${index}`}
                                  className={`rounded-2xl border px-3 py-2 text-xs ${
                                    agentEvent.type === 'fallback' || agentEvent.type === 'serviceBlocked'
                                      ? 'border-amber-200 bg-amber-50 text-amber-900'
                                      : agentEvent.type === 'planning'
                                        ? 'border-sky-200 bg-sky-50 text-sky-900'
                                        : 'border-slate-200 bg-white text-slate-700'
                                  }`}
                                >
                                  <p className="font-medium">{formatAgentEventTitle(agentEvent)}</p>
                                  <p className="mt-1 leading-5">{formatAgentEventDetail(agentEvent)}</p>
                                </div>
                              ))}
                            </div>
                          </div>
                        ) : null}

                        {message.sources && message.sources.length > 0 ? (
                          <div className="mt-4 rounded-[20px] border border-slate-200 bg-slate-50/80 p-3">
                            <div className="mb-2 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">
                              <SearchCheck className="h-3.5 w-3.5" />
                              证据来源
                            </div>
                            <div className="space-y-2">
                              {message.sources.map((source, index) => {
                                const isSelected = selectedCitation === index + 1;
                                return (
                                  <button
                                    key={`${message.id}-${source.source_id}`}
                                    type="button"
                                    onClick={() => setSelectedCitation(index + 1)}
                                    className={`w-full rounded-2xl border px-3 py-3 text-left text-xs transition ${
                                      isSelected ? 'border-sky-300 bg-sky-50' : 'border-slate-200 bg-white'
                                    }`}
                                  >
                                    <p className="font-medium text-slate-800">
                                      [{index + 1}] {source.title}
                                    </p>
                                    <p className="mt-1 text-slate-600">{source.snippet}</p>
                                    <p className="mt-2 text-[10px] uppercase tracking-[0.12em] text-slate-400">
                                      {toSourceLabel(source.source_type)} · {source.locator} · 相关度 {source.score.toFixed(3)}
                                    </p>
                                  </button>
                                );
                              })}
                            </div>
                          </div>
                        ) : null}

                        {showGraphPanel ? (
                          <GraphSubgraphPanel
                            graph={graph}
                            selectedCitation={selectedCitation}
                            expanded={Boolean(expandedGraphByMessage[message.id])}
                            onToggleExpanded={() =>
                              setExpandedGraphByMessage((prev) => ({ ...prev, [message.id]: !prev[message.id] }))
                            }
                            onSelectCitation={(citationIndex) => setSelectedCitation(citationIndex)}
                            showMetadata={viewMode === 'developer'}
                          />
                        ) : null}
                      </article>
                    );
                  })}
                  {isSending ? (
                    <div
                      data-testid="chat-streaming-stage-card"
                      className="overflow-hidden rounded-[26px] border border-sky-200 bg-[linear-gradient(135deg,rgba(239,246,255,0.96),rgba(255,255,255,0.98)_52%,rgba(236,253,245,0.96))] p-5 shadow-[0_18px_40px_rgba(56,189,248,0.14)]"
                    >
                      <div className="flex flex-col gap-5">
                        {/* 顶部：当前状态 + 转圈动画 */}
                        <div className="flex items-start gap-4">
                          <div className="thinking-orbit shrink-0">
                            <span className="thinking-orbit-dot thinking-orbit-dot-a" />
                            <span className="thinking-orbit-dot thinking-orbit-dot-b" />
                            <span className="thinking-orbit-dot thinking-orbit-dot-c" />
                          </div>
                          <div className="flex-1">
                            <div className="inline-flex items-center gap-2 rounded-full border border-sky-200 bg-white/90 px-3 py-1 text-[11px] font-semibold tracking-normal text-sky-700">
                              <Clock3 className="h-3.5 w-3.5" />
                              {waitingStage.badge}
                            </div>
                            <h4 className="mt-3 text-lg font-semibold text-slate-950">{waitingStage.title}</h4>
                            <p className="mt-2 max-w-xl text-sm leading-6 text-slate-600">{waitingStage.detail}</p>
                          </div>
                        </div>
                        
                        {/* 中间：竖向排列的所有阶段 */}
                        <div className="pl-4">
                          <ExecutionTimelineVertical steps={executionTimeline.steps} />
                        </div>
                        
                        {/* 底部：文字Tips */}
                        <div className="rounded-[22px] border border-white/80 bg-white/80 px-4 py-3 text-sm text-slate-700 shadow-sm">
                          <p className="text-[11px] font-semibold text-slate-500 tracking-normal">💡 等待时可以做什么</p>
                          <p className="mt-2 text-sm leading-[1.6] whitespace-normal break-words">{waitingMoment}</p>
                        </div>
                      </div>
                    </div>
                  ) : null}
                  <div ref={messageBottomRef} />
                </div>
              )}
            </div>

            <footer className="mt-3 rounded-[24px] border border-slate-200 bg-white p-3">
              <label className="mb-2 block text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">输入问题</label>
              <div className="flex gap-2">
                <input
                  value={input}
                  onChange={(event) => setInput(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter') {
                      handleSend();
                    }
                  }}
                  placeholder="例如：比较这两篇论文的方法差异，并用中文解释各自优缺点。"
                  className="h-12 w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 text-sm outline-none ring-sky-300 transition focus:bg-white focus:ring-2"
                />
                <button
                  type="button"
                  onClick={handleSend}
                  disabled={!canSend || isSending}
                  className="h-12 rounded-2xl bg-slate-950 px-5 text-sm font-medium text-white shadow-[0_14px_30px_rgba(15,23,42,0.2)] disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {isSending ? '回答整理中...' : '发送'}
                </button>
              </div>
              {sendError ? (
                <div className="mt-2 rounded-2xl border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">
                  <p>{sendError.message}</p>
                  {viewMode === 'developer' && (sendError.code || sendError.detail) ? (
                    <p className="mt-1 font-mono text-[11px] text-rose-900/80">
                      {sendError.code ? `code=${sendError.code}` : 'code=-'}
                      {sendError.detail ? ` · detail=${sendError.detail}` : ''}
                    </p>
                  ) : null}
                </div>
              ) : null}
              {sendError && lastFailedQuery ? (
                <button
                  type="button"
                  onClick={() => void sendQuery(lastFailedQuery)}
                  className="mt-2 text-xs font-medium text-sky-700 underline underline-offset-2"
                >
                  重试上一条问题
                </button>
              ) : null}
            </footer>
          </div>


        </div>
      </div>
    </section>
  );
}

function buildLlmDebugKey(message: Pick<ChatMessage, 'jobId' | 'traceId'>): string {
  if (message.jobId) {
    return `job:${message.jobId}`;
  }
  if (message.traceId) {
    return `trace:${message.traceId}`;
  }
  return '';
}

function describeWaitingStage(progressStage: string | null | undefined, mode: ChatMode, beat: number) {
  const normalized = (progressStage || '').toLowerCase();
  if (normalized.includes('queue')) {
    return {
      badge: '排队中',
      title: '问题已经送出，正在排队接单',
      detail: '系统刚收到你的问题，正在为它安排这一轮检索和回答流程。'
    };
  }
  if (normalized.includes('plan')) {
    return {
      badge: '拆解问题',
      title: '先想清楚这题该怎么答',
      detail: '助手在判断要不要先澄清、先检索，还是直接进入回答。'
    };
  }
  if (normalized.includes('retriev') || normalized.includes('search') || normalized.includes('recall')) {
    return {
      badge: '找资料',
      title: '正在翻找最相关的材料',
      detail: '会先把最可能有帮助的片段拉出来，再决定哪些值得放进最终答案。'
    };
  }
  if (normalized.includes('rerank') || normalized.includes('rank')) {
    return {
      badge: '筛选中',
      title: '已经找到一批材料，正在挑重点',
      detail: '系统会把更贴近问题的内容往前放，减少把无关信息塞进回答里。'
    };
  }
  if (normalized.includes('answer') || normalized.includes('draft') || normalized.includes('write') || normalized.includes('stream')) {
    return {
      badge: '整理回答',
      title: '证据差不多齐了，开始组织表达',
      detail: '现在主要是在把材料串成更容易读的回答，并尽量保留出处线索。'
    };
  }

  const fallbackByMode: Record<ChatMode, Array<{ badge: string; title: string; detail: string }>> = {
    local: [
      { badge: '读资料', title: '正在已导入资料里找答案', detail: '这轮会优先依赖你已经导入的内容，不会把重点丢给外部网页。' },
      { badge: '整理回答', title: '把资料内容翻成更好读的中文', detail: '系统会尽量把术语拆开说，并把结论和依据放在一起。' }
    ],
    web: [
      { badge: '补充信息', title: '正在网上补充公开信息', detail: '会先看公开网页里是否有更及时的补充，再整理回中文答案。' },
      { badge: '整理回答', title: '把网页信息重新收束成结论', detail: '目标不是堆链接，而是把要点压缩成能直接看的说明。' }
    ],
    hybrid: [
      { badge: '双路比对', title: '正在对比资料内信息和公开信息', detail: '会尽量保留两边一致的部分，把冲突点单独拎出来。' },
      { badge: '整理回答', title: '把两路信息合成一份回答', detail: '现在主要是在压缩重复信息，留下更值得你继续追问的部分。' }
    ]
  };
  return fallbackByMode[mode][beat % fallbackByMode[mode].length];
}

function normalizeExecutionStageKey(value: string | null | undefined): string {
  const normalized = (value || '').trim().toLowerCase();
  if (!normalized) return '';
  if (normalized.includes('queue')) return 'queued';
  if (normalized.includes('plan')) return 'planner';
  if (normalized.includes('rewrite')) return 'rewrite';
  if (normalized.includes('embed')) return 'embedding';
  if (normalized.includes('retriev') || normalized.includes('search') || normalized.includes('recall')) return 'retrieval';
  if (normalized.includes('rerank') || normalized.includes('rank')) return 'rerank';
  if (normalized.includes('graph')) return 'graph_entity';
  if (normalized.includes('suff')) return 'sufficiency_judge';
  if (normalized.includes('answer') || normalized.includes('draft') || normalized.includes('write') || normalized.includes('stream')) return 'answer';
  if (normalized.includes('complete') || normalized.includes('success')) return 'completed';
  if (normalized.includes('cancel')) return 'cancelled';
  if (normalized.includes('fail') || normalized.includes('error')) return 'failed';
  if (normalized === 'running') return 'running';
  return normalized;
}

function stageDefinition(stageKey: string, mode: ChatMode): { label: string; description: string } {
  const base: Record<string, { label: string; description: string }> = {
    queued: { label: '排队', description: '请求已经进入后台队列，等待当前轮次的执行资源。' },
    planner: { label: 'Planner', description: '先判断问题路径，决定是直接回答、先检索，还是需要改写与多步工具链。' },
    rewrite: { label: 'Rewrite', description: '把原问题压缩成更适合检索和比对的表达，减少召回漂移。' },
    embedding: { label: 'Embedding', description: '把问题或片段转成向量，准备做语义匹配。' },
    retrieval: { label: 'Retrieval', description: '从知识库里拉出最相关的候选材料，准备进入后续筛选。' },
    rerank: { label: 'Reranker', description: '对召回结果再排序，把更贴题的内容推到前面。' },
    graph_entity: { label: 'Graph Entity', description: '抽取实体或图谱线索，补强跨段落与跨文档连接。' },
    sufficiency_judge: { label: 'Judge', description: '检查当前证据是否够支撑结论，避免过早给出看似完整的答案。' },
    answer: { label: 'Answer', description: '把证据与结论串成可读回答，并尽量保留出处。' },
    completed: { label: '完成', description: '回答已经生成完毕，引用与最终文本都已落到结果里。' },
    cancelled: { label: '已取消', description: '本轮任务已被取消，不会继续推进后续模型阶段。' },
    failed: { label: '失败', description: '后台在当前阶段中断，需查看错误详情或重新发起。' },
    running: {
      label: mode === 'web' ? '处理中' : '执行中',
      description: mode === 'web' ? '后台正在处理这轮联网问答。' : '后台正在推进这轮知识库问答。',
    },
  };
  return base[stageKey] ?? { label: stageKey, description: '后台正在执行这一阶段。' };
}

function buildExecutionTimeline(job: JobStatus | undefined, events: JobEvent[], mode: ChatMode): { activeKey: string; steps: ExecutionTimelineStep[] } {
  const ordered: Array<{ key: string; meta?: string }> = [];
  const seen = new Set<string>();

  const pushStage = (key: string, meta?: string) => {
    const normalizedKey = normalizeExecutionStageKey(key);
    if (!normalizedKey || seen.has(normalizedKey)) {
      return;
    }
    seen.add(normalizedKey);
    ordered.push({ key: normalizedKey, meta });
  };

  if (job?.state === 'queued' || events.some((event) => event.event_type === 'state_changed' && String(event.payload?.state || '') === 'queued')) {
    pushStage('queued');
  }

  for (const event of events) {
    const payload = (event.payload ?? {}) as Record<string, unknown>;
    const payloadType = typeof payload.type === 'string' ? payload.type : '';
    if (payloadType === 'planning') {
      pushStage('planner');
      continue;
    }
    if (payloadType === 'llmStage') {
      const metaParts = [typeof payload.provider === 'string' ? payload.provider : '', typeof payload.model === 'string' ? payload.model : ''].filter(Boolean);
      pushStage(typeof payload.stage === 'string' ? payload.stage : '', metaParts.join(' / ') || undefined);
      continue;
    }
  }

  const currentKey = normalizeExecutionStageKey(job?.state === 'running' ? job?.progress_stage : job?.state);
  if (job?.state === 'running') {
    pushStage(currentKey || 'running');
  } else if (job?.state === 'succeeded') {
    pushStage('completed');
  } else if (job?.state === 'failed') {
    pushStage('failed');
  } else if (job?.state === 'cancelled') {
    pushStage('cancelled');
  }

  const activeKey =
    job?.state === 'running'
      ? currentKey || ordered[ordered.length - 1]?.key || 'running'
      : job?.state === 'succeeded'
        ? 'completed'
        : job?.state === 'failed'
          ? 'failed'
          : job?.state === 'cancelled'
            ? 'cancelled'
            : ordered[ordered.length - 1]?.key || 'queued';

  const activeIndex = ordered.findIndex((item) => item.key === activeKey);
  const steps = ordered.map((item, index) => {
    const definition = stageDefinition(item.key, mode);
    let status: ExecutionTimelineStep['status'] = 'pending';
    if (activeIndex === -1) {
      status = index === ordered.length - 1 ? 'active' : 'done';
    } else if (index < activeIndex) {
      status = 'done';
    } else if (index === activeIndex) {
      status = 'active';
    }
    if (job?.state === 'succeeded') {
      status = 'done';
    }
    return {
      key: item.key,
      label: definition.label,
      description: definition.description,
      status,
      meta: item.meta,
    };
  });

  return { activeKey, steps };
}

function ExecutionTimeline({ steps }: { steps: ExecutionTimelineStep[] }) {
  if (!steps.length) {
    return null;
  }
  return (
    <div className="w-full">
      {/* 水平进度条 - 在宽屏幕上显示 */}
      <div className="hidden md:block">
        <div className="flex items-center gap-2 overflow-x-auto pb-2 scrollbar-thin">
          {steps.map((step, index) => (
            <div key={`${step.key}-${index}`} className="flex items-center shrink-0">
              <div
                className={`flex-1 rounded-2xl border px-3 py-2.5 transition ${
                  step.status === 'active'
                    ? 'border-sky-300 bg-sky-50/90 shadow-[0_8px_20px_rgba(56,189,248,0.12)]'
                    : step.status === 'done'
                      ? 'border-emerald-200 bg-emerald-50/70'
                      : 'border-slate-200 bg-white/75'
                }`}
              >
                <div className="flex items-center gap-2">
                  <span
                    className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] font-semibold ${
                      step.status === 'active'
                        ? 'bg-sky-600 text-white'
                        : step.status === 'done'
                          ? 'bg-emerald-600 text-white'
                          : 'bg-slate-200 text-slate-600'
                    }`}
                  >
                    {index + 1}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5">
                      <p className="text-xs font-semibold text-slate-900 truncate">{step.label}</p>
                      <span
                        className={`shrink-0 rounded-full px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-[0.12em] ${
                          step.status === 'active'
                            ? 'bg-sky-100 text-sky-700'
                            : step.status === 'done'
                              ? 'bg-emerald-100 text-emerald-700'
                              : 'bg-slate-100 text-slate-500'
                        }`}
                      >
                        {step.status === 'active' ? '当前' : step.status === 'done' ? '完成' : '待办'}
                      </span>
                    </div>
                    {step.meta ? (
                      <p className="truncate text-[10px] text-slate-500">{step.meta}</p>
                    ) : (
                      <p className="truncate text-[10px] text-slate-600">{step.description}</p>
                    )}
                  </div>
                </div>
              </div>
              {index < steps.length - 1 && (
                <span
                  className={`mx-1.5 h-0.5 w-4 shrink-0 rounded-full ${
                    step.status === 'done' ? 'bg-emerald-400' : 'bg-slate-200'
                  }`}
                />
              )}
            </div>
          ))}
        </div>
      </div>

      {/* 垂直进度条 - 在窄屏幕上显示 */}
      <div className="md:hidden grid gap-2">
        {steps.map((step, index) => (
          <div
            key={`${step.key}-mobile-${index}`}
            className={`grid grid-cols-[28px_minmax(0,1fr)] gap-3 rounded-[20px] border px-3 py-3 transition ${
              step.status === 'active'
                ? 'border-sky-300 bg-sky-50/90 shadow-[0_12px_28px_rgba(56,189,248,0.12)]'
                : step.status === 'done'
                  ? 'border-emerald-200 bg-emerald-50/70'
                  : 'border-slate-200 bg-white/75'
            }`}
          >
            <div className="flex flex-col items-center">
              <span
                className={`mt-0.5 flex h-7 w-7 items-center justify-center rounded-full text-[11px] font-semibold ${
                  step.status === 'active'
                    ? 'bg-sky-600 text-white'
                    : step.status === 'done'
                      ? 'bg-emerald-600 text-white'
                      : 'bg-slate-200 text-slate-600'
                }`}
              >
                {index + 1}
              </span>
              {index < steps.length - 1 ? (
                <span
                  className={`mt-1 w-px flex-1 ${
                    step.status === 'done' ? 'bg-emerald-300' : step.status === 'active' ? 'bg-sky-300' : 'bg-slate-200'
                  }`}
                />
              ) : null}
            </div>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <p className="text-sm font-semibold text-slate-900">{step.label}</p>
                <span
                  className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.16em] ${
                    step.status === 'active'
                      ? 'bg-sky-100 text-sky-700'
                      : step.status === 'done'
                        ? 'bg-emerald-100 text-emerald-700'
                        : 'bg-slate-100 text-slate-500'
                  }`}
                >
                  {step.status === 'active' ? '当前' : step.status === 'done' ? '已完成' : '待推进'}
                </span>
                {step.meta ? <span className="truncate text-[11px] text-slate-500">{step.meta}</span> : null}
              </div>
              <p className="mt-1 text-xs leading-5 text-slate-600">{step.description}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// 竖向排列的阶段时间线组件
function ExecutionTimelineVertical({ steps }: { steps: ExecutionTimelineStep[] }) {
  if (!steps.length) {
    return null;
  }
  return (
    <div className="w-full">
      <div className="grid gap-3">
        {steps.map((step, index) => (
          <div
            key={`${step.key}-vertical-${index}`}
            className={`grid grid-cols-[36px_minmax(0,1fr)] gap-3 rounded-[16px] border px-3 py-3 transition ${
              step.status === 'active'
                ? 'border-sky-300 bg-sky-50/90 shadow-[0_8px_20px_rgba(56,189,248,0.12)]'
                : step.status === 'done'
                  ? 'border-emerald-200 bg-emerald-50/70'
                  : 'border-slate-200 bg-white/75'
            }`}
          >
            <div className="flex flex-col items-center">
              <span
                className={`mt-0.5 flex h-8 w-8 items-center justify-center rounded-full text-[12px] font-semibold ${
                  step.status === 'active'
                    ? 'bg-sky-600 text-white'
                    : step.status === 'done'
                      ? 'bg-emerald-600 text-white'
                      : 'bg-slate-200 text-slate-600'
                }`}
              >
                {index + 1}
              </span>
              {index < steps.length - 1 ? (
                <span
                  className={`mt-1.5 w-px flex-1 min-h-[20px] ${
                    step.status === 'done' ? 'bg-emerald-300' : step.status === 'active' ? 'bg-sky-300' : 'bg-slate-200'
                  }`}
                />
              ) : null}
            </div>
            <div className="min-w-0 py-0.5">
              <div className="flex flex-wrap items-center gap-2">
                <p className="text-sm font-semibold text-slate-900">{step.label}</p>
                <span
                  className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                    step.status === 'active'
                      ? 'bg-sky-100 text-sky-700'
                      : step.status === 'done'
                        ? 'bg-emerald-100 text-emerald-700'
                        : 'bg-slate-100 text-slate-500'
                  }`}
                >
                  {step.status === 'active' ? '当前' : step.status === 'done' ? '已完成' : '待推进'}
                </span>
                {step.meta ? <span className="truncate text-[11px] text-slate-500">{step.meta}</span> : null}
              </div>
              <p className="mt-1 text-xs leading-5 text-slate-600">{step.description}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function StreamingPlaceholder({
  stage,
  moment,
  timeline
}: {
  stage: { badge: string; title: string; detail: string };
  moment: string;
  timeline: ExecutionTimelineStep[];
}) {
  return (
    <div className="not-prose rounded-[22px] border border-sky-100 bg-[linear-gradient(135deg,#f8fbff,#ffffff_50%,#f0fdf4)] p-4">
      <div className="flex items-start gap-3">
        <div className="thinking-orbit thinking-orbit-compact shrink-0">
          <span className="thinking-orbit-dot thinking-orbit-dot-a" />
          <span className="thinking-orbit-dot thinking-orbit-dot-b" />
          <span className="thinking-orbit-dot thinking-orbit-dot-c" />
        </div>
        <div className="min-w-0">
          <div className="inline-flex items-center gap-2 rounded-full border border-sky-200 bg-white/95 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-sky-700">
            <Clock3 className="h-3.5 w-3.5" />
            {stage.badge}
          </div>
          <p className="mt-3 text-sm font-semibold text-slate-900">{stage.title}</p>
          <p className="mt-1 text-sm leading-6 text-slate-600">{stage.detail}</p>
          <div className="mt-3">
            <ExecutionTimeline steps={timeline} />
          </div>
          <p className="mt-3 rounded-2xl bg-white/80 px-3 py-2 text-xs leading-5 text-slate-500">{moment}</p>
        </div>
      </div>
    </div>
  );
}

function materializeJobBackedAssistantMessage(message: ChatMessage, job: JobStatus | undefined, events: JobEvent[]): ChatMessage {
  const messagePieces: string[] = [];
  let nextSources = message.sources ?? [];
  let nextRunId = message.runId;
  let nextTraceId = message.traceId;
  let nextMode = message.mode;
  let nextErrorMeta = message.errorMeta;
  const nextAgentEvents: AgentEvent[] = [];

  for (const event of events) {
    const payload = event.payload ?? {};
    if (event.event_type === 'message' && typeof payload.content === 'string') {
      messagePieces.push(payload.content);
    }
    if (event.event_type === 'sources' && Array.isArray(payload.sources)) {
      nextSources = payload.sources as SourceItem[];
      if (typeof payload.runId === 'string' && payload.runId) {
        nextRunId = payload.runId;
      }
    }
    if (event.event_type === 'messageEnd' && typeof payload.runId === 'string' && payload.runId) {
      nextRunId = payload.runId;
    }
    if (typeof payload.traceId === 'string' && payload.traceId) {
      nextTraceId = payload.traceId;
    }
    if (typeof payload.mode === 'string' && (payload.mode === 'local' || payload.mode === 'web' || payload.mode === 'hybrid')) {
      nextMode = payload.mode;
    }
    if (event.event_type === 'error') {
      nextErrorMeta = normalizeJobEventError(payload, job?.error);
    }
    if (isAgentEventPayload(payload)) {
      nextAgentEvents.push(payload);
    }
  }

  const jobErrorMeta = !nextErrorMeta && job?.error ? normalizeJobEventError(job.error, job.error) : nextErrorMeta;
  const nextContent =
    messagePieces.length > 0
      ? messagePieces.join('')
      : (job?.latest_output_text ?? '').trim() || (job?.state === 'queued' || job?.state === 'running' ? '正在生成回答…' : message.content);
  const nextStatus =
    job?.state === 'failed'
      ? 'error'
      : job?.state === 'succeeded' || job?.state === 'cancelled'
        ? 'done'
        : 'streaming';
  const nextTrace = (job?.trace_id ?? nextTraceId) || undefined;
  const nextRun = (job?.run_id ?? nextRunId) || undefined;
  const errorMeta = jobErrorMeta ?? undefined;
  const content =
    nextStatus === 'error' && (!nextContent || nextContent === '正在生成回答…')
      ? `请求失败：${errorMeta?.code || 'JOB_FAILED'} - ${errorMeta?.detail || '后台任务执行失败'}`
      : nextContent;

  return {
    ...message,
    traceId: nextTrace,
    runId: nextRun,
    mode: nextMode,
    content,
    sources: nextSources,
    agentEvents: nextAgentEvents.length ? nextAgentEvents : undefined,
    status: nextStatus,
    errorMeta
  };
}

function normalizeJobEventError(payload: Record<string, unknown> | undefined, fallback: Record<string, unknown> | null | undefined) {
  const source = payload && Object.keys(payload).length > 0 ? payload : fallback ?? {};
  const detail = isRecord(source.detail) ? source.detail : source;
  const code = readString(detail.code) || readString(source.code) || readString(detail.reason_code) || 'JOB_FAILED';
  const message =
    readString(detail.message) ||
    readString(source.message) ||
    readString(detail.detail) ||
    readString(source.detail) ||
    readString(detail.error) ||
    '后台任务执行失败';
  return { code, detail: message };
}

function normalizeJobCreateFailure(payload: unknown, fallbackMessage: string): { code: string; detail: string; message: string } {
  if (isRecord(payload)) {
    const detail = isRecord(payload.detail) ? payload.detail : payload;
    const code = readString(detail.code) || readString(payload.code) || 'JOB_CREATE_REJECTED';
    const message = readString(detail.message) || readString(payload.message) || fallbackMessage || '创建后台任务失败';
    return { code, detail: message, message };
  }
  return {
    code: 'JOB_CREATE_REJECTED',
    detail: fallbackMessage || '创建后台任务失败',
    message: fallbackMessage || '创建后台任务失败'
  };
}

function chatMessageEquals(left: ChatMessage, right: ChatMessage): boolean {
  return (
    left.jobId === right.jobId &&
    left.traceId === right.traceId &&
    left.runId === right.runId &&
    left.content === right.content &&
    left.status === right.status &&
    left.mode === right.mode &&
    JSON.stringify(left.sources ?? []) === JSON.stringify(right.sources ?? []) &&
    JSON.stringify(left.agentEvents ?? []) === JSON.stringify(right.agentEvents ?? []) &&
    JSON.stringify(left.errorMeta ?? null) === JSON.stringify(right.errorMeta ?? null)
  );
}

function isAgentEventPayload(value: unknown): value is AgentEvent {
  if (!isRecord(value) || typeof value.type !== 'string') {
    return false;
  }
  return ['planning', 'toolSelection', 'toolRunning', 'toolResult', 'fallback', 'serviceBlocked'].includes(value.type);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function readString(value: unknown): string {
  return typeof value === 'string' ? value : '';
}

function buildSessionSummary(sessionId: string, messages: ChatMessage[], createdAt?: string): ChatSessionSummary {
  const firstUserMessage = messages.find((item) => item.role === 'user')?.content.trim() || '新对话';
  const preview = [...messages].reverse().find((item) => item.role === 'assistant' || item.role === 'user')?.content.trim() || '';
  const title = firstUserMessage.length > 22 ? `${firstUserMessage.slice(0, 22)}...` : firstUserMessage;
  const now = new Date().toISOString();
  return {
    id: sessionId,
    title,
    createdAt: createdAt || now,
    updatedAt: now,
    preview: preview.length > 56 ? `${preview.slice(0, 56)}...` : preview,
    messageCount: messages.length
  };
}

function toSessionSummary(session: ChatSessionSummary & { messages?: ChatMessage[] }): ChatSessionSummary {
  return {
    id: session.id,
    title: session.title || '新对话',
    createdAt: session.createdAt,
    updatedAt: session.updatedAt,
    preview: session.preview || '',
    messageCount: session.messageCount ?? session.messages?.length ?? 0
  };
}

function loadStoredMessages(sessionId: string): ChatMessage[] {
  try {
    const sessions = loadStoredSessions();
    return sessions.find((item) => item.id === sessionId)?.messages ?? [];
  } catch {
    return [];
  }
}

function loadStoredSessions(): StoredChatSession[] {
  const raw = localStorage.getItem(storageKey);
  if (!raw) {
    return [];
  }
  const parsed = JSON.parse(raw) as { sessions?: StoredChatSession[] };
  return Array.isArray(parsed.sessions) ? parsed.sessions : [];
}

function saveStoredSessions(sessions: StoredChatSession[]) {
  try {
    localStorage.setItem(storageKey, JSON.stringify({ sessions: sessions.slice(0, 24) }));
  } catch {
    // ignore storage failures
  }
}

function loadStoredActiveSessionId() {
  const raw = localStorage.getItem(activeSessionStorageKey);
  return typeof raw === 'string' ? raw : '';
}

function saveStoredActiveSessionId(sessionId: string) {
  try {
    localStorage.setItem(activeSessionStorageKey, sessionId);
  } catch {
    // ignore storage failures
  }
}

function sortSessionsByUpdatedAt<T extends { updatedAt: string }>(items: T[]) {
  return [...items].sort((a, b) => +new Date(b.updatedAt) - +new Date(a.updatedAt));
}

function groupSessionsByTime(items: ChatSessionSummary[]) {
  const groups = [
    { label: '今天', items: [] as ChatSessionSummary[] },
    { label: '昨天', items: [] as ChatSessionSummary[] },
    { label: '更早', items: [] as ChatSessionSummary[] }
  ];
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const yesterday = today - 24 * 60 * 60 * 1000;

  items.forEach((item) => {
    const time = new Date(item.updatedAt).getTime();
    if (time >= today) {
      groups[0].items.push(item);
    } else if (time >= yesterday) {
      groups[1].items.push(item);
    } else {
      groups[2].items.push(item);
    }
  });

  return groups.filter((group) => group.items.length > 0);
}

function formatRelativeTime(raw: string) {
  const date = new Date(raw);
  if (Number.isNaN(date.getTime())) {
    return raw;
  }
  return date.toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function formatAgentEventTitle(event: AgentEvent) {
  if (event.type === 'planning') {
    return `Planning · ${event.executionSource || event.plannerSource || 'unknown'}`;
  }
  if (event.type === 'toolSelection') {
    return `Tool selected · ${event.toolName}`;
  }
  if (event.type === 'toolRunning') {
    return `Tool running · ${event.toolName}`;
  }
  if (event.type === 'toolResult') {
    return `Tool result · ${event.toolName} · ${event.status}`;
  }
  if (event.type === 'serviceBlocked') {
    return 'Service blocked';
  }
  return `Fallback · ${event.fallbackScope}`;
}

function formatAgentEventDetail(event: AgentEvent) {
  if (event.type === 'planning') {
    const tools = (event.selectedToolsOrSkills ?? []).join(', ') || 'none';
    return `decision=${event.decisionResult || '-'} path=${event.selectedPath || '-'} sourceMode=${event.plannerSourceMode || '-'} tools=${tools}`;
  }
  if (event.type === 'toolSelection' || event.type === 'toolRunning') {
    return `callId=${event.callId}`;
  }
  if (event.type === 'toolResult') {
    return event.message ? `${event.resultKind || event.status} · ${event.message}` : `${event.resultKind || event.status}`;
  }
  if (event.type === 'serviceBlocked') {
    return `reason=${event.reasonCode || '-'} mode=${event.serviceMode || '-'}${event.message ? ` · ${event.message}` : ''}`;
  }
  const toolPart = event.failedTool ? ` failedTool=${event.failedTool}` : '';
  const messagePart = event.message ? ` · ${event.message}` : '';
  return `reason=${event.reasonCode}${toolPart}${messagePart}`;
}

function DebugBlock({ title, content }: { title: string; content?: string }) {
  if (!content) {
    return null;
  }
  const formatted = formatDebugContent(content);
  return (
    <div>
      <p className="mb-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">{title}</p>
      <pre className="overflow-x-auto whitespace-pre-wrap rounded-2xl bg-slate-950 px-3 py-2 font-mono text-[11px] leading-5 text-slate-100">
        {formatted}
      </pre>
    </div>
  );
}

function formatDebugContent(content: string): string {
  const normalize = (value: unknown): unknown => {
    if (typeof value === 'string') {
      const trimmed = value.trim();
      if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
        try {
          return normalize(JSON.parse(trimmed));
        } catch {
          return value;
        }
      }
      return value;
    }
    if (Array.isArray(value)) {
      return value.map((item) => normalize(item));
    }
    if (isRecord(value)) {
      return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, normalize(item)]));
    }
    return value;
  };

  const normalized = normalize(content);
  if (typeof normalized === 'string') {
    return normalized;
  }
  try {
    return JSON.stringify(normalized, null, 2);
  } catch {
    return content;
  }
}

function toSourceLabel(type: SourceItem['source_type']) {
  if (type === 'local') return '知识库';
  if (type === 'web') return '网页';
  return '图谱';
}
