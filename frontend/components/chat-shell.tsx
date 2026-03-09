'use client';

import Link from 'next/link';
import { useEffect, useMemo, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import rehypeHighlight from 'rehype-highlight';
import type { ChatMessage, ChatMode, RuntimeOverview, SourceItem, ViewMode } from '../lib/types';
import { fetchAdminJson } from '../lib/admin-http';
import { buildGraphSubgraph } from '../lib/graph';
import { GraphSubgraphPanel } from './graph-subgraph';
import { mapConnectionStatus, mapRuntimeLevel } from '../lib/status-mapper';

type WsPayload =
  | { type: 'message'; traceId: string; mode: ChatMode; content: string }
  | { type: 'sources'; traceId: string; mode: ChatMode; sources: SourceItem[] }
  | { type: 'messageEnd'; traceId: string; mode: ChatMode; usage?: { latencyMs: number } }
  | { type: 'error'; traceId: string; code: string; message: string };

const modeOptions: Array<{ key: ChatMode; label: string }> = [
  { key: 'local', label: '本地' },
  { key: 'web', label: '联网' },
  { key: 'hybrid', label: '混合' }
];

const viewModeOptions: Array<{ key: ViewMode; label: string }> = [
  { key: 'user', label: '用户视图' },
  { key: 'developer', label: '开发视图' }
];

const promptSuggestions = [
  '总结当前知识库里关于 GraphRAG 的核心方法差异',
  '给我一份最近导入论文的关键贡献对比表',
  '基于现有证据回答：为什么这套方案更稳健？',
  '列出可直接落地到生产环境的三项改进建议'
];

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

  const wsRef = useRef<WebSocket | null>(null);
  const pendingSourcesRef = useRef<Record<string, SourceItem[]>>({});
  const messageBottomRef = useRef<HTMLDivElement | null>(null);
  const sessionIdRef = useRef(crypto.randomUUID());

  const wsUrl = process.env.NEXT_PUBLIC_GATEWAY_WS_URL ?? 'ws://localhost:8080/ws';
  const kernelBaseUrl = process.env.NEXT_PUBLIC_KERNEL_BASE_URL ?? '';
  const statusLevel = runtimeOverview?.status?.level ?? 'ERROR';
  const answerConfigured = Boolean(runtimeOverview?.llm?.answer?.configured);
  const canSend = input.trim().length > 0 && statusText === 'Connected' && answerConfigured && statusLevel !== 'BLOCKED';
  const connection = mapConnectionStatus(statusText);
  const runtimeView = mapRuntimeLevel(statusLevel);

  useEffect(() => {
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => setStatusText('Connected');
    ws.onclose = () => setStatusText('Disconnected');
    ws.onerror = () => setStatusText('Connection error');

    ws.onmessage = (event) => {
      const payload = JSON.parse(event.data) as WsPayload;

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
              sources: pendingSourcesRef.current[payload.traceId] ?? []
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
                  sources: pendingSourcesRef.current[payload.traceId] ?? item.sources
                }
              : item
          )
        );
        setIsSending(false);
        setSendError('');
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
            sources: []
          }
        ]);
        setSendError(payload.message);
        setIsSending(false);
      }
    };

    return () => ws.close();
  }, [mode, wsUrl]);

  useEffect(() => {
    let mounted = true;
    const loadRuntimeOverview = async () => {
      try {
        const result = await fetchAdminJson<RuntimeOverview>(`${kernelBaseUrl}/api/admin/runtime-overview`);
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
  }, [kernelBaseUrl]);

  useEffect(() => {
    messageBottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages]);

  const sendQuery = (query: string) => {
    if (!query.trim()) {
      return;
    }
    if (!answerConfigured || statusLevel === 'BLOCKED') {
      setSendError('Answer 模型未就绪，请先前往“模型设置”完成配置。');
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

  const hasMessages = messages.length > 0;

  const emptyState = useMemo(
    () => (
      <div className="flex h-full min-h-[360px] flex-col items-center justify-center rounded-3xl border border-dashed border-slate-300 bg-gradient-to-br from-white to-slate-100 text-center">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">对话问答</p>
        <h3 className="mt-3 text-2xl font-semibold tracking-tight text-slate-900">向你的研究知识库提问</h3>
        <p className="mt-2 max-w-md text-sm text-slate-600">
          支持本地检索、联网补充与混合模式。回答将附带证据来源，便于快速验证。
        </p>
        <div className="mt-5 grid w-full max-w-3xl gap-2 px-4 md:grid-cols-2">
          {promptSuggestions.map((item) => (
            <button
              key={item}
              type="button"
              onClick={() => sendQuery(item)}
              className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-left text-xs text-slate-700 transition hover:border-sky-300 hover:bg-sky-50"
            >
              {item}
            </button>
          ))}
        </div>
      </div>
    ),
    []
  );

  return (
    <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm md:p-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">对话问答</p>
          <h2 className="mt-2 text-2xl font-semibold tracking-tight">知识问答与证据追踪</h2>
          <p className="mt-2 text-sm text-slate-600">面向真实使用场景的聊天界面，支持流式响应、引用溯源与图谱子图可视化。</p>
        </div>
        <span className="inline-flex items-center gap-2 text-xs text-slate-600">
          <span
            className={`h-2.5 w-2.5 rounded-full ${connection.connected ? 'bg-emerald-500 shadow-[0_0_10px_rgba(16,185,129,0.65)]' : 'bg-slate-400'}`}
            aria-hidden
          />
          {connection.connected ? '🟢 已连接' : '⚪ 未连接'}
        </span>
      </header>

      {runtimeOverview ? (
        <div data-testid="chat-runtime-summary" className="mt-4 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-800">
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">当前会话模型摘要</p>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <span className="rounded-full border border-slate-200 bg-white px-2 py-1 text-xs">
              [推理模型] 🏷️ {runtimeOverview.llm.answer.model || '-'}
            </span>
            <span className="rounded-full border border-slate-200 bg-white px-2 py-1 text-xs">
              [重排模型] 🏷️ {runtimeOverview.llm.rerank.model || '-'}
            </span>
            <span className="rounded-full border border-slate-200 bg-white px-2 py-1 text-xs">
              [重写模型] 🏷️ {runtimeOverview.llm.rewrite.model || '-'}
            </span>
          </div>
          <p className="mt-2 text-xs">
            状态: {runtimeView.icon} {runtimeView.label}
          </p>
          {runtimeOverview.status.reasons.length ? (
            <p className="mt-1 text-xs text-amber-700">{runtimeOverview.status.reasons[0]}</p>
          ) : null}
        </div>
      ) : null}

      {!answerConfigured || statusLevel === 'BLOCKED' ? (
        <div className="mt-4 rounded-2xl border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          检测到 Answer 路由不可用。请先前往
          <Link href="/settings" className="mx-1 font-semibold underline underline-offset-2">
            模型设置
          </Link>
          后再发起对话。
        </div>
      ) : null}
      {runtimeOverviewError ? <p className="mt-2 text-xs text-rose-600">{runtimeOverviewError}</p> : null}

      <div className="mt-4 flex flex-wrap items-center gap-2">
        {modeOptions.map((item) => (
          <button
            key={item.key}
            type="button"
            onClick={() => setMode(item.key)}
            className={`rounded-full border px-3 py-1.5 text-xs font-medium transition ${
              mode === item.key ? 'border-slate-900 bg-slate-900 text-white' : 'border-slate-200 bg-white text-slate-600'
            }`}
          >
            {item.label}
          </button>
        ))}

        <div className="ml-auto flex gap-2">
          {viewModeOptions.map((item) => (
            <button
              key={item.key}
              type="button"
              onClick={() => setViewMode(item.key)}
              className={`rounded-full border px-3 py-1.5 text-xs font-medium transition ${
                viewMode === item.key ? 'border-sky-600 bg-sky-600 text-white' : 'border-slate-200 bg-white text-slate-600'
              }`}
            >
              {item.label}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-4 h-[56vh] overflow-y-auto rounded-3xl border border-slate-200 bg-slate-50/80 p-3 md:p-4">
        {!hasMessages ? (
          emptyState
        ) : (
          <div className="space-y-3">
            {messages.map((message) => {
              const graph = buildGraphSubgraph(message.sources ?? []);
              const showGraphPanel =
                (message.sources ?? []).some((source) => source.source_type === 'graph') || viewMode === 'developer';

              return (
                <article
                  key={message.id}
                  className={`max-w-[92%] rounded-2xl border px-4 py-3 text-sm shadow-sm backdrop-blur-xl ${
                    message.role === 'user'
                      ? 'ml-auto border-sky-200 bg-sky-100/70 text-slate-900'
                      : 'border-white/70 bg-white/70 text-slate-900'
                  }`}
                >
                  <div className="mb-2 flex items-center gap-2 text-[11px] uppercase tracking-[0.14em] text-slate-500">
                    <span>{message.role === 'user' ? '用户' : 'AI 助手'}</span>
                    {message.mode ? <span>{message.mode}</span> : null}
                    {message.status === 'streaming' ? <span>生成中...</span> : null}
                  </div>

                  <div className="prose prose-sm max-w-none prose-pre:bg-slate-900 prose-pre:text-slate-100 prose-code:text-slate-900">
                    <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex, rehypeHighlight]}>
                      {message.content}
                    </ReactMarkdown>
                  </div>

                  {message.sources && message.sources.length > 0 ? (
                    <div className="mt-3 rounded-xl border border-slate-200 bg-white/80 p-2.5">
                      <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">证据来源</div>
                      <div className="space-y-2">
                        {message.sources.map((source, index) => {
                          const isSelected = selectedCitation === index + 1;
                          return (
                            <button
                              key={`${message.id}-${source.source_id}`}
                              type="button"
                              onClick={() => setSelectedCitation(index + 1)}
                              className={`w-full rounded-xl border px-3 py-2 text-left text-xs transition ${
                                isSelected ? 'border-sky-300 bg-sky-50' : 'border-slate-200 bg-white'
                              }`}
                            >
                              <p className="font-medium text-slate-800">
                                [{index + 1}] {source.title}
                              </p>
                              <p className="mt-1 text-slate-600">{source.snippet}</p>
                              <p className="mt-1 text-[10px] uppercase tracking-[0.1em] text-slate-500">
                                {source.source_type} · {source.locator} · score {source.score.toFixed(3)}
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

      <footer className="mt-4 rounded-2xl border border-slate-200 bg-white p-3">
        <label className="mb-2 block text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">输入问题</label>
        <div className="flex gap-2">
          <input
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                handleSend();
              }
            }}
            placeholder="例如：比较这两篇论文的方法差异并给出处证据。"
            className="h-11 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm outline-none ring-sky-300 transition focus:ring-2"
          />
          <button
            type="button"
            onClick={handleSend}
            disabled={!canSend || isSending}
            className="h-11 rounded-xl bg-slate-900 px-4 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-50"
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
    </section>
  );
}
