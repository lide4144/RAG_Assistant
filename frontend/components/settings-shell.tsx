'use client';

import { Eye, EyeOff, Sparkles } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { toast } from 'sonner';
import { fetchAdminJson } from '../lib/admin-http';
import { resolveAdminUrl } from '../lib/deployment-endpoints';
import type { MarkerLlmRuntimeConfig, MarkerTuning, RuntimeOverview, RuntimeSource } from '../lib/types';

type AdminModel = { id: string; owned_by?: string | null };
type StageKey = 'answer' | 'embedding' | 'rerank' | 'rewrite' | 'graph_entity';

type StageConfig = {
  provider: string;
  apiBase: string;
  apiKey: string;
  model: string;
  models: AdminModel[];
  detectLoading: boolean;
  error: string;
  showApiKey: boolean;
};

type ParsedAdminError = {
  message: string;
  code?: string;
  stage?: StageKey;
};

type DraftConfig = Pick<StageConfig, 'provider' | 'apiBase' | 'apiKey' | 'model'>;
type DraftPayload = Record<StageKey, DraftConfig>;
type OverridePayload = Record<StageKey, boolean>;
type MarkerLlmField =
  | 'use_llm'
  | 'llm_service'
  | 'gemini_api_key'
  | 'vertex_project_id'
  | 'ollama_base_url'
  | 'ollama_model'
  | 'claude_api_key'
  | 'claude_model_name'
  | 'openai_api_key'
  | 'openai_model'
  | 'openai_base_url'
  | 'azure_endpoint'
  | 'azure_api_key'
  | 'deployment_name';
type MarkerLlmForm = {
  use_llm: boolean;
  llm_service: string;
  gemini_api_key: string;
  vertex_project_id: string;
  ollama_base_url: string;
  ollama_model: string;
  claude_api_key: string;
  claude_model_name: string;
  openai_api_key: string;
  openai_model: string;
  openai_base_url: string;
  azure_endpoint: string;
  azure_api_key: string;
  deployment_name: string;
};
type PipelineConfigPayload = {
  configured?: boolean;
  saved?: { marker_tuning?: MarkerTuning; marker_llm?: MarkerLlmForm };
  effective?: { marker_tuning?: MarkerTuning; marker_llm?: MarkerLlmForm };
  effective_source?: {
    marker_tuning?: Partial<Record<keyof MarkerTuning, RuntimeSource>>;
    marker_llm?: Partial<Record<MarkerLlmField, RuntimeSource>>;
  };
};

type ProviderPreset = {
  label: string;
  apiBase: string;
};

type StageMeta = {
  key: StageKey;
  title: string;
  defaultProvider: string;
  defaultApiBase: string;
  defaultModel: string;
};

const providerPresets: Record<string, ProviderPreset> = {
  openai: { label: 'OpenAI', apiBase: 'https://api.openai.com/v1' },
  azure: { label: 'Azure OpenAI', apiBase: 'https://YOUR-RESOURCE.openai.azure.com/openai/deployments/YOUR-DEPLOYMENT' },
  siliconflow: { label: 'SiliconFlow', apiBase: 'https://api.siliconflow.cn/v1' },
  ollama: { label: 'Ollama', apiBase: 'http://127.0.0.1:11434/v1' },
  vllm: { label: 'vLLM', apiBase: 'http://127.0.0.1:8000/v1' }
};

const stageMeta: StageMeta[] = [
  { key: 'answer', title: 'Answer 模型', defaultProvider: 'openai', defaultApiBase: 'https://api.openai.com/v1', defaultModel: '' },
  {
    key: 'embedding',
    title: 'Embedding 模型',
    defaultProvider: 'ollama',
    defaultApiBase: 'http://127.0.0.1:11434/v1',
    defaultModel: 'BAAI/bge-small-zh-v1.5'
  },
  {
    key: 'rerank',
    title: 'Rerank 模型',
    defaultProvider: 'ollama',
    defaultApiBase: 'http://127.0.0.1:11434/v1',
    defaultModel: 'BAAI/bge-reranker-base'
  },
  {
    key: 'rewrite',
    title: 'Rewrite 模型',
    defaultProvider: 'ollama',
    defaultApiBase: 'http://127.0.0.1:11434/v1',
    defaultModel: 'Qwen2.5-3B-Instruct'
  },
  {
    key: 'graph_entity',
    title: 'Graph Entity 模型',
    defaultProvider: 'siliconflow',
    defaultApiBase: 'https://api.siliconflow.cn/v1',
    defaultModel: 'Pro/deepseek-ai/DeepSeek-V3.2'
  }
];

const initialConfigs: Record<StageKey, StageConfig> = stageMeta.reduce(
  (acc, stage) => ({
    ...acc,
    [stage.key]: {
      provider: stage.defaultProvider,
      apiBase: stage.defaultApiBase,
      apiKey: '',
      model: stage.defaultModel,
      models: stage.defaultModel ? [{ id: stage.defaultModel }] : [],
      detectLoading: false,
      error: '',
      showApiKey: false
    }
  }),
  {} as Record<StageKey, StageConfig>
);
const inheritableStages = new Set<StageKey>(['rewrite', 'graph_entity']);
const initialOverrides = stageMeta.reduce(
  (acc, stage) => ({ ...acc, [stage.key]: false }),
  {} as OverridePayload
);

const defaultMarkerTuning: MarkerTuning = {
  recognition_batch_size: 2,
  detector_batch_size: 2,
  layout_batch_size: 2,
  ocr_error_batch_size: 1,
  table_rec_batch_size: 1,
  model_dtype: 'float16'
};

const marker8GbSafePreset: MarkerTuning = {
  recognition_batch_size: 1,
  detector_batch_size: 1,
  layout_batch_size: 1,
  ocr_error_batch_size: 1,
  table_rec_batch_size: 1,
  model_dtype: 'float16'
};

const defaultMarkerLlm: MarkerLlmForm = {
  use_llm: false,
  llm_service: 'gemini',
  gemini_api_key: '',
  vertex_project_id: '',
  ollama_base_url: 'http://127.0.0.1:11434',
  ollama_model: '',
  claude_api_key: '',
  claude_model_name: '',
  openai_api_key: '',
  openai_model: '',
  openai_base_url: 'https://api.openai.com/v1',
  azure_endpoint: '',
  azure_api_key: '',
  deployment_name: ''
};

const markerLlmServiceOptions = [
  { value: 'gemini', label: 'Gemini' },
  { value: 'marker.services.vertex.GoogleVertexService', label: 'Google Vertex' },
  { value: 'marker.services.ollama.OllamaService', label: 'Ollama' },
  { value: 'marker.services.claude.ClaudeService', label: 'Claude' },
  { value: 'marker.services.openai.OpenAIService', label: 'OpenAI' },
  { value: 'marker.services.azure_openai.AzureOpenAIService', label: 'Azure OpenAI' }
];

const markerLlmFieldMeta: Record<
  Exclude<MarkerLlmField, 'use_llm' | 'llm_service'>,
  { label: string; placeholder?: string; secret?: boolean; type?: 'text' | 'password' }
> = {
  gemini_api_key: { label: 'Gemini API Key', placeholder: 'AIza...', secret: true, type: 'password' },
  vertex_project_id: { label: 'Vertex Project ID', placeholder: 'your-gcp-project' },
  ollama_base_url: { label: 'Ollama Base URL', placeholder: 'http://127.0.0.1:11434' },
  ollama_model: { label: 'Ollama Model', placeholder: 'qwen2.5:7b' },
  claude_api_key: { label: 'Claude API Key', placeholder: 'sk-ant-...', secret: true, type: 'password' },
  claude_model_name: { label: 'Claude Model', placeholder: 'claude-3-7-sonnet-20250219' },
  openai_api_key: { label: 'OpenAI API Key', placeholder: 'sk-...', secret: true, type: 'password' },
  openai_model: { label: 'OpenAI Model', placeholder: 'gpt-4.1-mini' },
  openai_base_url: { label: 'OpenAI Base URL', placeholder: 'https://api.openai.com/v1' },
  azure_endpoint: { label: 'Azure Endpoint', placeholder: 'https://resource.openai.azure.com' },
  azure_api_key: { label: 'Azure API Key', placeholder: 'azure-key', secret: true, type: 'password' },
  deployment_name: { label: 'Deployment Name', placeholder: 'gpt-4o-mini' }
};

const markerLlmFieldOrder: Record<string, Array<Exclude<MarkerLlmField, 'use_llm' | 'llm_service'>>> = {
  gemini: ['gemini_api_key'],
  'marker.services.vertex.GoogleVertexService': ['vertex_project_id'],
  'marker.services.ollama.OllamaService': ['ollama_base_url', 'ollama_model'],
  'marker.services.claude.ClaudeService': ['claude_api_key', 'claude_model_name'],
  'marker.services.openai.OpenAIService': ['openai_api_key', 'openai_model', 'openai_base_url'],
  'marker.services.azure_openai.AzureOpenAIService': ['azure_endpoint', 'azure_api_key', 'deployment_name']
};

export function SettingsShell() {
  const draftStorageKey = 'settings-shell-draft-v2';
  const [configs, setConfigs] = useState<Record<StageKey, StageConfig>>(initialConfigs);
  const [overrides, setOverrides] = useState<OverridePayload>(initialOverrides);
  const [saveLoading, setSaveLoading] = useState(false);
  const [statusText, setStatusText] = useState('');
  const [globalError, setGlobalError] = useState('');
  const [draftHydrated, setDraftHydrated] = useState(false);
  const [persistedDraft, setPersistedDraft] = useState<DraftPayload>(toDraftPayload(initialConfigs));
  const [markerTuning, setMarkerTuning] = useState<MarkerTuning>(defaultMarkerTuning);
  const [markerFieldErrors, setMarkerFieldErrors] = useState<Partial<Record<keyof MarkerTuning, string>>>({});
  const [markerLlm, setMarkerLlm] = useState<MarkerLlmForm>(defaultMarkerLlm);
  const [markerLlmFieldErrors, setMarkerLlmFieldErrors] = useState<Partial<Record<MarkerLlmField, string>>>({});
  const [markerLlmShowSecrets, setMarkerLlmShowSecrets] = useState<Partial<Record<MarkerLlmField, boolean>>>({});
  const [markerOpenAiModels, setMarkerOpenAiModels] = useState<AdminModel[]>([]);
  const [markerOpenAiDetectLoading, setMarkerOpenAiDetectLoading] = useState(false);
  const [pipelineSaveLoading, setPipelineSaveLoading] = useState(false);
  const [pipelineStatusText, setPipelineStatusText] = useState('');
  const [pipelineGlobalError, setPipelineGlobalError] = useState('');
  const [pipelineConfig, setPipelineConfig] = useState<PipelineConfigPayload | null>(null);
  const [runtimeOverview, setRuntimeOverview] = useState<RuntimeOverview | null>(null);
  const llmConfigUrl = useMemo(() => resolveAdminUrl('/api/admin/llm-config'), []);
  const detectModelsUrl = useMemo(() => resolveAdminUrl('/api/admin/detect-models'), []);
  const pipelineConfigUrl = useMemo(() => resolveAdminUrl('/api/admin/pipeline-config'), []);
  const runtimeOverviewUrl = useMemo(() => resolveAdminUrl('/api/admin/runtime-overview'), []);
  const controlsDisabled = !draftHydrated;
  const visibleMarkerLlmFields = markerLlm.use_llm ? markerLlmFieldOrder[markerLlm.llm_service] ?? [] : [];

  const providerOptions = useMemo(
    () => Object.entries(providerPresets).map(([value, item]) => ({ value, label: item.label })),
    []
  );

  const setField = <K extends keyof StageConfig>(stage: StageKey, field: K, value: StageConfig[K]) => {
    setConfigs((prev) => ({ ...prev, [stage]: { ...prev[stage], [field]: value } }));
  };

  const setMarkerField = <K extends keyof MarkerTuning>(field: K, value: MarkerTuning[K]) => {
    setMarkerTuning((prev) => ({ ...prev, [field]: value }));
    setMarkerFieldErrors((prev) => ({ ...prev, [field]: '' }));
  };

  const setMarkerLlmField = <K extends MarkerLlmField>(field: K, value: MarkerLlmForm[K]) => {
    setMarkerLlm((prev) => ({ ...prev, [field]: value }));
    setMarkerLlmFieldErrors((prev) => ({ ...prev, [field]: '' }));
  };

  const mergeDetectedModels = (detected: AdminModel[], currentModel: string): AdminModel[] => {
    if (currentModel && !detected.some((item) => item.id === currentModel)) {
      return [{ id: currentModel }, ...detected];
    }
    return detected;
  };

  const parseAdminError = (payload: unknown): ParsedAdminError => {
    if (!payload || typeof payload !== 'object') {
      return { message: '请求失败' };
    }
    const detail = (payload as { detail?: unknown }).detail;
    if (detail && typeof detail === 'object') {
      const maybeCode = (detail as { code?: unknown }).code;
      const maybeMessage = (detail as { message?: unknown }).message;
      const maybeStage = (detail as { stage?: unknown }).stage;
      const code = typeof maybeCode === 'string' && maybeCode ? maybeCode : undefined;
      const messageText = typeof maybeMessage === 'string' && maybeMessage ? maybeMessage : '请求失败';
      const stage = stageMeta.some((item) => item.key === maybeStage) ? (maybeStage as StageKey) : undefined;
      return { message: messageText, code, stage };
    }
    return { message: '请求失败' };
  };

  const withBackendDetail = (prefix: string, detail: string): string => {
    const text = detail.trim();
    if (!text) {
      return prefix;
    }
    return `${prefix}（后端信息：${text}）`;
  };

  const mapAdminErrorToGuidance = (parsed: ParsedAdminError, action: 'detect' | 'save'): string => {
    const code = parsed.code?.toUpperCase() ?? '';
    const message = parsed.message || '请求失败';
    if (code === 'AUTH_FAILED') {
      return withBackendDetail('认证失败：请检查 API Key 是否正确、是否过期，并确认 API Base 与服务商一致。', message);
    }
    if (code === 'INVALID_PARAMS' && /model|模型/i.test(message)) {
      return withBackendDetail('模型不能为空：请先点击“测试连接”，然后从下拉框选择可用模型。', message);
    }
    if (code === 'MODEL_REQUIRED' || code === 'EMPTY_MODEL') {
      return withBackendDetail('模型不能为空：请先点击“测试连接”，然后从下拉框选择可用模型。', message);
    }
    if (code === 'NETWORK_ERROR' || code === 'UPSTREAM_UNREACHABLE' || code === 'TIMEOUT') {
      return withBackendDetail('网络异常：请检查 API Base 连通性、代理与防火墙配置后重试。', message);
    }
    if (action === 'detect' && /no model|empty|未检测到模型|models?\s*0/i.test(message)) {
      return withBackendDetail('未检测到可用模型：请确认 API Base/API Key 权限并重试。', message);
    }
    if (code === 'INVALID_PARAMS') {
      return withBackendDetail('参数校验失败：请检查 provider、API Base、API Key 与模型配置。', message);
    }
    return withBackendDetail('请求失败：请检查输入并重试。', `${code ? `[${code}] ` : ''}${message}`);
  };

  const networkErrorMessage = (action: 'detect' | 'save') =>
    action === 'detect'
      ? '网络请求失败：请确认模型服务可达后重试连接测试。'
      : '网络请求失败：请确认内核服务在线后重试保存。';

  const draftsEqual = (a: DraftPayload, b: DraftPayload): boolean => JSON.stringify(a) === JSON.stringify(b);
  const isInheritMode = (stage: StageKey) => inheritableStages.has(stage) && !overrides[stage];
  const dirtyFieldsByStage = useMemo(() => {
    const current = toDraftPayload(configs);
    const result: Record<StageKey, Partial<Record<keyof DraftConfig, boolean>>> = {
      answer: {},
      embedding: {},
      rerank: {},
      rewrite: {},
      graph_entity: {}
    };
    for (const stage of stageMeta) {
      result[stage.key] = {
        provider: current[stage.key].provider !== persistedDraft[stage.key].provider,
        apiBase: current[stage.key].apiBase !== persistedDraft[stage.key].apiBase,
        apiKey: current[stage.key].apiKey !== persistedDraft[stage.key].apiKey,
        model: current[stage.key].model !== persistedDraft[stage.key].model
      };
    }
    return result;
  }, [configs, persistedDraft]);

  const applyDraftConfig = (source: Record<StageKey, StageConfig>): Record<StageKey, StageConfig> => {
    try {
      const cached = sessionStorage.getItem(draftStorageKey);
      if (!cached) {
        return source;
      }
      const parsed = JSON.parse(cached) as Partial<Record<StageKey, Partial<DraftConfig>>>;
      const next = { ...source };
      for (const stage of stageMeta) {
        const draft = parsed[stage.key];
        if (!draft || typeof draft !== 'object') {
          continue;
        }
        next[stage.key] = {
          ...next[stage.key],
          provider: typeof draft.provider === 'string' ? draft.provider : next[stage.key].provider,
          apiBase: typeof draft.apiBase === 'string' ? draft.apiBase : next[stage.key].apiBase,
          apiKey: typeof draft.apiKey === 'string' ? draft.apiKey : next[stage.key].apiKey,
          model: typeof draft.model === 'string' ? draft.model : next[stage.key].model
        };
      }
      return next;
    } catch {
      return source;
    }
  };

  useEffect(() => {
    let mounted = true;
    const loadSavedConfig = async () => {
      try {
        const result = await fetchAdminJson<{
          configured?: boolean;
          answer?: { provider?: string; api_base?: string; model?: string };
          embedding?: { provider?: string; api_base?: string; model?: string };
          rerank?: { provider?: string; api_base?: string; model?: string };
          rewrite?: { provider?: string; api_base?: string; model?: string };
          graph_entity?: { provider?: string; api_base?: string; model?: string };
          api_base?: string;
          model?: string;
        }>(llmConfigUrl);
        if (!result.ok || !mounted || !result.data.configured) {
          if (mounted) {
            const merged = applyDraftConfig(initialConfigs);
            setConfigs(merged);
            setPersistedDraft(toDraftPayload(merged));
          }
          return;
        }
        const payload = result.data;
        let loadedDraft: DraftPayload | null = null;
        setConfigs((prev) => {
          const next = { ...prev };
          for (const stage of stageMeta) {
            const stagePayload = payload[stage.key];
            const fallbackApiBase = typeof payload.api_base === 'string' ? payload.api_base : '';
            const fallbackModel = typeof payload.model === 'string' ? payload.model : '';
            const provider = stagePayload?.provider || prev[stage.key].provider;
            const apiBase = stagePayload?.api_base || fallbackApiBase || prev[stage.key].apiBase;
            const model = stagePayload?.model || fallbackModel || prev[stage.key].model;
            const models = model
              ? prev[stage.key].models.some((item) => item.id === model)
                ? prev[stage.key].models
                : [...prev[stage.key].models, { id: model }]
              : prev[stage.key].models;
            next[stage.key] = {
              ...prev[stage.key],
              provider,
              apiBase,
              model,
              models
            };
          }
          const merged = applyDraftConfig(next);
          loadedDraft = toDraftPayload(merged);
          return merged;
        });
        if (loadedDraft) {
          setPersistedDraft(loadedDraft);
        }
      } catch {
        if (mounted) {
          const merged = applyDraftConfig(initialConfigs);
          setConfigs(merged);
          setPersistedDraft(toDraftPayload(merged));
        }
      } finally {
        if (mounted) {
          setDraftHydrated(true);
        }
      }
    };
    void loadSavedConfig();
    return () => {
      mounted = false;
    };
  }, [llmConfigUrl]);

  useEffect(() => {
    let mounted = true;
    const loadRuntimePanels = async () => {
      try {
        const [pipelineResult, overviewResult] = await Promise.all([
          fetchAdminJson<PipelineConfigPayload>(pipelineConfigUrl),
          fetchAdminJson<RuntimeOverview>(runtimeOverviewUrl)
        ]);
        if (!mounted) {
          return;
        }
        if (pipelineResult.ok) {
          setPipelineConfig(pipelineResult.data);
          if (pipelineResult.data.saved?.marker_tuning) {
            setMarkerTuning(pipelineResult.data.saved.marker_tuning);
          }
          if (pipelineResult.data.saved?.marker_llm) {
            const nextMarkerLlm = { ...defaultMarkerLlm, ...pipelineResult.data.saved.marker_llm };
            setMarkerOpenAiModels(mergeDetectedModels([], nextMarkerLlm.openai_model));
            for (const [field, meta] of Object.entries(markerLlmFieldMeta)) {
              if (meta.secret) {
                nextMarkerLlm[field as keyof MarkerLlmForm] = '' as never;
              }
            }
            setMarkerLlm(nextMarkerLlm);
          } else {
            setMarkerOpenAiModels(mergeDetectedModels([], defaultMarkerLlm.openai_model));
          }
        }
        if (overviewResult.ok) {
          setRuntimeOverview(overviewResult.data);
        }
        if (!pipelineResult.ok && !overviewResult.ok) {
          setPipelineGlobalError('运行态概览加载失败，请稍后重试。');
        }
      } catch {
        if (mounted) {
          setPipelineGlobalError('运行态概览加载失败，请稍后重试。');
        }
      }
    };
    void loadRuntimePanels();
    return () => {
      mounted = false;
    };
  }, [pipelineConfigUrl, runtimeOverviewUrl]);

  useEffect(() => {
    if (!draftHydrated) {
      return;
    }
    const payload = toDraftPayload(configs);
    sessionStorage.setItem(draftStorageKey, JSON.stringify(payload));
  }, [configs, draftHydrated]);

  const isDirty = useMemo(() => !draftsEqual(toDraftPayload(configs), persistedDraft), [configs, persistedDraft]);

  useEffect(() => {
    if (!isDirty) {
      return;
    }
    const onBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', onBeforeUnload);
    return () => window.removeEventListener('beforeunload', onBeforeUnload);
  }, [isDirty]);

  useEffect(() => {
    if (!isDirty) {
      return;
    }
    const onDocumentClick = (event: MouseEvent) => {
      const target = event.target as HTMLElement | null;
      const anchor = target?.closest('a[href]') as HTMLAnchorElement | null;
      if (!anchor) {
        return;
      }
      const href = anchor.getAttribute('href') ?? '';
      if (!href.startsWith('/')) {
        return;
      }
      const nextUrl = new URL(href, window.location.origin);
      if (nextUrl.pathname === window.location.pathname) {
        return;
      }
      const shouldLeave = window.confirm('当前模型配置尚未保存，确认离开当前页面吗？');
      if (!shouldLeave) {
        event.preventDefault();
        event.stopPropagation();
      }
    };
    document.addEventListener('click', onDocumentClick, true);
    return () => document.removeEventListener('click', onDocumentClick, true);
  }, [isDirty]);

  const handleProviderChange = (stage: StageKey, provider: string) => {
    const preset = providerPresets[provider];
    setConfigs((prev) => ({
      ...prev,
      [stage]: {
        ...prev[stage],
        provider,
        apiBase: preset?.apiBase ?? prev[stage].apiBase,
        error: ''
      }
    }));
  };

  const handleDetectModels = async (stage: StageKey) => {
    if (controlsDisabled) {
      return;
    }
    const current = configs[stage];
    const inherited = isInheritMode(stage);
    const apiBase = inherited ? configs.answer.apiBase : current.apiBase;
    const apiKey = inherited ? configs.answer.apiKey : current.apiKey;
    setField(stage, 'detectLoading', true);
    setField(stage, 'error', '');
    setGlobalError('');
    setStatusText('');
    try {
      const result = await fetchAdminJson<{ models?: AdminModel[]; detail?: unknown }>(detectModelsUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ api_base: apiBase, api_key: apiKey })
      });
      if (!result.ok) {
        if (!result.data) {
          throw new Error(result.message);
        }
        const parsed = parseAdminError(result.data);
        throw new Error(mapAdminErrorToGuidance(parsed, 'detect'));
      }
      const detected = Array.isArray(result.data.models) ? result.data.models : [];
      if (!detected.length) {
        const message = '未检测到可用模型：请确认 API Base/API Key 权限并重试。';
        setField(stage, 'error', message);
        toast.error(`${stage} 模型探测失败`);
        return;
      }
      setConfigs((prev) => ({
        ...prev,
        [stage]: {
          ...prev[stage],
          models:
            prev[stage].model && !detected.some((item) => item.id === prev[stage].model)
              ? [{ id: prev[stage].model }, ...detected]
              : detected,
          model: prev[stage].model || detected[0]?.id || '',
          error: ''
        }
      }));
      setStatusText(`${stage} 连接成功，已发现 ${detected.length} 个模型。`);
      toast.success(`${stage} 模型探测成功`);
    } catch (error) {
      const message =
        error instanceof TypeError
          ? networkErrorMessage('detect')
          : error instanceof Error
            ? error.message
            : '探测失败';
      setField(stage, 'error', message);
      toast.error(`${stage} 模型探测失败`);
    } finally {
      setField(stage, 'detectLoading', false);
    }
  };

  const handleSave = async () => {
    if (controlsDisabled) {
      return;
    }
    for (const stage of stageMeta) {
      const current = configs[stage.key];
      const inherited = isInheritMode(stage.key);
      const apiBase = inherited ? configs.answer.apiBase : current.apiBase;
      const apiKey = inherited ? configs.answer.apiKey : current.apiKey;
      if (!current.provider.trim() || !apiBase.trim() || !apiKey.trim() || !current.model.trim()) {
        setGlobalError(`请先补全 ${stage.title} 的 provider、API Base、API Key 和模型。`);
        return;
      }
    }

    setSaveLoading(true);
    setStatusText('');
    setGlobalError('');

    try {
      const result = await fetchAdminJson<{ detail?: unknown }>(llmConfigUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(
          stageMeta.reduce(
            (acc, stage) => ({
              ...acc,
              [stage.key]: {
                provider: configs[stage.key].provider.trim(),
                api_base: (isInheritMode(stage.key) ? configs.answer.apiBase : configs[stage.key].apiBase).trim(),
                api_key: (isInheritMode(stage.key) ? configs.answer.apiKey : configs[stage.key].apiKey).trim(),
                model: configs[stage.key].model.trim()
              }
            }),
            {}
          )
        )
      });

      if (!result.ok) {
        if (!result.data) {
          setGlobalError(result.message);
          toast.error('保存失败，请检查配置。');
          return;
        }
        const parsed = parseAdminError(result.data);
        const guidance = mapAdminErrorToGuidance(parsed, 'save');
        if (parsed.stage) {
          setField(parsed.stage, 'error', guidance);
        } else {
          setGlobalError(guidance);
        }
        toast.error('保存失败，请检查配置。');
        return;
      }

      setStatusText('配置已保存，聊天页面将自动读取最新连接状态。');
      setPersistedDraft(toDraftPayload(configs));
      toast.success('模型配置保存成功');
    } catch (error) {
      const message =
        error instanceof TypeError ? networkErrorMessage('save') : error instanceof Error ? error.message : '保存失败';
      setGlobalError(message);
      toast.error('保存失败，请稍后重试。');
    } finally {
      setSaveLoading(false);
    }
  };

  const handleSavePipeline = async () => {
    if (controlsDisabled) {
      return;
    }
    setPipelineSaveLoading(true);
    setPipelineStatusText('');
    setPipelineGlobalError('');
    setMarkerFieldErrors({});
    setMarkerLlmFieldErrors({});
    try {
      const result = await fetchAdminJson<{
        detail?: {
          field_errors?: Partial<Record<keyof MarkerTuning | MarkerLlmField, string>>;
          message?: string;
        };
      }>(
        pipelineConfigUrl,
        {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          marker_tuning: {
            recognition_batch_size: Number(markerTuning.recognition_batch_size),
            detector_batch_size: Number(markerTuning.detector_batch_size),
            layout_batch_size: Number(markerTuning.layout_batch_size),
            ocr_error_batch_size: Number(markerTuning.ocr_error_batch_size),
            table_rec_batch_size: Number(markerTuning.table_rec_batch_size),
            model_dtype: markerTuning.model_dtype
          },
          marker_llm: markerLlm
        })
        }
      );
      if (!result.ok) {
        const payload = result.data as {
          detail?: {
            field_errors?: Partial<Record<keyof MarkerTuning | MarkerLlmField, string>>;
            message?: string;
          };
        } | undefined;
        const fieldErrors = payload?.detail?.field_errors;
        if (fieldErrors && typeof fieldErrors === 'object') {
          const tuningErrors: Partial<Record<keyof MarkerTuning, string>> = {};
          const llmErrors: Partial<Record<MarkerLlmField, string>> = {};
          for (const [key, value] of Object.entries(fieldErrors)) {
            if (key in defaultMarkerTuning) {
              tuningErrors[key as keyof MarkerTuning] = value as string;
            } else {
              llmErrors[key as MarkerLlmField] = value as string;
            }
          }
          setMarkerFieldErrors(tuningErrors);
          setMarkerLlmFieldErrors(llmErrors);
        }
        setPipelineGlobalError(payload?.detail?.message || result.message || 'Marker tuning 保存失败');
        toast.error('Marker tuning 保存失败');
        return;
      }
      setPipelineStatusText('Marker Runtime 与 LLM service 配置已保存并生效。');
      toast.success('Marker tuning 保存成功');
      const [pipelineResult, overviewResult] = await Promise.all([
        fetchAdminJson<PipelineConfigPayload>(pipelineConfigUrl),
        fetchAdminJson<RuntimeOverview>(runtimeOverviewUrl)
      ]);
      if (pipelineResult.ok) {
        setPipelineConfig(pipelineResult.data);
      }
      if (overviewResult.ok) {
        setRuntimeOverview(overviewResult.data);
      }
    } catch {
      setPipelineGlobalError('网络请求失败：请确认内核服务在线后重试保存。');
      toast.error('Marker tuning 保存失败');
    } finally {
      setPipelineSaveLoading(false);
    }
  };

  const handleDetectMarkerOpenAiModels = async () => {
    if (controlsDisabled || markerOpenAiDetectLoading) {
      return;
    }
    const apiBase = markerLlm.openai_base_url.trim();
    const apiKey = markerLlm.openai_api_key.trim();
    if (!apiBase || !apiKey) {
      setMarkerLlmFieldErrors((prev) => ({
        ...prev,
        openai_api_key: apiKey ? '' : '请先填写 OpenAI API Key',
        openai_base_url: apiBase ? '' : '请先填写 OpenAI Base URL'
      }));
      setPipelineGlobalError('请先填写 OpenAI API Base 与 API Key，再测试 Marker OpenAI 连接。');
      return;
    }
    setMarkerOpenAiDetectLoading(true);
    setPipelineGlobalError('');
    setPipelineStatusText('');
    try {
      const result = await fetchAdminJson<{ models?: AdminModel[]; detail?: unknown }>(detectModelsUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ api_base: apiBase, api_key: apiKey })
      });
      if (!result.ok) {
        if (!result.data) {
          throw new Error(result.message);
        }
        const parsed = parseAdminError(result.data);
        throw new Error(mapAdminErrorToGuidance(parsed, 'detect'));
      }
      const detected = Array.isArray(result.data.models) ? result.data.models : [];
      if (!detected.length) {
        setMarkerLlmFieldErrors((prev) => ({
          ...prev,
          openai_model: '未检测到可用模型：请确认 API Base/API Key 权限并重试。'
        }));
        toast.error('Marker OpenAI 模型探测失败');
        return;
      }
      const nextModels = mergeDetectedModels(detected, markerLlm.openai_model);
      setMarkerOpenAiModels(nextModels);
      setMarkerLlm((prev) => ({
        ...prev,
        openai_model: prev.openai_model && nextModels.some((item) => item.id === prev.openai_model) ? prev.openai_model : detected[0]?.id || ''
      }));
      setMarkerLlmFieldErrors((prev) => ({ ...prev, openai_model: '', openai_api_key: '', openai_base_url: '' }));
      setPipelineStatusText(`Marker OpenAI 连接成功，已发现 ${detected.length} 个模型。`);
      toast.success('Marker OpenAI 模型探测成功');
    } catch (error) {
      const message =
        error instanceof TypeError
          ? networkErrorMessage('detect')
          : error instanceof Error
            ? error.message
            : '探测失败';
      setMarkerLlmFieldErrors((prev) => ({ ...prev, openai_model: message }));
      toast.error('Marker OpenAI 模型探测失败');
    } finally {
      setMarkerOpenAiDetectLoading(false);
    }
  };

  const apply8GbSafePreset = () => {
    if (controlsDisabled || pipelineSaveLoading) {
      return;
    }
    setMarkerTuning(marker8GbSafePreset);
    setMarkerFieldErrors({});
    setPipelineGlobalError('');
    setPipelineStatusText('已填充 8GB 安全档位，请保存使其生效。');
  };

  return (
    <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm md:p-6">
      <header className="mb-6">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">模型设置</p>
        <h2 className="mt-2 text-2xl font-semibold tracking-tight">统一配置 LLM 连接</h2>
        <p className="mt-2 text-sm text-slate-600">
          所有模型连接参数集中管理。Provider 选择后会自动填入推荐 API Base，支持全模型位点独立保存。
        </p>
        {!draftHydrated ? (
          <p data-testid="llm-loading-text" className="mt-2 text-xs text-slate-500">
            正在加载历史配置...
          </p>
        ) : (
          <p data-testid="llm-ready-text" className="mt-2 text-xs text-emerald-700">
            配置已加载
          </p>
        )}
      </header>

      <section className="mb-6 grid gap-4 xl:grid-cols-2">
        <article data-testid="runtime-overview-panel" className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">当前生效配置概览</p>
          <p className="mt-2 text-xs text-slate-600">
            状态等级: {runtimeOverview?.status.level ?? 'ERROR'}
            {runtimeOverview?.status.reasons?.[0] ? ` · ${runtimeOverview.status.reasons[0]}` : ''}
          </p>
          <div className="mt-3 space-y-1 text-xs text-slate-700">
            <p>
              Answer: {runtimeOverview?.llm.answer.provider || '-'} / {runtimeOverview?.llm.answer.model || '-'}
            </p>
            <p>
              Rerank: {runtimeOverview?.llm.rerank.provider || '-'} / {runtimeOverview?.llm.rerank.model || '-'}
            </p>
            <p>
              Rewrite: {runtimeOverview?.llm.rewrite.provider || '-'} / {runtimeOverview?.llm.rewrite.model || '-'}
            </p>
          </div>
          <div className="mt-4 rounded-xl border border-slate-200 bg-white p-3 text-xs text-slate-700">
            <p className="font-medium text-slate-900">Marker LLM 摘要</p>
            <p className="mt-1">
              状态: {runtimeOverview?.pipeline.marker_llm?.status || 'disabled'} · Service:{' '}
              {runtimeOverview?.pipeline.marker_llm?.llm_service || '-'}
            </p>
            <p className="mt-1">
              最近导入: {runtimeOverview?.pipeline.last_ingest?.degraded ? '降级完成' : '未降级'} ·
              {runtimeOverview?.pipeline.last_ingest?.fallback_reason || ' 无降级原因'}
            </p>
            <p className="mt-1">
              产物健康: healthy {runtimeOverview?.pipeline.artifacts?.counts?.healthy ?? 0} / missing{' '}
              {runtimeOverview?.pipeline.artifacts?.counts?.missing ?? 0} / stale {runtimeOverview?.pipeline.artifacts?.counts?.stale ?? 0}
            </p>
          </div>
        </article>

        <article className="rounded-2xl border border-slate-200 bg-white p-4">
          <div className="mb-3 flex items-center justify-between">
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">Marker Runtime Tuning</p>
            <div className="flex items-center gap-2">
              <button
                type="button"
                data-testid="pipeline-8gb-preset-btn"
                onClick={apply8GbSafePreset}
                disabled={controlsDisabled || pipelineSaveLoading}
                className="inline-flex items-center gap-1 rounded-lg border border-sky-200 bg-sky-50 px-3 py-1.5 text-xs font-medium text-sky-700 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <Sparkles className="h-3.5 w-3.5" />
                一键填充 8GB 安全档位
              </button>
              <button
                type="button"
                data-testid="pipeline-save-btn"
                onClick={() => void handleSavePipeline()}
                disabled={controlsDisabled || pipelineSaveLoading}
                className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {pipelineSaveLoading ? '保存中...' : '保存 Marker 配置'}
              </button>
            </div>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            {(
              [
                ['recognition_batch_size', 'Recognition Batch'],
                ['detector_batch_size', 'Detector Batch'],
                ['layout_batch_size', 'Layout Batch'],
                ['ocr_error_batch_size', 'OCR Error Batch'],
                ['table_rec_batch_size', 'Table Rec Batch']
              ] as Array<[keyof MarkerTuning, string]>
            ).map(([field, label]) => (
              <label key={field} className="block text-xs font-medium text-slate-600">
                {label}
                <input
                  data-testid={`pipeline-${field}-input`}
                  type="number"
                  min={1}
                  max={32}
                  value={markerTuning[field]}
                  onChange={(event) => setMarkerField(field, Number(event.target.value) as MarkerTuning[typeof field])}
                  className="mt-1 h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-800 outline-none ring-sky-300 transition focus:ring-2"
                />
                {markerFieldErrors[field] ? <span className="mt-1 block text-[11px] text-rose-600">{markerFieldErrors[field]}</span> : null}
              </label>
            ))}
            <label className="block text-xs font-medium text-slate-600">
              DType
              <select
                data-testid="pipeline-model-dtype-select"
                value={markerTuning.model_dtype}
                onChange={(event) => setMarkerField('model_dtype', event.target.value)}
                className="mt-1 h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-800 outline-none ring-sky-300 transition focus:ring-2"
              >
                <option value="float16">float16</option>
                <option value="float32">float32</option>
                <option value="bfloat16">bfloat16</option>
              </select>
              {markerFieldErrors.model_dtype ? <span className="mt-1 block text-[11px] text-rose-600">{markerFieldErrors.model_dtype}</span> : null}
            </label>
          </div>
          <div className="mt-3 rounded-xl border border-dashed border-slate-200 bg-slate-50 p-2 text-[11px] text-slate-600">
            <p className="font-medium text-slate-700">当前生效 Marker 参数</p>
            <ul className="mt-1 space-y-0.5">
              {Object.entries(pipelineConfig?.effective?.marker_tuning ?? defaultMarkerTuning).map(([key, value]) => (
                <li key={key}>
                  {key}: <span className="font-mono">{String(value)}</span>
                </li>
              ))}
            </ul>
          </div>
          <div data-testid="marker-llm-panel" className="mt-4 rounded-2xl border border-slate-200 bg-slate-50/80 p-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">Marker LLM Services</p>
                <p className="mt-1 text-[11px] text-slate-600">让前端与 Marker `--use_llm` 配置保持同步，并在保存后回显运行态。</p>
              </div>
              <label className="inline-flex items-center gap-2 text-xs font-medium text-slate-700">
                <input
                  data-testid="marker-llm-use-toggle"
                  type="checkbox"
                  checked={markerLlm.use_llm}
                  onChange={(event) => setMarkerLlmField('use_llm', event.target.checked)}
                />
                启用 `--use_llm`
              </label>
            </div>
            <label className="mt-3 block text-xs font-medium text-slate-600">
              LLM Service
              <select
                data-testid="marker-llm-service-select"
                value={markerLlm.llm_service}
                onChange={(event) => setMarkerLlmField('llm_service', event.target.value)}
                className="mt-1 h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-800 outline-none ring-sky-300 transition focus:ring-2"
              >
                {markerLlmServiceOptions.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
              {markerLlmFieldErrors.llm_service ? (
                <span className="mt-1 block text-[11px] text-rose-600">{markerLlmFieldErrors.llm_service}</span>
              ) : null}
            </label>
            {markerLlm.use_llm ? (
              <div className="mt-3 grid gap-3 sm:grid-cols-2">
                {visibleMarkerLlmFields.map((field) => {
                  const meta = markerLlmFieldMeta[field];
                  const isSecret = Boolean(meta.secret);
                  const showSecret = Boolean(markerLlmShowSecrets[field]);
                  const isMarkerOpenAiModelField =
                    markerLlm.llm_service === 'marker.services.openai.OpenAIService' && field === 'openai_model';
                  return (
                    <label key={field} className="block text-xs font-medium text-slate-600">
                      {meta.label}
                      {isMarkerOpenAiModelField ? (
                        <>
                          <div className="mt-1 flex items-center gap-2">
                            <select
                              data-testid="marker-llm-openai-model-select"
                              value={markerLlm.openai_model}
                              onChange={(event) => setMarkerLlmField('openai_model', event.target.value)}
                              className="h-10 min-w-0 flex-1 rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-800 outline-none ring-sky-300 transition focus:ring-2"
                            >
                              <option value="">请选择模型</option>
                              {markerOpenAiModels.map((model) => (
                                <option key={`marker-openai-${model.id}`} value={model.id}>
                                  {model.id}
                                </option>
                              ))}
                            </select>
                            <button
                              type="button"
                              data-testid="marker-llm-openai-detect-btn"
                              onClick={() => void handleDetectMarkerOpenAiModels()}
                              disabled={
                                controlsDisabled ||
                                markerOpenAiDetectLoading ||
                                !markerLlm.openai_base_url.trim() ||
                                !markerLlm.openai_api_key.trim()
                              }
                              className="shrink-0 rounded-lg border border-slate-200 px-3 py-2 text-xs font-medium text-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
                            >
                              {markerOpenAiDetectLoading ? '检测中...' : '测试连接'}
                            </button>
                          </div>
                          <p className="mt-1 text-[11px] text-slate-500">将使用 OpenAI 兼容 `/models` 端点自动拉取可用模型。</p>
                        </>
                      ) : (
                        <div className="relative mt-1">
                          <input
                            data-testid={`marker-llm-${field}-input`}
                            type={isSecret && !showSecret ? 'password' : meta.type ?? 'text'}
                            value={markerLlm[field]}
                            onChange={(event) => setMarkerLlmField(field, event.target.value)}
                            placeholder={meta.placeholder}
                            className="h-10 w-full rounded-xl border border-slate-200 bg-white px-3 pr-10 text-sm text-slate-800 outline-none ring-sky-300 transition focus:ring-2"
                          />
                          {isSecret ? (
                            <button
                              type="button"
                              onClick={() => setMarkerLlmShowSecrets((prev) => ({ ...prev, [field]: !prev[field] }))}
                              className="absolute inset-y-0 right-2 inline-flex items-center text-slate-500"
                              aria-label={showSecret ? '隐藏密钥' : '显示密钥'}
                            >
                              {showSecret ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                            </button>
                          ) : null}
                        </div>
                      )}
                      {pipelineConfig?.effective_source?.marker_llm?.[field] ? (
                        <span className="mt-1 block text-[11px] text-slate-500">
                          来源: {pipelineConfig.effective_source.marker_llm[field]}
                        </span>
                      ) : null}
                      {markerLlmFieldErrors[field] ? (
                        <span className="mt-1 block text-[11px] text-rose-600">{markerLlmFieldErrors[field]}</span>
                      ) : null}
                    </label>
                  );
                })}
              </div>
            ) : (
              <p className="mt-3 text-[11px] text-slate-500">关闭后仍保留已保存字段，但导入链路不会请求 Marker LLM 增强。</p>
            )}
            <div className="mt-3 rounded-xl border border-dashed border-slate-200 bg-white p-2 text-[11px] text-slate-600">
              <p className="font-medium text-slate-700">当前生效 Marker LLM 摘要</p>
              <p className="mt-1">
                状态: {runtimeOverview?.pipeline.marker_llm?.status || 'disabled'} · 配置完整:{' '}
                {runtimeOverview?.pipeline.marker_llm?.configured ? 'yes' : 'no'}
              </p>
              <ul className="mt-1 space-y-0.5">
                {(runtimeOverview?.pipeline.marker_llm?.summary_fields ?? []).map((item) => (
                  <li key={item.field}>
                    {item.field}: <span className="font-mono">{item.value}</span> <span className="text-slate-400">({item.source})</span>
                  </li>
                ))}
                {!(runtimeOverview?.pipeline.marker_llm?.summary_fields ?? []).length ? <li>暂无额外字段摘要</li> : null}
              </ul>
            </div>
          </div>
          {pipelineStatusText ? <p className="mt-2 text-xs text-emerald-700">{pipelineStatusText}</p> : null}
          {pipelineGlobalError ? <p className="mt-2 text-xs text-rose-600">{pipelineGlobalError}</p> : null}
        </article>
      </section>

      <div className="grid gap-4 xl:grid-cols-3">
        {stageMeta.map((stage) => {
          const item = configs[stage.key];
          const inherited = isInheritMode(stage.key);
          const showUnsaved = (field: keyof DraftConfig) => dirtyFieldsByStage[stage.key]?.[field];
          return (
            <article key={stage.key} className="magic-card rounded-2xl p-[1px]">
              <div className="h-full rounded-2xl bg-white p-4">
                <div className="mb-3 flex items-center justify-between gap-2">
                  <h3 className="text-sm font-semibold text-slate-900">{stage.title}</h3>
                  <button
                    type="button"
                    data-testid={`llm-${stage.key}-detect-btn`}
                    onClick={() => void handleDetectModels(stage.key)}
                    disabled={
                      controlsDisabled ||
                      item.detectLoading ||
                      !(inherited ? configs.answer.apiBase : item.apiBase).trim() ||
                      !(inherited ? configs.answer.apiKey : item.apiKey).trim()
                    }
                    className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {item.detectLoading ? '检测中...' : '测试连接'}
                  </button>
                </div>

                <div className="space-y-3">
                  <label className="block text-xs font-medium text-slate-600">
                    <span className="inline-flex items-center gap-2">
                      服务商
                      {showUnsaved('provider') ? <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] text-amber-700">⚠️ 未保存</span> : null}
                    </span>
                    <select
                      data-testid={`llm-${stage.key}-provider-select`}
                      value={item.provider}
                      onChange={(event) => handleProviderChange(stage.key, event.target.value)}
                      disabled={controlsDisabled}
                      className="mt-1 h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-800 outline-none ring-sky-300 transition focus:ring-2"
                    >
                      {providerOptions.map((provider) => (
                        <option key={provider.value} value={provider.value}>
                          {provider.label}
                        </option>
                      ))}
                    </select>
                  </label>

                  {inheritableStages.has(stage.key) ? (
                    <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 text-xs text-slate-700">
                      <label className="inline-flex items-center gap-2">
                        <input
                          type="checkbox"
                          checked={overrides[stage.key]}
                          onChange={(event) => setOverrides((prev) => ({ ...prev, [stage.key]: event.target.checked }))}
                        />
                        独立配置 (Override)
                      </label>
                      {inherited ? <p className="mt-2 text-emerald-700">🔄 已继承全局配置</p> : null}
                    </div>
                  ) : null}

                  {!inherited ? (
                    <>
                      <label className="block text-xs font-medium text-slate-600">
                        <span className="inline-flex items-center gap-2">
                          API Base
                          {showUnsaved('apiBase') ? <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] text-amber-700">⚠️ 未保存</span> : null}
                        </span>
                        <input
                          data-testid={`llm-${stage.key}-api-base-input`}
                          value={item.apiBase}
                          onChange={(event) => setField(stage.key, 'apiBase', event.target.value)}
                          disabled={controlsDisabled}
                          placeholder={stage.defaultApiBase}
                          className="mt-1 h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-800 outline-none ring-sky-300 transition focus:ring-2"
                        />
                      </label>

                      <label className="block text-xs font-medium text-slate-600">
                        <span className="inline-flex items-center gap-2">
                          API Key
                          {showUnsaved('apiKey') ? <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] text-amber-700">⚠️ 未保存</span> : null}
                        </span>
                        <div className="relative mt-1">
                          <input
                            data-testid={`llm-${stage.key}-api-key-input`}
                            type={item.showApiKey ? 'text' : 'password'}
                            value={item.apiKey}
                            onChange={(event) => setField(stage.key, 'apiKey', event.target.value)}
                            disabled={controlsDisabled}
                            placeholder="sk-..."
                            className="h-10 w-full rounded-xl border border-slate-200 bg-white px-3 pr-10 text-sm text-slate-800 outline-none ring-sky-300 transition focus:ring-2"
                          />
                          <button
                            type="button"
                            onClick={() => setField(stage.key, 'showApiKey', !item.showApiKey)}
                            disabled={controlsDisabled}
                            className="absolute inset-y-0 right-2 inline-flex items-center text-slate-500"
                            aria-label={item.showApiKey ? '隐藏密钥' : '显示密钥'}
                          >
                            {item.showApiKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                          </button>
                        </div>
                      </label>
                    </>
                  ) : null}

                  <label className="block text-xs font-medium text-slate-600">
                    <span className="inline-flex items-center gap-2">
                      模型
                      {showUnsaved('model') ? <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] text-amber-700">⚠️ 未保存</span> : null}
                    </span>
                    <select
                      data-testid={`llm-${stage.key}-model-select`}
                      value={item.model}
                      onChange={(event) => setField(stage.key, 'model', event.target.value)}
                      disabled={controlsDisabled}
                      className="mt-1 h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-800 outline-none ring-sky-300 transition focus:ring-2"
                    >
                      <option value="">请选择模型</option>
                      {item.models.map((model) => (
                        <option key={`${stage.key}-${model.id}`} value={model.id}>
                          {model.id}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>

                {item.error ? (
                  <p data-testid={`llm-${stage.key}-error`} className="mt-3 text-xs text-rose-600">
                    {item.error}
                  </p>
                ) : null}
              </div>
            </article>
          );
        })}
      </div>

      <div className="mt-6 flex flex-wrap items-center gap-3">
        <button
          type="button"
          data-testid="llm-save-btn"
          onClick={() => void handleSave()}
          disabled={controlsDisabled || saveLoading}
          className="shimmer-btn"
        >
          <Sparkles className="h-4 w-4" />
          {saveLoading ? '测试并保存中...' : '测试并保存'}
        </button>
        <span className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs text-slate-600">所有操作均含加载态反馈</span>
      </div>

      {statusText ? (
        <p data-testid="llm-status-text" className="mt-3 text-sm text-emerald-700">
          {statusText}
        </p>
      ) : null}
      {globalError ? (
        <p data-testid="llm-global-error" className="mt-3 text-sm text-rose-600">
          {globalError}
        </p>
      ) : null}
    </section>
  );
}

function toDraftPayload(source: Record<StageKey, StageConfig>): DraftPayload {
  return stageMeta.reduce(
    (acc, stage) => ({
      ...acc,
      [stage.key]: {
        provider: source[stage.key].provider,
        apiBase: source[stage.key].apiBase,
        apiKey: source[stage.key].apiKey,
        model: source[stage.key].model
      }
    }),
    {} as DraftPayload
  );
}
