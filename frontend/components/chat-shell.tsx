'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import type { ChatMessage, ChatMode, SourceItem, ViewMode } from '../lib/types';
import { buildGraphSubgraph } from '../lib/graph';
import { GraphSubgraphPanel } from './graph-subgraph';

type WsPayload =
  | { type: 'message'; traceId: string; mode: ChatMode; content: string }
  | { type: 'sources'; traceId: string; mode: ChatMode; sources: SourceItem[] }
  | { type: 'messageEnd'; traceId: string; mode: ChatMode; usage?: { latencyMs: number } }
  | { type: 'error'; traceId: string; code: string; message: string };

type AdminModel = { id: string; owned_by?: string | null };
type StageKey = 'answer' | 'embedding' | 'rerank';
type StageConfig = {
  provider: string;
  apiBase: string;
  apiKey: string;
  model: string;
  models: AdminModel[];
  detectLoading: boolean;
  error: string;
};

const stageOptions: Array<{ key: StageKey; label: string; defaultProvider: string; defaultApiBase: string }> = [
  { key: 'answer', label: 'Answer', defaultProvider: 'openai', defaultApiBase: 'http://127.0.0.1:8000/v1' },
  { key: 'embedding', label: 'Embedding', defaultProvider: 'siliconflow', defaultApiBase: 'http://127.0.0.1:8000/v1' },
  { key: 'rerank', label: 'Rerank', defaultProvider: 'siliconflow', defaultApiBase: 'http://127.0.0.1:8000/v1' }
];

const modeOptions: Array<{ key: ChatMode; label: string }> = [
  { key: 'local', label: 'Local' },
  { key: 'web', label: 'Web' },
  { key: 'hybrid', label: 'Hybrid' }
];

const viewModes: Array<{ key: ViewMode; label: string }> = [
  { key: 'user', label: 'User View' },
  { key: 'developer', label: 'Developer View' }
];

function parseCitations(text: string): Array<{ label: string; citationNumber?: number }> {
  const tokens: Array<{ label: string; citationNumber?: number }> = [];
  const pattern = /\[(\d+)\]/g;
  let lastIndex = 0;

  for (const match of text.matchAll(pattern)) {
    const matchIndex = match.index ?? 0;
    if (matchIndex > lastIndex) {
      tokens.push({ label: text.slice(lastIndex, matchIndex) });
    }
    tokens.push({ label: `[${match[1]}]`, citationNumber: Number(match[1]) });
    lastIndex = matchIndex + match[0].length;
  }

  if (lastIndex < text.length) {
    tokens.push({ label: text.slice(lastIndex) });
  }

  return tokens;
}

export function ChatShell() {
  const [mode, setMode] = useState<ChatMode>('local');
  const [viewMode, setViewMode] = useState<ViewMode>('user');
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [selectedCitation, setSelectedCitation] = useState<number | null>(null);
  const [statusText, setStatusText] = useState('Disconnected');
  const [expandedGraphByMessage, setExpandedGraphByMessage] = useState<Record<string, boolean>>({});
  const [stageConfigs, setStageConfigs] = useState<Record<StageKey, StageConfig>>({
    answer: {
      provider: 'openai',
      apiBase: 'http://127.0.0.1:8000/v1',
      apiKey: '',
      model: '',
      models: [],
      detectLoading: false,
      error: ''
    },
    embedding: {
      provider: 'siliconflow',
      apiBase: 'http://127.0.0.1:8000/v1',
      apiKey: '',
      model: '',
      models: [],
      detectLoading: false,
      error: ''
    },
    rerank: {
      provider: 'siliconflow',
      apiBase: 'http://127.0.0.1:8000/v1',
      apiKey: '',
      model: '',
      models: [],
      detectLoading: false,
      error: ''
    }
  });
  const [saveLoading, setSaveLoading] = useState(false);
  const [adminStatus, setAdminStatus] = useState('');
  const [adminError, setAdminError] = useState('');

  const wsRef = useRef<WebSocket | null>(null);
  const pendingSourcesRef = useRef<Record<string, SourceItem[]>>({});
  const messageBottomRef = useRef<HTMLDivElement | null>(null);
  const sessionIdRef = useRef(crypto.randomUUID());

  const canSend = useMemo(() => input.trim().length > 0, [input]);
  const wsUrl = process.env.NEXT_PUBLIC_GATEWAY_WS_URL ?? 'ws://localhost:8080/ws';
  const kernelBaseUrl = process.env.NEXT_PUBLIC_KERNEL_BASE_URL ?? 'http://127.0.0.1:8000';

  const parseAdminError = (payload: unknown): { message: string; stage?: StageKey } => {
    if (!payload || typeof payload !== 'object') {
      return { message: '请求失败' };
    }
    const detail = (payload as { detail?: unknown }).detail;
    if (detail && typeof detail === 'object') {
      const maybeCode = (detail as { code?: unknown }).code;
      const maybeMessage = (detail as { message?: unknown }).message;
      const maybeStage = (detail as { stage?: unknown }).stage;
      const codeText = typeof maybeCode === 'string' && maybeCode ? `[${maybeCode}] ` : '';
      const messageText = typeof maybeMessage === 'string' && maybeMessage ? maybeMessage : '请求失败';
      const stage =
        maybeStage === 'answer' || maybeStage === 'embedding' || maybeStage === 'rerank' ? maybeStage : undefined;
      return { message: `${codeText}${messageText}`, stage };
    }
    return { message: '请求失败' };
  };

  const setStageConfigField = <K extends keyof StageConfig>(stage: StageKey, field: K, value: StageConfig[K]) => {
    setStageConfigs((prev) => ({ ...prev, [stage]: { ...prev[stage], [field]: value } }));
  };

  const findStageInMessage = (message: string): StageKey | null => {
    const normalized = message.toLowerCase();
    if (normalized.includes('answer')) return 'answer';
    if (normalized.includes('embedding')) return 'embedding';
    if (normalized.includes('rerank')) return 'rerank';
    return null;
  };

  const handleDetectModels = async (stage: StageKey) => {
    const current = stageConfigs[stage];
    setStageConfigField(stage, 'detectLoading', true);
    setStageConfigField(stage, 'error', '');
    setAdminError('');
    setAdminStatus('');
    try {
      const response = await fetch(`${kernelBaseUrl}/api/admin/detect-models`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ api_base: current.apiBase, api_key: current.apiKey })
      });
      const payload = (await response.json()) as { models?: AdminModel[]; raw_count?: number; detail?: unknown };
      if (!response.ok) {
        throw new Error(parseAdminError(payload).message);
      }
      const detected = Array.isArray(payload.models) ? payload.models : [];
      const firstModel = current.model || detected[0]?.id || '';
      setStageConfigs((prev) => ({
        ...prev,
        [stage]: {
          ...prev[stage],
          models: detected,
          model: firstModel,
          error: ''
        }
      }));
      setAdminStatus(`${stage} 连接成功，已获取 ${detected.length} 个模型`);
    } catch (error) {
      const message = error instanceof Error ? error.message : '探测失败';
      setStageConfigs((prev) => ({
        ...prev,
        [stage]: {
          ...prev[stage],
          models: [],
          model: '',
          error: message
        }
      }));
    } finally {
      setStageConfigField(stage, 'detectLoading', false);
    }
  };

  const handleSaveConfig = async () => {
    for (const stage of stageOptions) {
      const current = stageConfigs[stage.key];
      if (!current.provider.trim() || !current.apiBase.trim() || !current.apiKey.trim() || !current.model.trim()) {
        setAdminError(`请先补全 ${stage.key} 的 provider/api_base/api_key/model`);
        return;
      }
    }
    setSaveLoading(true);
    setAdminError('');
    setAdminStatus('');
    setStageConfigs((prev) => ({
      answer: { ...prev.answer, error: '' },
      embedding: { ...prev.embedding, error: '' },
      rerank: { ...prev.rerank, error: '' }
    }));
    try {
      const answer = stageConfigs.answer;
      const embedding = stageConfigs.embedding;
      const rerank = stageConfigs.rerank;
      const response = await fetch(`${kernelBaseUrl}/api/admin/llm-config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          answer: {
            provider: answer.provider.trim(),
            api_base: answer.apiBase.trim(),
            api_key: answer.apiKey.trim(),
            model: answer.model.trim()
          },
          embedding: {
            provider: embedding.provider.trim(),
            api_base: embedding.apiBase.trim(),
            api_key: embedding.apiKey.trim(),
            model: embedding.model.trim()
          },
          rerank: {
            provider: rerank.provider.trim(),
            api_base: rerank.apiBase.trim(),
            api_key: rerank.apiKey.trim(),
            model: rerank.model.trim()
          }
        })
      });
      const payload = (await response.json()) as { detail?: unknown };
      if (!response.ok) {
        const parsed = parseAdminError(payload);
        const stage = parsed.stage ?? findStageInMessage(parsed.message);
        if (stage) {
          setStageConfigField(stage, 'error', parsed.message);
        } else {
          setAdminError(parsed.message);
        }
        return;
      }
      setAdminStatus('三路配置已保存，刷新后将回显最新持久化结果');
    } catch (error) {
      const message = error instanceof Error ? error.message : '保存失败';
      setAdminError(message);
    } finally {
      setSaveLoading(false);
    }
  };

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
        return;
      }

      if (payload.type === 'error') {
        setMessages((prev) => [
          ...prev,
          {
            id: crypto.randomUUID(),
            traceId: payload.traceId,
            role: 'assistant',
            content: `Error ${payload.code}: ${payload.message}`,
            mode,
            status: 'error',
            sources: []
          }
        ]);
      }
    };

    return () => {
      ws.close();
    };
  }, [mode, wsUrl]);

  useEffect(() => {
    let mounted = true;
    const loadSavedConfig = async () => {
      try {
        const response = await fetch(`${kernelBaseUrl}/api/admin/llm-config`);
        const payload = (await response.json()) as {
          configured?: boolean;
          answer?: { provider?: string; api_base?: string; model?: string };
          embedding?: { provider?: string; api_base?: string; model?: string };
          rerank?: { provider?: string; api_base?: string; model?: string };
          api_base?: string;
          model?: string;
        };
        if (!response.ok || !mounted || !payload.configured) {
          return;
        }
        setStageConfigs((prev) => {
          const next = { ...prev };
          for (const stage of stageOptions) {
            const stagePayload = payload[stage.key];
            const fallbackApiBase = typeof payload.api_base === 'string' ? payload.api_base : '';
            const fallbackModel = typeof payload.model === 'string' ? payload.model : '';
            const apiBase = stagePayload?.api_base || fallbackApiBase;
            const model = stagePayload?.model || fallbackModel;
            const provider = stagePayload?.provider || prev[stage.key].provider;
            const modelList = model
              ? prev[stage.key].models.some((item) => item.id === model)
                ? prev[stage.key].models
                : [...prev[stage.key].models, { id: model }]
              : prev[stage.key].models;
            next[stage.key] = {
              ...prev[stage.key],
              provider,
              apiBase: apiBase || prev[stage.key].apiBase,
              model,
              models: modelList
            };
          }
          return next;
        });
      } catch {
        // Keep silent to avoid blocking chat experience when admin endpoint is unavailable.
      }
    };
    void loadSavedConfig();
    return () => {
      mounted = false;
    };
  }, [kernelBaseUrl]);

  useEffect(() => {
    messageBottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages]);

  const handleSend = () => {
    if (!canSend || !wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      return;
    }
    const query = input.trim();
    const userMessage: ChatMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      content: query,
      mode,
      status: 'done'
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput('');

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

  return (
    <section className="mx-auto flex min-h-screen w-full max-w-5xl flex-col px-4 py-6 md:px-8">
      <header className="rounded-2xl border border-black/10 bg-white/75 p-4 shadow-sm backdrop-blur">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-xl font-semibold tracking-tight">Chat Workspace</h1>
            <p className="mt-1 text-sm text-black/70">Live WebSocket chat with source tracing and citation mapping.</p>
          </div>
          <span className="rounded-full border border-black/15 bg-white px-3 py-1 text-xs">{statusText}</span>
        </div>
      </header>

      <div className="mt-4 flex flex-wrap gap-2">
        {modeOptions.map((option) => (
          <button
            key={option.key}
            type="button"
            onClick={() => setMode(option.key)}
            className={`rounded-full border px-3 py-1.5 text-xs font-medium uppercase tracking-wide ${
              mode === option.key
                ? 'border-accent bg-accent text-white'
                : 'border-black/20 bg-white/80 text-black/70 hover:border-black/40'
            }`}
          >
            {option.label}
          </button>
        ))}

        <div className="ml-auto flex gap-2">
          {viewModes.map((option) => (
            <button
              key={option.key}
              type="button"
              onClick={() => setViewMode(option.key)}
              className={`rounded-full border px-3 py-1.5 text-xs font-medium ${
                viewMode === option.key
                  ? 'border-ink bg-ink text-white'
                  : 'border-black/20 bg-white/80 text-black/70'
              }`}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      <section className="mt-4 rounded-2xl border border-black/10 bg-white/80 p-4 shadow-sm backdrop-blur">
        <h2 className="text-sm font-semibold uppercase tracking-[0.12em] text-black/70">LLM Connection Settings</h2>
        <div className="mt-3 grid gap-3">
          {stageOptions.map((stage) => {
            const current = stageConfigs[stage.key];
            return (
              <div key={stage.key} className="rounded-xl border border-black/10 bg-white p-3">
                <div className="mb-2 flex items-center justify-between">
                  <h3 className="text-xs font-semibold uppercase tracking-[0.12em] text-black/70">{stage.label}</h3>
                  <button
                    data-testid={`llm-${stage.key}-detect-btn`}
                    type="button"
                    onClick={() => void handleDetectModels(stage.key)}
                    disabled={current.detectLoading || !current.apiBase.trim() || !current.apiKey.trim()}
                    className="rounded-lg bg-accent px-3 py-1.5 text-xs font-medium text-white disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {current.detectLoading ? 'Testing...' : '测试连接并获取模型'}
                  </button>
                </div>
                <div className="grid gap-3 md:grid-cols-2">
                  <label className="text-xs text-black/70">
                    Provider
                    <input
                      data-testid={`llm-${stage.key}-provider-input`}
                      value={current.provider}
                      onChange={(event) => setStageConfigField(stage.key, 'provider', event.target.value)}
                      placeholder={stage.defaultProvider}
                      className="mt-1 h-10 w-full rounded-lg border border-black/15 bg-white px-3 text-sm outline-none ring-accent transition focus:ring-2"
                    />
                  </label>
                  <label className="text-xs text-black/70">
                    API Base
                    <input
                      data-testid={`llm-${stage.key}-api-base-input`}
                      value={current.apiBase}
                      onChange={(event) => setStageConfigField(stage.key, 'apiBase', event.target.value)}
                      placeholder={stage.defaultApiBase}
                      className="mt-1 h-10 w-full rounded-lg border border-black/15 bg-white px-3 text-sm outline-none ring-accent transition focus:ring-2"
                    />
                  </label>
                  <label className="text-xs text-black/70">
                    API Key
                    <input
                      data-testid={`llm-${stage.key}-api-key-input`}
                      type="password"
                      value={current.apiKey}
                      onChange={(event) => setStageConfigField(stage.key, 'apiKey', event.target.value)}
                      placeholder="sk-..."
                      className="mt-1 h-10 w-full rounded-lg border border-black/15 bg-white px-3 text-sm outline-none ring-accent transition focus:ring-2"
                    />
                  </label>
                  <label className="text-xs text-black/70">
                    Model
                    <select
                      data-testid={`llm-${stage.key}-model-select`}
                      value={current.model}
                      onChange={(event) => setStageConfigField(stage.key, 'model', event.target.value)}
                      className="mt-1 h-10 w-full rounded-lg border border-black/15 bg-white px-3 text-xs"
                    >
                      <option value="">请选择模型</option>
                      {current.models.map((item) => (
                        <option key={`${stage.key}-${item.id}`} value={item.id}>
                          {item.id}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
                {current.error ? <p className="mt-2 text-xs text-red-700">{current.error}</p> : null}
              </div>
            );
          })}
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          <button
            data-testid="llm-save-btn"
            type="button"
            onClick={() => void handleSaveConfig()}
            disabled={saveLoading}
            className="rounded-lg bg-ink px-4 py-2 text-xs font-medium text-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            {saveLoading ? 'Saving...' : '保存三路配置'}
          </button>
        </div>
        {adminStatus ? <p className="mt-2 text-xs text-emerald-700">{adminStatus}</p> : null}
        {adminError ? <p className="mt-2 text-xs text-red-700">{adminError}</p> : null}
      </section>

      <div className="mt-4 flex-1 overflow-hidden rounded-2xl border border-black/10 bg-white/70 p-4 shadow-sm backdrop-blur">
        <div className="h-[52vh] space-y-3 overflow-y-auto pr-2">
          {messages.length === 0 ? (
            <p className="text-sm text-black/55">No messages yet. Ask your first question.</p>
          ) : (
            messages.map((message) => {
              const citationTokens = parseCitations(message.content);
              const graph = buildGraphSubgraph(message.sources ?? []);
              const showGraphPanel =
                (message.sources ?? []).some((source) => source.source_type === 'graph') || viewMode === 'developer';
              return (
                <article
                  key={message.id}
                  className={`max-w-[90%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${
                    message.role === 'user'
                      ? 'ml-auto bg-ink text-white'
                      : 'border border-black/10 bg-white text-black/90'
                  }`}
                >
                  <div className="mb-1 flex items-center gap-2 text-[10px] uppercase tracking-[0.14em] opacity-70">
                    <span>{message.role}</span>
                    {message.mode ? <span>({message.mode})</span> : null}
                    {message.status === 'streaming' ? <span>streaming</span> : null}
                  </div>

                  <div className="whitespace-pre-wrap break-words">
                    {citationTokens.map((token, index) => {
                      if (!token.citationNumber) {
                        return <span key={`${message.id}-t-${index}`}>{token.label}</span>;
                      }

                      return (
                        <button
                          key={`${message.id}-c-${index}`}
                          type="button"
                          onClick={() => setSelectedCitation(token.citationNumber ?? null)}
                          className="mx-0.5 rounded border border-accent/40 bg-accent/10 px-1 text-xs text-accentDark"
                        >
                          {token.label}
                        </button>
                      );
                    })}
                  </div>

                  {message.sources && message.sources.length > 0 ? (
                    <div className="mt-3 space-y-2 border-t border-black/10 pt-2">
                      <div className="text-[11px] uppercase tracking-[0.14em] text-black/60">Sources</div>
                      {message.sources.map((source, index) => {
                        const isSelected = selectedCitation === index + 1;
                        return (
                          <button
                            key={`${message.id}-s-${source.source_id}`}
                            type="button"
                            onClick={() => setSelectedCitation(index + 1)}
                            className={`block w-full rounded-lg border px-3 py-2 text-left ${
                              isSelected ? 'border-accent bg-accent/10' : 'border-black/10 bg-white'
                            }`}
                          >
                            <div className="text-xs font-medium">
                              [{index + 1}] {source.title}
                            </div>
                            <div className="mt-1 text-xs text-black/70">{source.snippet}</div>
                            <div className="mt-1 text-[10px] uppercase tracking-[0.12em] text-black/50">
                              {source.source_type} · {source.locator} · score {source.score.toFixed(3)}
                            </div>
                          </button>
                        );
                      })}
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

                  {viewMode === 'developer' && message.traceId ? (
                    <pre className="mt-2 overflow-x-auto rounded bg-black/90 p-2 text-[10px] text-green-300">
                      {JSON.stringify(
                        {
                          traceId: message.traceId,
                          mode: message.mode,
                          status: message.status,
                          sourceCount: message.sources?.length ?? 0
                        },
                        null,
                        2
                      )}
                    </pre>
                  ) : null}
                </article>
              );
            })
          )}
          <div ref={messageBottomRef} />
        </div>
      </div>

      <footer className="mt-4 rounded-2xl border border-black/10 bg-white/80 p-3 shadow-sm backdrop-blur">
        <label className="mb-2 block text-xs uppercase tracking-[0.14em] text-black/60">
          Message input ({mode} mode)
        </label>
        <div className="flex gap-2">
          <input
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                handleSend();
              }
            }}
            placeholder="Ask a question..."
            className="h-11 w-full rounded-lg border border-black/15 bg-white px-3 text-sm outline-none ring-accent transition focus:ring-2"
          />
          <button
            type="button"
            onClick={handleSend}
            disabled={!canSend || statusText !== 'Connected'}
            className="h-11 rounded-lg bg-accent px-4 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            Send
          </button>
        </div>
      </footer>
    </section>
  );
}
