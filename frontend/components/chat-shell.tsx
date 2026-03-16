'use client';

import Link from 'next/link';
import {
  Bot,
  ChevronRight,
  Globe,
  History,
  MessageSquarePlus,
  Network,
  SearchCheck,
  Sparkles,
  Trash2
} from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import rehypeHighlight from 'rehype-highlight';
import type { AgentEvent, ChatMessage, ChatMode, RuntimeOverview, SourceItem, ViewMode } from '../lib/types';
import { fetchAdminJson } from '../lib/admin-http';
import { resolveAdminUrl, resolveGatewayWebSocketUrl } from '../lib/deployment-endpoints';
import { buildGraphSubgraph } from '../lib/graph';
import { mapConnectionStatus, mapRuntimeLevel } from '../lib/status-mapper';
import { GraphSubgraphPanel } from './graph-subgraph';

type WsPayload =
  | AgentEvent
  | { type: 'message'; traceId: string; mode: ChatMode; content: string }
  | { type: 'sources'; traceId: string; mode: ChatMode; sources: SourceItem[] }
  | { type: 'messageEnd'; traceId: string; mode: ChatMode; usage?: { latencyMs: number } }
  | { type: 'error'; traceId: string; code: string; message: string };

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
  { key: 'local', label: '仅知识库', hint: '只检索本地资料', icon: SearchCheck },
  { key: 'web', label: '联网补充', hint: '补充公开网络信息', icon: Globe },
  { key: 'hybrid', label: '混合回答', hint: '本地证据与网络结合', icon: Network }
];

const viewModeOptions: Array<{ key: ViewMode; label: string }> = [
  { key: 'user', label: '简洁视图' },
  { key: 'developer', label: '调试视图' }
];

const promptSuggestions = [
  '总结当前知识库里关于 GraphRAG 的核心方法差异',
  '给我一份最近导入论文的关键贡献对比表',
  '基于现有证据回答：为什么这套方案更稳健？',
  '列出可直接落地到生产环境的三项改进建议'
];

const storageKey = 'rag-workbench-chat-history-v1';

export function ChatShell() {
  const [mode, setMode] = useState<ChatMode>('local');
  const [viewMode, setViewMode] = useState<ViewMode>('user');
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [statusText, setStatusText] = useState('Disconnected');
  const [selectedCitation, setSelectedCitation] = useState<number | null>(null);
  const [expandedGraphByMessage, setExpandedGraphByMessage] = useState<Record<string, boolean>>({});
  const [sendError, setSendError] = useState('');
  const [isSending, setIsSending] = useState(false);
  const [runtimeOverview, setRuntimeOverview] = useState<RuntimeOverview | null>(null);
  const [runtimeOverviewError, setRuntimeOverviewError] = useState('');
  const [lastFailedQuery, setLastFailedQuery] = useState('');
  const [sessionHistory, setSessionHistory] = useState<ChatSessionSummary[]>([]);
  const [activeSessionId, setActiveSessionId] = useState('');
  const [historyHydrated, setHistoryHydrated] = useState(false);

  const wsRef = useRef<WebSocket | null>(null);
  const pendingSourcesRef = useRef<Record<string, SourceItem[]>>({});
  const pendingAgentEventsRef = useRef<Record<string, AgentEvent[]>>({});
  const messageBottomRef = useRef<HTMLDivElement | null>(null);
  const sessionIdRef = useRef(crypto.randomUUID());

  const wsUrl = useMemo(() => resolveGatewayWebSocketUrl(), []);
  const runtimeOverviewUrl = useMemo(() => resolveAdminUrl('/api/admin/runtime-overview'), []);
  const statusLevel = runtimeOverview?.status?.level ?? 'ERROR';
  const answerConfigured = Boolean(runtimeOverview?.llm?.answer?.configured);
  const canSend = input.trim().length > 0 && statusText === 'Connected' && answerConfigured && statusLevel !== 'BLOCKED';
  const connection = mapConnectionStatus(statusText);
  const runtimeView = mapRuntimeLevel(statusLevel);

  useEffect(() => {
    if (!wsUrl) {
      setStatusText('Connection error');
      return;
    }

    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => setStatusText('Connected');
    ws.onclose = () => setStatusText('Disconnected');
    ws.onerror = () => setStatusText('Connection error');

    ws.onmessage = (event) => {
      const payload = JSON.parse(event.data) as WsPayload;

      if (
        payload.type === 'planning' ||
        payload.type === 'toolSelection' ||
        payload.type === 'toolRunning' ||
        payload.type === 'toolResult' ||
        payload.type === 'fallback'
      ) {
        const existingEvents = pendingAgentEventsRef.current[payload.traceId] ?? [];
        pendingAgentEventsRef.current[payload.traceId] = [...existingEvents, payload];
        setMessages((prev) =>
          prev.map((item) =>
            item.traceId === payload.traceId && item.role === 'assistant'
              ? {
                  ...item,
                  agentEvents: [...(item.agentEvents ?? []), payload]
                }
              : item
          )
        );
        return;
      }

      if (payload.type === 'sources') {
        pendingSourcesRef.current[payload.traceId] = payload.sources;
        return;
      }

      if (payload.type === 'message') {
        setMessages((prev) => {
          const existing = prev.find((item) => item.traceId === payload.traceId && item.role === 'assistant');
          if (!existing) {
            const assistantMessage: ChatMessage = {
              id: crypto.randomUUID(),
              traceId: payload.traceId,
              role: 'assistant',
              content: payload.content,
              mode: payload.mode,
              status: 'streaming',
              sources: pendingSourcesRef.current[payload.traceId] ?? [],
              agentEvents: pendingAgentEventsRef.current[payload.traceId] ?? []
            };
            return [...prev, assistantMessage];
          }
          return prev.map((item) =>
            item.id === existing.id
              ? {
                  ...item,
                  content: `${item.content}${payload.content}`,
                  status: 'streaming'
                }
              : item
          );
        });
        setIsSending(true);
        return;
      }

      if (payload.type === 'messageEnd') {
        setMessages((prev) =>
          prev.map((item) =>
            item.traceId === payload.traceId && item.role === 'assistant'
              ? {
                  ...item,
                  status: 'done',
                  sources: pendingSourcesRef.current[payload.traceId] ?? item.sources,
                  agentEvents: pendingAgentEventsRef.current[payload.traceId] ?? item.agentEvents
                }
              : item
          )
        );
        setIsSending(false);
        setSendError('');
        delete pendingSourcesRef.current[payload.traceId];
        delete pendingAgentEventsRef.current[payload.traceId];
        return;
      }

      if (payload.type === 'error') {
        setMessages((prev) => [
          ...prev,
          {
            id: crypto.randomUUID(),
            traceId: payload.traceId,
            role: 'assistant',
            content: `请求失败：${payload.code} - ${payload.message}`,
            mode,
            status: 'error',
            sources: [],
            agentEvents: pendingAgentEventsRef.current[payload.traceId] ?? []
          }
        ]);
        setSendError(payload.message);
        setIsSending(false);
        delete pendingSourcesRef.current[payload.traceId];
        delete pendingAgentEventsRef.current[payload.traceId];
      }
    };

    return () => ws.close();
  }, [mode, wsUrl]);

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
    try {
      const sessions = loadStoredSessions();
      if (!sessions.length) {
        const newId = sessionIdRef.current;
        setActiveSessionId(newId);
        return;
      }
      const sorted = sortSessionsByUpdatedAt(sessions);
      const current = sorted[0];
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

  const sendQuery = (query: string) => {
    if (!query.trim()) {
      return;
    }
    if (!answerConfigured || statusLevel === 'BLOCKED') {
      setSendError('当前推理模型未就绪，请先前往“模型设置”完成配置。');
      return;
    }
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      setSendError('WebSocket 未连接，请确认 Gateway 服务已启动。');
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
    setSendError('');
    setIsSending(true);

    wsRef.current.send(
      JSON.stringify({
        type: 'chat',
        payload: {
          sessionId: sessionIdRef.current,
          query,
          mode,
          history: messages.slice(-8).map((item) => ({
            role: item.role,
            content: item.content
          }))
        }
      })
    );
  };

  const handleSend = () => {
    const query = input.trim();
    if (!query) {
      return;
    }
    setLastFailedQuery(query);
    sendQuery(query);
  };

  const createNewSession = () => {
    const nextId = crypto.randomUUID();
    sessionIdRef.current = nextId;
    setActiveSessionId(nextId);
    setMessages([]);
    setExpandedGraphByMessage({});
    setSelectedCitation(null);
    setSendError('');
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
    setSendError('');
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
      setSendError('');
      setLastFailedQuery('');
      return;
    }

    createNewSession();
  };

  const historyGroups = useMemo(() => groupSessionsByTime(sessionHistory), [sessionHistory]);
  const hasMessages = messages.length > 0;
  const latestAssistantMessage = [...messages].reverse().find((item) => item.role === 'assistant');
  const sourceCount = latestAssistantMessage?.sources?.length ?? 0;
  const showSessionAside = true;

  return (
    <section className="grid items-start gap-5 2xl:grid-cols-[252px_minmax(0,1fr)]">
      <aside className="order-2 rounded-[28px] border border-white/70 bg-[linear-gradient(180deg,rgba(255,255,255,0.96),rgba(244,247,251,0.92))] p-3 shadow-[0_20px_80px_rgba(15,23,42,0.08)] backdrop-blur 2xl:order-1 2xl:sticky 2xl:top-6">
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
                  把提问、引用与图谱验证放在同一个工作流里，让首屏先服务于发问和继续追问。
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
              <span className="rounded-full border border-slate-200 bg-white/90 px-3 py-1.5 text-xs text-slate-600">左侧自动保存历史，首屏优先留给提问。</span>
              {runtimeOverviewError ? <span className="text-xs text-rose-600">{runtimeOverviewError}</span> : null}
            </div>
          </div>

          {!answerConfigured || statusLevel === 'BLOCKED' ? (
            <div className="mt-4 rounded-2xl border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900">
              当前推理模型不可用。请先前往
              <Link href="/settings" className="mx-1 font-semibold underline underline-offset-2">
                模型设置
              </Link>
              完成配置后再开始问答。
            </div>
          ) : null}
        </header>

        <div className={`mt-5 grid gap-4 ${showSessionAside ? '2xl:grid-cols-[minmax(0,1fr)_300px]' : '2xl:grid-cols-1'}`}>
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
                hasMessages ? 'h-[62vh] md:h-[64vh]' : 'h-[58vh] md:h-[62vh]'
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
                        onClick={() => sendQuery(item)}
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
                          {message.status === 'streaming' ? <span>生成中</span> : null}
                        </div>

                        <div className="prose prose-sm max-w-none prose-headings:text-slate-900 prose-p:text-slate-700 prose-pre:bg-slate-950 prose-pre:text-slate-100 prose-code:text-slate-900">
                          <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex, rehypeHighlight]}>
                            {message.content}
                          </ReactMarkdown>
                        </div>

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
                                    agentEvent.type === 'fallback'
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
                  {isSending ? '发送中...' : '发送'}
                </button>
              </div>
              {sendError ? <p className="mt-2 text-xs text-rose-600">{sendError}</p> : null}
              {sendError && lastFailedQuery ? (
                <button
                  type="button"
                  onClick={() => sendQuery(lastFailedQuery)}
                  className="mt-2 text-xs font-medium text-sky-700 underline underline-offset-2"
                >
                  重试上一条问题
                </button>
              ) : null}
            </footer>
          </div>

          {showSessionAside ? <aside data-testid="chat-session-aside" className="space-y-4">
            <div className="rounded-[28px] border border-slate-200 bg-white/85 p-4">
              <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-slate-500">本次会话速览</p>
              <div className="mt-3 grid gap-3">
                <div className="rounded-2xl bg-slate-50 px-4 py-3">
                  <p className="text-xs text-slate-500">引用条目</p>
                  <p className="mt-1 text-2xl font-semibold text-slate-950">{sourceCount}</p>
                </div>
                <div className="rounded-2xl bg-slate-50 px-4 py-3">
                  <p className="text-xs text-slate-500">当前模式</p>
                  <p className="mt-1 text-sm font-medium text-slate-900">{modeOptions.find((item) => item.key === mode)?.label}</p>
                </div>
                <div className="rounded-2xl bg-slate-50 px-4 py-3">
                  <p className="text-xs text-slate-500">证据回看</p>
                  <p className="mt-1 text-sm leading-6 text-slate-700">
                    {hasMessages ? '回答会优先给出“资料来自哪里”，减少只看结论看不懂的情况。' : '开始提问后，这里会持续汇总当前会话的引用和阅读重点。'}
                  </p>
                </div>
              </div>
            </div>

            <div className="rounded-[28px] border border-slate-200 bg-[linear-gradient(180deg,#fffefb,#fff)] p-4">
              <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-slate-500">使用提示</p>
              <ul className="mt-3 space-y-3 text-sm leading-6 text-slate-600">
                <li>先问“总结”和“对比”，系统更容易给出结构化答案。</li>
                <li>若结果过泛，可继续追问“请只基于已导入论文回答”。</li>
                <li>切到“调试视图”可查看图谱子图和更多技术元数据。</li>
              </ul>
            </div>
          </aside> : null}
        </div>
      </div>
    </section>
  );
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
  const toolPart = event.failedTool ? ` failedTool=${event.failedTool}` : '';
  const messagePart = event.message ? ` · ${event.message}` : '';
  return `reason=${event.reasonCode}${toolPart}${messagePart}`;
}

function toSourceLabel(type: SourceItem['source_type']) {
  if (type === 'local') return '知识库';
  if (type === 'web') return '网页';
  return '图谱';
}
