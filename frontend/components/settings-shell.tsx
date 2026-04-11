'use client';

import { ChevronDown, Clock3, Eye, EyeOff, HelpCircle, Lock, ShieldAlert, Sparkles } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { toast } from 'sonner';
import { fetchAdminJson } from '../lib/admin-http';
import { resolveAdminUrl } from '../lib/deployment-endpoints';
import type { LlmLoggingSummary, MarkerLlmRuntimeConfig, MarkerTuning, PlannerRuntimeSummary, RuntimeOverview, RuntimeSource } from '../lib/types';

type AdminModel = { id: string; owned_by?: string | null };
type StageKey = 'answer' | 'embedding' | 'rerank' | 'rewrite' | 'graph_entity' | 'sufficiency_judge';

type StageConfig = {
  provider: string;
  apiBase: string;
  apiKey: string;
  model: string;
  models: AdminModel[];
  detectLoading: boolean;
  saveLoading: boolean;
  error: string;
  status: string;
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
  saved?: { marker_enabled?: boolean; marker_tuning?: MarkerTuning; marker_llm?: MarkerLlmForm };
  effective?: { marker_enabled?: boolean; marker_tuning?: MarkerTuning; marker_llm?: MarkerLlmForm };
  effective_source?: {
    marker_enabled?: RuntimeSource;
    marker_tuning?: Partial<Record<keyof MarkerTuning, RuntimeSource>>;
    marker_llm?: Partial<Record<MarkerLlmField, RuntimeSource>>;
  };
};

type PlannerConfigForm = {
  serviceMode: 'production' | 'diagnostic';
  provider: string;
  apiBase: string;
  apiKey: string;
  model: string;
  timeoutMs: number;
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
  { key: 'answer', title: '回答模型', defaultProvider: 'openai', defaultApiBase: 'https://api.openai.com/v1', defaultModel: '' },
  {
    key: 'embedding',
    title: '向量模型',
    defaultProvider: 'ollama',
    defaultApiBase: 'http://127.0.0.1:11434/v1',
    defaultModel: 'nomic-embed-text'
  },
  {
    key: 'rerank',
    title: '重排模型',
    defaultProvider: 'siliconflow',
    defaultApiBase: 'https://api.siliconflow.cn/v1',
    defaultModel: 'Qwen/Qwen3-Reranker-8B'
  },
  {
    key: 'rewrite',
    title: '问题改写模型',
    defaultProvider: 'ollama',
    defaultApiBase: 'http://127.0.0.1:11434/v1',
    defaultModel: 'qwen2.5:3b'
  },
  {
    key: 'graph_entity',
    title: '图谱实体模型',
    defaultProvider: 'openai',
    defaultApiBase: 'https://api.siliconflow.cn/v1',
    defaultModel: 'Pro/deepseek-ai/DeepSeek-V3.2'
  },
  {
    key: 'sufficiency_judge',
    title: '证据判定模型',
    defaultProvider: 'openai',
    defaultApiBase: 'https://api.siliconflow.cn/v1',
    defaultModel: 'Qwen/Qwen2.5-7B-Instruct'
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
      saveLoading: false,
      error: '',
      status: '',
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

const defaultPlannerConfig: PlannerConfigForm = {
  serviceMode: 'production',
  provider: 'openai',
  apiBase: 'https://api.siliconflow.cn/v1',
  apiKey: '',
  model: 'Pro/deepseek-ai/DeepSeek-V3.2',
  timeoutMs: 6000
};

function formatRuntimeSource(source?: RuntimeSource): string {
  if (source === 'env') {
    return '环境变量';
  }
  if (source === 'runtime') {
    return '运行时保存';
  }
  return '静态基线';
}

function formatBytes(value?: number): string {
  const size = typeof value === 'number' && Number.isFinite(value) ? value : 0;
  if (size < 1024) {
    return `${size} B`;
  }
  if (size < 1024 * 1024) {
    return `${(size / 1024).toFixed(1)} KB`;
  }
  if (size < 1024 * 1024 * 1024) {
    return `${(size / (1024 * 1024)).toFixed(1)} MB`;
  }
  return `${(size / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}

function formatRelativeTimeLabel(raw?: string): string {
  if (!raw) {
    return '未知时间';
  }
  const date = new Date(raw);
  if (Number.isNaN(date.getTime())) {
    return raw;
  }
  return date.toLocaleString('zh-CN', {
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  });
}

function formatMarkerModeSummary(summary?: string, markerEnabled?: boolean): string {
  if (summary === 'degraded_available') {
    return '增强降级可用';
  }
  if (summary === 'enhanced') {
    return '增强解析';
  }
  if (summary === 'base_only') {
    return '基础解析';
  }
  return markerEnabled ? '增强解析' : '基础解析';
}

function formatActiveJobKind(kind?: string): string {
  if (!kind) {
    return '后台任务';
  }
  if (kind.includes('chat')) {
    return '对话回答';
  }
  if (kind.includes('planner')) {
    return '回答规划';
  }
  if (kind.includes('import')) {
    return '资料导入';
  }
  return kind;
}

function formatActiveJobState(state?: string): string {
  if (state === 'queued') {
    return '排队中';
  }
  if (state === 'running') {
    return '进行中';
  }
  if (state === 'succeeded') {
    return '已完成';
  }
  if (state === 'failed') {
    return '失败';
  }
  return state || '处理中';
}

function formatActiveJobStage(progressStage?: string): string {
  const normalized = (progressStage || '').toLowerCase();
  if (!normalized) {
    return '正在处理中';
  }
  if (normalized.includes('queue')) {
    return '等待系统接单';
  }
  if (normalized.includes('plan')) {
    return '判断回答路径';
  }
  if (normalized.includes('retriev') || normalized.includes('search') || normalized.includes('recall')) {
    return '查找相关资料';
  }
  if (normalized.includes('rerank') || normalized.includes('rank')) {
    return '筛选重点内容';
  }
  if (normalized.includes('answer') || normalized.includes('write') || normalized.includes('draft') || normalized.includes('stream')) {
    return '整理最终回答';
  }
  return progressStage || '正在处理中';
}

function normalizeCompatibleProvider(provider: string, { preserveNative = false }: { preserveNative?: boolean } = {}): string {
  const normalized = provider.trim().toLowerCase();
  if (normalized === 'siliconflow' || normalized === 'silicon-flow') {
    return preserveNative ? 'siliconflow' : 'openai';
  }
  return provider.trim();
}

function HintTip({
  text,
  open,
  onToggle
}: {
  text: string;
  open: boolean;
  onToggle: () => void;
}) {
  return (
    <span className="relative inline-flex">
      <button
        type="button"
        aria-label="查看参数解释"
        aria-expanded={open}
        onClick={(event) => {
          event.preventDefault();
          event.stopPropagation();
          onToggle();
        }}
        className={`inline-flex rounded-full p-0.5 transition ${open ? 'bg-slate-900 text-white' : 'text-slate-400 hover:bg-slate-100 hover:text-slate-600'}`}
      >
        <HelpCircle className="h-3.5 w-3.5" />
      </button>
      {open ? (
        <span className="absolute left-1/2 top-full z-10 mt-2 w-64 -translate-x-1/2 rounded-xl bg-slate-950 px-3 py-2 text-[11px] leading-5 text-white shadow-xl">
          {text}
        </span>
      ) : null}
    </span>
  );
}

export function SettingsShell() {
  // 后续设置页继续沿用 magic-mcp 约束做现代化迭代，新增文案与注解保持中文语境。
  const draftStorageKey = 'settings-shell-draft-v2';
  const [configs, setConfigs] = useState<Record<StageKey, StageConfig>>(initialConfigs);
  const [overrides, setOverrides] = useState<OverridePayload>(initialOverrides);
  const [saveLoading, setSaveLoading] = useState(false);
  const [statusText, setStatusText] = useState('');
  const [globalError, setGlobalError] = useState('');
  const [draftHydrated, setDraftHydrated] = useState(false);
  const [persistedDraft, setPersistedDraft] = useState<DraftPayload>(toDraftPayload(initialConfigs));
  const [markerTuning, setMarkerTuning] = useState<MarkerTuning>(defaultMarkerTuning);
  const [markerEnabled, setMarkerEnabled] = useState(false);
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
  const [plannerConfig, setPlannerConfig] = useState<PlannerConfigForm>(defaultPlannerConfig);
  const [plannerPersisted, setPlannerPersisted] = useState<PlannerConfigForm>(defaultPlannerConfig);
  const [plannerModels, setPlannerModels] = useState<AdminModel[]>(defaultPlannerConfig.model ? [{ id: defaultPlannerConfig.model }] : []);
  const [plannerSaveLoading, setPlannerSaveLoading] = useState(false);
  const [plannerDetectLoading, setPlannerDetectLoading] = useState(false);
  const [plannerStatusText, setPlannerStatusText] = useState('');
  const [plannerGlobalError, setPlannerGlobalError] = useState('');
  const [activeTooltipId, setActiveTooltipId] = useState<string | null>(null);
  const llmConfigUrl = useMemo(() => resolveAdminUrl('/api/admin/llm-config'), []);
  const detectModelsUrl = useMemo(() => resolveAdminUrl('/api/admin/detect-models'), []);
  const pipelineConfigUrl = useMemo(() => resolveAdminUrl('/api/admin/pipeline-config'), []);
  const llmLogDownloadUrl = useMemo(() => resolveAdminUrl('/api/admin/llm-logs/download'), []);
  const plannerConfigUrl = useMemo(() => resolveAdminUrl('/api/admin/planner-config'), []);
  const runtimeOverviewUrl = useMemo(() => resolveAdminUrl('/api/admin/runtime-overview'), []);
  const settingsLocked = runtimeOverview?.jobs?.settings_locked === true;
  const activeJobs = runtimeOverview?.jobs?.active ?? [];
  const primaryActiveJob = activeJobs[0];
  const controlsDisabled = !draftHydrated || settingsLocked;
  const visibleMarkerLlmFields = markerLlm.use_llm ? markerLlmFieldOrder[markerLlm.llm_service] ?? [] : [];

  const providerOptions = useMemo(
    () => Object.entries(providerPresets).map(([value, item]) => ({ value, label: item.label })),
    []
  );
  const coreModelCards: Array<[StageKey, string, string]> = [
    ['answer', '回答模型', '决定最终回复内容'],
    ['embedding', '向量模型', '决定向量检索质量'],
    ['rerank', '重排模型', '决定证据排序'],
    ['rewrite', '问题改写模型', '优化检索提问'],
    ['graph_entity', '图谱实体模型', '支持图谱实体抽取'],
    ['sufficiency_judge', '证据判定模型', '用于充分性与证据匹配判定']
  ];
  const plannerDirty = useMemo(() => JSON.stringify(plannerConfig) !== JSON.stringify(plannerPersisted), [plannerConfig, plannerPersisted]);
  const runtimeLlmLogging = runtimeOverview?.observability?.llm_logging as LlmLoggingSummary | undefined;

  const setField = <K extends keyof StageConfig>(stage: StageKey, field: K, value: StageConfig[K]) => {
    setConfigs((prev) => ({
      ...prev,
      [stage]: {
        ...prev[stage],
        [field]: value,
        status:
          field === 'provider' || field === 'apiBase' || field === 'apiKey' || field === 'model'
            ? ''
            : prev[stage].status,
      },
    }));
  };

  const setMarkerField = <K extends keyof MarkerTuning>(field: K, value: MarkerTuning[K]) => {
    setMarkerTuning((prev) => ({ ...prev, [field]: value }));
    setMarkerFieldErrors((prev) => ({ ...prev, [field]: '' }));
  };

  const setMarkerLlmField = <K extends MarkerLlmField>(field: K, value: MarkerLlmForm[K]) => {
    setMarkerLlm((prev) => ({ ...prev, [field]: value }));
    setMarkerLlmFieldErrors((prev) => ({ ...prev, [field]: '' }));
  };
  const setPlannerField = <K extends keyof PlannerConfigForm>(field: K, value: PlannerConfigForm[K]) => {
    setPlannerConfig((prev) => ({ ...prev, [field]: value }));
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
    if (code === 'SETTINGS_LOCKED_BY_ACTIVE_JOB') {
      return withBackendDetail('当前存在运行中的任务，设置暂时只读，请等待任务结束后再修改。', message);
    }
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
      graph_entity: {},
      sufficiency_judge: {}
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
          sufficiency_judge?: { provider?: string; api_base?: string; model?: string };
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
            const provider = normalizeCompatibleProvider(stagePayload?.provider || prev[stage.key].provider, {
              preserveNative: stage.key === 'rerank'
            });
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
    const loadPlannerConfig = async () => {
      try {
        const result = await fetchAdminJson<{
          configured?: boolean;
          service_mode?: 'production' | 'diagnostic';
          provider?: string;
          api_base?: string;
          model?: string;
          timeout_ms?: number;
        }>(plannerConfigUrl);
        if (!mounted || !result.ok || !result.data.configured) {
          return;
        }
        const nextConfig: PlannerConfigForm = {
          serviceMode: result.data.service_mode || 'production',
          provider: normalizeCompatibleProvider(result.data.provider || defaultPlannerConfig.provider),
          apiBase: result.data.api_base || defaultPlannerConfig.apiBase,
          apiKey: '',
          model: result.data.model || defaultPlannerConfig.model,
          timeoutMs:
            typeof result.data.timeout_ms === 'number' && Number.isFinite(result.data.timeout_ms)
              ? result.data.timeout_ms
              : defaultPlannerConfig.timeoutMs
        };
        setPlannerConfig(nextConfig);
        setPlannerPersisted(nextConfig);
        setPlannerModels(mergeDetectedModels([], nextConfig.model));
      } catch {
        // Planner 面板失败时保留静态默认值，不阻断其余设置页。
      }
    };
    void loadPlannerConfig();
    return () => {
      mounted = false;
    };
  }, [plannerConfigUrl]);

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
          setMarkerEnabled(Boolean(pipelineResult.data.saved?.marker_enabled));
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
  const hasUnsavedChanges = isDirty || plannerDirty;

  useEffect(() => {
    if (!hasUnsavedChanges) {
      return;
    }
    const onBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', onBeforeUnload);
    return () => window.removeEventListener('beforeunload', onBeforeUnload);
  }, [hasUnsavedChanges]);

  useEffect(() => {
    if (!hasUnsavedChanges) {
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
  }, [hasUnsavedChanges]);

  const handleProviderChange = (stage: StageKey, provider: string) => {
    const preset = providerPresets[provider];
    setConfigs((prev) => ({
      ...prev,
      [stage]: {
        ...prev[stage],
        provider,
        apiBase: preset?.apiBase ?? prev[stage].apiBase,
        error: '',
        status: '',
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
                provider: normalizeCompatibleProvider(configs[stage.key].provider.trim(), {
                  preserveNative: stage.key === 'rerank'
                }),
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

  const buildStageSavePayload = (draft: DraftPayload) =>
    stageMeta.reduce(
      (acc, stage) => ({
        ...acc,
        [stage.key]: {
          provider: normalizeCompatibleProvider(draft[stage.key].provider.trim(), {
            preserveNative: stage.key === 'rerank'
          }),
          api_base: (isInheritMode(stage.key) ? draft.answer.apiBase : draft[stage.key].apiBase).trim(),
          api_key: (isInheritMode(stage.key) ? draft.answer.apiKey : draft[stage.key].apiKey).trim(),
          model: draft[stage.key].model.trim()
        }
      }),
      {}
    );

  const handleSaveStage = async (stageKey: StageKey) => {
    if (controlsDisabled) {
      return;
    }
    const currentDraft = toDraftPayload(configs);
    const nextDraft: DraftPayload = {
      ...persistedDraft,
      [stageKey]: currentDraft[stageKey],
      ...(stageKey === 'answer' ? { answer: currentDraft.answer } : {})
    };
    const current = configs[stageKey];
    const inherited = isInheritMode(stageKey);
    const apiBase = inherited ? nextDraft.answer.apiBase : current.apiBase;
    const apiKey = inherited ? nextDraft.answer.apiKey : current.apiKey;
    if (!current.provider.trim() || !apiBase.trim() || !apiKey.trim() || !current.model.trim()) {
      setField(stageKey, 'error', `请先补全 ${stageMeta.find((item) => item.key === stageKey)?.title || '当前模型'} 的服务商、API Base、API Key 和模型。`);
      return;
    }

    setField(stageKey, 'saveLoading', true);
    setField(stageKey, 'error', '');
    setField(stageKey, 'status', '');
    setGlobalError('');
    setStatusText('');

    try {
      const result = await fetchAdminJson<{ detail?: unknown }>(llmConfigUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(buildStageSavePayload(nextDraft))
      });
      if (!result.ok) {
        if (!result.data) {
          setField(stageKey, 'error', result.message);
          toast.error('保存失败，请检查配置。');
          return;
        }
        const parsed = parseAdminError(result.data);
        const guidance = mapAdminErrorToGuidance(parsed, 'save');
        setField(parsed.stage || stageKey, 'error', guidance);
        toast.error('保存失败，请检查配置。');
        return;
      }

      setPersistedDraft((prev) => ({
        ...prev,
        [stageKey]: currentDraft[stageKey],
        ...(stageKey === 'answer' ? { answer: currentDraft.answer } : {})
      }));
      setField(stageKey, 'status', `${stageMeta.find((item) => item.key === stageKey)?.title || '当前模型'}已保存`);
      toast.success(`${stageMeta.find((item) => item.key === stageKey)?.title || '当前模型'}保存成功`);
    } catch (error) {
      const message =
        error instanceof TypeError ? networkErrorMessage('save') : error instanceof Error ? error.message : '保存失败';
      setField(stageKey, 'error', message);
      toast.error('保存失败，请稍后重试。');
    } finally {
      setField(stageKey, 'saveLoading', false);
    }
  };

  const handleDetectPlannerModel = async () => {
    if (controlsDisabled || plannerDetectLoading) {
      return;
    }
    if (!plannerConfig.apiBase.trim() || !plannerConfig.apiKey.trim()) {
      setPlannerGlobalError('请先填写规划模型的服务地址与密钥，再测试连接。');
      return;
    }
    setPlannerDetectLoading(true);
    setPlannerGlobalError('');
    setPlannerStatusText('');
    try {
      const result = await fetchAdminJson<{ models?: AdminModel[]; detail?: unknown }>(detectModelsUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ api_base: plannerConfig.apiBase.trim(), api_key: plannerConfig.apiKey.trim() })
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
        setPlannerGlobalError('未检测到可用模型：请确认服务地址和密钥有效。');
        return;
      }
      const nextModels = mergeDetectedModels(detected, plannerConfig.model);
      setPlannerModels(nextModels);
      setPlannerConfig((prev) => ({
        ...prev,
        model: prev.model && nextModels.some((item) => item.id === prev.model) ? prev.model : detected[0]?.id || ''
      }));
      setPlannerStatusText(`规划模型连接成功，已发现 ${detected.length} 个可选模型。`);
      toast.success('规划模型连接成功');
    } catch (error) {
      const message =
        error instanceof TypeError
          ? networkErrorMessage('detect')
          : error instanceof Error
            ? error.message
            : '探测失败';
      setPlannerGlobalError(message);
      toast.error('规划模型连接失败');
    } finally {
      setPlannerDetectLoading(false);
    }
  };

  const handleSavePlanner = async () => {
    if (controlsDisabled || plannerSaveLoading) {
      return;
    }
    if (!plannerConfig.provider.trim() || !plannerConfig.apiBase.trim() || !plannerConfig.model.trim()) {
      setPlannerGlobalError('请先补全规划模型的服务商、服务地址和模型。');
      return;
    }
    if (plannerConfig.serviceMode === 'production' && !plannerConfig.apiKey.trim()) {
      setPlannerGlobalError('正式模式下必须填写规划模型密钥。');
      return;
    }
    setPlannerSaveLoading(true);
    setPlannerStatusText('');
    setPlannerGlobalError('');
    try {
      const result = await fetchAdminJson<{ detail?: unknown; config?: PlannerRuntimeSummary }>(plannerConfigUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          service_mode: plannerConfig.serviceMode,
          provider: normalizeCompatibleProvider(plannerConfig.provider.trim()),
          api_base: plannerConfig.apiBase.trim(),
          api_key: plannerConfig.apiKey.trim(),
          model: plannerConfig.model.trim(),
          timeout_ms: Number(plannerConfig.timeoutMs)
        })
      });
      if (!result.ok) {
        const parsed = parseAdminError(result.data);
        setPlannerGlobalError(mapAdminErrorToGuidance(parsed, 'save'));
        toast.error('规划模型保存失败');
        return;
      }
      const persisted = { ...plannerConfig, apiKey: '' };
      setPlannerConfig(persisted);
      setPlannerPersisted(persisted);
      setPlannerModels(mergeDetectedModels(plannerModels, persisted.model));
      setPlannerStatusText('Planner Runtime 配置已保存并进入统一治理。');
      toast.success('规划模型保存成功');
      const overviewResult = await fetchAdminJson<RuntimeOverview>(runtimeOverviewUrl);
      if (overviewResult.ok) {
        setRuntimeOverview(overviewResult.data);
      }
    } catch {
      setPlannerGlobalError('网络请求失败：请确认内核服务在线后重试保存。');
      toast.error('规划模型保存失败');
    } finally {
      setPlannerSaveLoading(false);
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
          marker_enabled: markerEnabled,
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
      setPipelineStatusText('Marker 开关、运行档位与增强服务配置已保存并生效。');
      toast.success('Marker 配置保存成功');
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
      toast.error('Marker 配置保存失败');
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
    <section className="glass-card rounded-[34px] p-5 md:p-6">
      <header className="mb-6">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">模型设置</p>
        <h2 data-testid="settings-shell-title" className="mt-2 text-[32px] font-semibold tracking-tight text-slate-950">
          模型设置与导入优化
        </h2>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
          这里只改当前页面可调的配置，不会覆盖底层默认策略。页面上半部分先告诉你系统现在实际在用什么，避免改错位置。
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
        {settingsLocked ? (
          <div
            data-testid="settings-lock-banner"
            className="lock-grid mt-4 overflow-hidden rounded-[30px] border border-amber-300 bg-[radial-gradient(circle_at_top_left,rgba(251,191,36,0.22),transparent_34%),linear-gradient(135deg,#fff7ed,#ffffff_52%,#fef3c7)] shadow-[0_26px_70px_rgba(245,158,11,0.16)]"
          >
            <div className="grid gap-4 p-5 lg:grid-cols-[1.15fr_0.85fr] lg:p-6">
              <div>
                <div className="inline-flex items-center gap-2 rounded-full border border-amber-300 bg-white/85 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.22em] text-amber-800">
                  <span className="lock-pulse inline-flex h-6 w-6 items-center justify-center rounded-full bg-amber-500 text-white">
                    <Lock className="h-3.5 w-3.5" />
                  </span>
                  设置已暂时锁定
                </div>
                <h3 className="mt-4 text-[28px] font-semibold leading-tight tracking-tight text-slate-950">
                  当前正在生成或处理任务，先不要改设置
                </h3>
                <p className="mt-3 max-w-2xl text-sm leading-7 text-slate-700">
                  现在可以继续查看当前配置，但所有输入框、测试连接和保存按钮都会先进入只读模式。等任务结束后，这里会自动恢复可编辑。
                </p>
                <div className="mt-4 flex flex-wrap gap-2 text-xs">
                  <span className="rounded-full border border-amber-200 bg-white/85 px-3 py-1.5 font-medium text-amber-900">
                    {activeJobs.length || 1} 个任务占用设置锁
                  </span>
                  <span className="rounded-full border border-slate-200 bg-white/80 px-3 py-1.5 text-slate-700">当前页面仅可查看</span>
                </div>
              </div>

              <div className="rounded-[24px] border border-white/80 bg-white/82 p-4 shadow-sm">
                <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">
                  <Clock3 className="h-3.5 w-3.5 text-amber-600" />
                  正在占用设置锁的任务
                </div>
                {primaryActiveJob ? (
                  <div className="mt-3 rounded-[22px] border border-amber-100 bg-amber-50/70 p-4">
                    <p className="text-lg font-semibold text-slate-950">{formatActiveJobKind(primaryActiveJob.kind)}</p>
                    <p className="mt-2 text-sm text-slate-700">
                      {formatActiveJobState(primaryActiveJob.state)} · {formatActiveJobStage(primaryActiveJob.progressStage)}
                    </p>
                    <p className="mt-3 break-all text-[11px] font-mono text-slate-500">{primaryActiveJob.jobId}</p>
                  </div>
                ) : (
                  <p className="mt-3 text-sm leading-6 text-slate-600">后台任务正在运行，系统暂时不允许改动配置。</p>
                )}
                {activeJobs.slice(1).length ? (
                  <div className="mt-3 space-y-2 text-xs text-slate-600">
                    {activeJobs.slice(1, 4).map((job) => (
                      <div key={job.jobId} className="rounded-2xl border border-slate-200 bg-slate-50 px-3 py-2">
                        <p className="font-medium text-slate-800">{formatActiveJobKind(job.kind)}</p>
                        <p className="mt-1">
                          {formatActiveJobState(job.state)} · {formatActiveJobStage(job.progressStage)}
                        </p>
                      </div>
                    ))}
                  </div>
                ) : null}
              </div>
            </div>
          </div>
        ) : null}
      </header>

      <div className="relative">
        {settingsLocked ? (
          <div className="sticky top-4 z-20 mb-4">
            <div
              data-testid="settings-lock-spotlight"
              className="lock-grid rounded-[26px] border border-amber-300 bg-[linear-gradient(135deg,rgba(255,247,237,0.96),rgba(255,255,255,0.98)_55%,rgba(254,243,199,0.94))] p-4 shadow-[0_18px_40px_rgba(245,158,11,0.14)]"
            >
              <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                <div className="flex items-start gap-3">
                  <span className="lock-pulse inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-amber-500 text-white shadow-[0_10px_30px_rgba(245,158,11,0.28)]">
                    <ShieldAlert className="h-5 w-5" />
                  </span>
                  <div>
                    <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-amber-700">只读提醒</p>
                    <p className="mt-1 text-lg font-semibold text-slate-950">下方所有可编辑区域都已暂时锁住</p>
                    <p className="mt-1 text-sm leading-6 text-slate-600">
                      等当前任务结束后，按钮和输入框会自动恢复，不需要手动刷新页面。
                    </p>
                  </div>
                </div>
                <div className="rounded-2xl border border-white/90 bg-white/80 px-4 py-3 text-sm text-slate-700">
                  <p className="font-medium text-slate-900">
                    {primaryActiveJob ? formatActiveJobKind(primaryActiveJob.kind) : '后台任务'}
                  </p>
                  <p className="mt-1">
                    {primaryActiveJob
                      ? `${formatActiveJobState(primaryActiveJob.state)} · ${formatActiveJobStage(primaryActiveJob.progressStage)}`
                      : '处理中'}
                  </p>
                </div>
              </div>
            </div>
          </div>
        ) : null}

        <div className={`relative ${settingsLocked ? 'isolate rounded-[34px]' : ''}`}>
          {settingsLocked ? (
            <div
              aria-hidden
              className="pointer-events-none absolute inset-0 z-10 rounded-[34px] border border-amber-200/80 bg-[linear-gradient(180deg,rgba(255,251,235,0.28),rgba(255,255,255,0.56))]"
            />
          ) : null}

          <div className={settingsLocked ? 'opacity-55' : ''}>

      <section className="mb-6 grid gap-4 xl:grid-cols-[1.2fr_0.8fr]">
        <article data-testid="runtime-overview-panel" className="rounded-[28px] border border-slate-200 bg-[linear-gradient(135deg,#fffdfa,#ffffff_48%,#f3f8ff)] p-5 shadow-[0_18px_50px_rgba(15,23,42,0.05)]">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">当前实际使用的模型</p>
              <p className="mt-1 text-[11px] text-slate-400">这里只展示系统现在真的在用什么。</p>
              <h3 className="mt-2 text-xl font-semibold text-slate-950">先看系统现在实际在用什么，再决定是否调整</h3>
              <p className="mt-2 text-sm leading-6 text-slate-600">
                这里是只读摘要，只告诉你回答、检索、排序这些关键环节当前实际生效的模型和来源。真正可保存的配置在下面。
              </p>
            </div>
            <div className="rounded-2xl border border-slate-200 bg-white/85 px-4 py-3 text-sm text-slate-700">
              <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">当前状态</p>
              <p className="mt-2 font-medium text-slate-900">
                {runtimeOverview?.status.level ?? 'ERROR'}
                {runtimeOverview?.status.reasons?.[0] ? ` · ${runtimeOverview.status.reasons[0]}` : ''}
              </p>
            </div>
          </div>

          <div data-testid="core-model-overview" className="mt-6 grid gap-5 lg:grid-cols-2 2xl:grid-cols-3">
            {coreModelCards.map(([stageKey, label, hint]) => {
              const stage = configs[stageKey];
              return (
                <div
                  key={stageKey}
                  data-testid={`core-model-card-${stageKey}`}
                  className="block min-w-0 rounded-[24px] border border-slate-200 bg-white/90 p-5"
                >
                  <span className="text-sm font-semibold text-slate-900">{label}</span>
                  <span className="mt-1.5 block text-xs leading-5 text-slate-500">{hint}</span>
                  <div className="mt-4 rounded-2xl border border-slate-100 bg-slate-50/80 px-3.5 py-3">
                    <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-400">当前生效</p>
                    <p className="mt-1 break-all text-sm font-medium leading-6 text-slate-900">
                      {runtimeOverview?.llm?.[stageKey]?.model || stage.model || '未设置'}
                    </p>
                    <p className="mt-2 text-[11px] font-medium leading-5 text-slate-700">
                      {formatRuntimeSource(runtimeOverview?.llm?.[stageKey]?.source)}
                    </p>
                    <p className="mt-1 text-[11px] leading-5 text-slate-600">
                      服务商：{runtimeOverview?.llm?.[stageKey]?.provider || stage.provider || '未设置'}
                    </p>
                    <p className="mt-1 break-all font-mono text-[11px] leading-5 text-slate-600">
                      地址：{runtimeOverview?.llm?.[stageKey]?.api_base || stage.apiBase || '未填写地址'}
                    </p>
                  </div>
                </div>
              );
            })}
          </div>

          <div data-testid="planner-runtime-overview" className="mt-4 rounded-[22px] border border-amber-200 bg-amber-50/60 p-4 text-sm text-slate-700">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-amber-700">对话路线模型</p>
                <p className="mt-1 text-sm text-slate-700">
                  这部分决定系统是直接回答，还是先想一步再继续。它更偏高级控制，通常由管理员单独维护。
                </p>
              </div>
              <div className="rounded-xl border border-amber-200 bg-white/90 px-3 py-2 text-xs text-slate-700">
                <p>模式: {runtimeOverview?.planner?.service_mode === 'diagnostic' ? '诊断模式' : '正式模式'}</p>
                <p>来源: {formatRuntimeSource(runtimeOverview?.planner?.source)}</p>
              </div>
            </div>
            <p className="mt-3 break-all font-mono text-[11px] text-slate-700">
              {(runtimeOverview?.planner?.provider || plannerConfig.provider || '未设置') +
                ' / ' +
                (runtimeOverview?.planner?.model || plannerConfig.model || '未设置') +
                ' / ' +
                (runtimeOverview?.planner?.api_base || plannerConfig.apiBase || '未设置')}
            </p>
          </div>

          <div className="mt-4 rounded-[22px] border border-sky-200 bg-sky-50/60 p-4 text-sm text-slate-700">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-sky-700">LLM 调试日志</p>
                <p className="mt-1 text-sm text-slate-700">这里只读展示当前后端是否会把模型请求和返回写到控制台/日志文件。</p>
              </div>
              <div className="rounded-xl border border-sky-200 bg-white/90 px-3 py-2 text-xs text-slate-700">
                <p>开关: {runtimeLlmLogging?.enabled ? '开启' : '关闭'}</p>
                <p>来源: {formatRuntimeSource(runtimeLlmLogging?.source)}</p>
              </div>
            </div>
            <p className="mt-3 text-[11px] text-slate-700">
              最大日志体长度: {runtimeLlmLogging?.max_body_chars ?? '-'} 字符
            </p>
            <p className="mt-1 break-all font-mono text-[11px] text-slate-600">
              安全根目录: {runtimeLlmLogging?.safe_root || '未设置'}
            </p>
            <p className="mt-1 break-all font-mono text-[11px] text-slate-600">
              文件路径: {runtimeLlmLogging?.log_path || '未设置，当前仅输出到控制台'}
            </p>
            <div className="mt-3">
              <a
                href={runtimeLlmLogging?.download_url ? resolveAdminUrl(runtimeLlmLogging.download_url) : llmLogDownloadUrl}
                className="inline-flex items-center rounded-lg border border-sky-200 bg-white px-3 py-1.5 text-xs font-medium text-sky-800 transition hover:bg-sky-50"
              >
                下载当前日志文件
              </a>
            </div>
          </div>

          <div className="mt-4 rounded-[22px] border border-slate-200 bg-white/85 p-4 text-sm text-slate-700">
            <p className="font-medium text-slate-900">导入增强摘要</p>
            <p className="mt-2">
              模式：{formatMarkerModeSummary(runtimeOverview?.pipeline.marker_mode_summary, runtimeOverview?.pipeline.marker_enabled)} · 增强解析：
              {runtimeOverview?.pipeline.marker_enabled ? '已开启' : '已关闭'}
            </p>
            <p className="mt-1">
              最近导入：{runtimeOverview?.pipeline.last_ingest?.degraded ? '增强降级完成' : '基础或增强正常完成'} ·{' '}
              {runtimeOverview?.pipeline.last_ingest?.fallback_reason || '无额外说明'}
            </p>
            <p className="mt-1">
              文件健康：正常 {runtimeOverview?.pipeline.artifacts?.counts?.healthy ?? 0} / 缺失{' '}
              {runtimeOverview?.pipeline.artifacts?.counts?.missing ?? 0} / 待更新 {runtimeOverview?.pipeline.artifacts?.counts?.stale ?? 0}
            </p>
          </div>
        </article>

        <article className="rounded-[28px] border border-slate-200 bg-white/92 p-5 shadow-[0_18px_50px_rgba(15,23,42,0.05)]">
          <details className="group" open={false}>
            <summary data-testid="advanced-settings-toggle" className="flex cursor-pointer list-none items-center justify-between gap-3">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">高级设置概览</p>
                <h3 className="mt-2 text-xl font-semibold text-slate-950">高级模型调优</h3>
                <p className="mt-1 text-sm text-slate-600">这里只放不常改的高级项，默认折叠，避免把常用设置和重参数混在一起。</p>
              </div>
              <ChevronDown className="h-5 w-5 text-slate-400 transition group-open:rotate-180" />
            </summary>

            <div className="mt-4 border-t border-slate-200 pt-4">
              <div className="mb-3 flex items-center justify-between">
                <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">
                  高级参数
                  <HintTip
                    text="这部分主要影响 Marker 解析吞吐、显存占用与导入稳定性。普通用户通常无需改动。"
                    open={activeTooltipId === 'marker-runtime-overview'}
                    onToggle={() => setActiveTooltipId((prev) => (prev === 'marker-runtime-overview' ? null : 'marker-runtime-overview'))}
                  />
                </div>
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
                    {pipelineSaveLoading ? '保存中...' : '保存高级配置'}
                  </button>
                </div>
              </div>
              <div className="mb-3 rounded-xl border border-amber-200 bg-amber-50/70 p-3 text-xs text-slate-700">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <p className="font-medium text-slate-900">Marker 总开关</p>
                    <p className="mt-1 text-[11px] text-slate-600">关闭时系统默认走基础解析；开启后仅 PDF 会尝试 Marker 增强，失败时自动降级。</p>
                  </div>
                  <label className="inline-flex items-center gap-2 text-xs font-medium text-slate-800">
                    <input
                      data-testid="pipeline-marker-enabled-toggle"
                      type="checkbox"
                      checked={markerEnabled}
                      onChange={(event) => setMarkerEnabled(event.target.checked)}
                    />
                    启用 Marker 增强解析
                  </label>
                </div>
                <p className="mt-2">
                  当前生效: {pipelineConfig?.effective?.marker_enabled ? '增强解析' : '基础解析'}
                  {pipelineConfig?.effective_source?.marker_enabled ? ` · 来源: ${formatRuntimeSource(pipelineConfig.effective_source.marker_enabled)}` : ''}
                </p>
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
            {(
              [
                ['recognition_batch_size', '识别批量', '单次送入识别模型的页面数量，越大越快，但更占显存。'],
                ['detector_batch_size', '检测批量', '版面检测阶段的并发页数。'],
                ['layout_batch_size', '布局批量', '版面结构分析的批处理规模。'],
                ['ocr_error_batch_size', '疑难 OCR 批量', '用于重试疑难页面的批量大小。'],
                ['table_rec_batch_size', '表格识别批量', '表格解析时的单次处理数量。']
              ] as Array<[keyof MarkerTuning, string, string]>
            ).map(([field, label, hint]) => (
                <label key={field} className="block text-xs font-medium text-slate-600">
                  <span className="inline-flex items-center gap-1.5">
                    {label}
                    <HintTip
                      text={hint}
                      open={activeTooltipId === field}
                      onToggle={() => setActiveTooltipId((prev) => (prev === field ? null : field))}
                    />
                  </span>
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
                  <span className="inline-flex items-center gap-1.5">
                    精度类型
                    <HintTip
                      text="控制底层计算精度。通常 `float16` 更省显存，`float32` 更稳但更重。"
                      open={activeTooltipId === 'model_dtype'}
                      onToggle={() => setActiveTooltipId((prev) => (prev === 'model_dtype' ? null : 'model_dtype'))}
                    />
                  </span>
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
                <p className="font-medium text-slate-700">当前生效高级参数</p>
                <ul className="mt-1 space-y-0.5">
                  {Object.entries(pipelineConfig?.effective?.marker_tuning ?? defaultMarkerTuning).map(([key, value]) => (
                    <li key={key}>
                      {key}: <span className="font-mono">{String(value)}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </details>
          <div id="llm-log-config" data-testid="llm-log-config-panel" className="mt-4 rounded-2xl border border-sky-200 bg-sky-50/70 p-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-sky-700">LLM 调试日志</p>
                <p className="mt-1 text-[11px] leading-5 text-slate-600">
                  后端默认开启 LLM 调试日志，所有模型请求体、原始返回体和响应文本都会写入控制台与安全目录下的日志文件。页面只读展示当前状态，并提供下载入口。
                </p>
              </div>
              <a
                href={runtimeLlmLogging?.download_url ? resolveAdminUrl(runtimeLlmLogging.download_url) : llmLogDownloadUrl}
                className="rounded-lg border border-sky-200 bg-white px-3 py-1.5 text-xs font-medium text-sky-800 transition hover:bg-sky-50"
              >
                下载日志文件
              </a>
            </div>
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <div className="rounded-xl border border-white/90 bg-white/90 p-3 text-xs font-medium text-slate-700">
                <p>日志状态</p>
                <p className="mt-2 text-sm text-slate-900">{runtimeLlmLogging?.enabled ? '默认开启' : '关闭'}</p>
                <p className="mt-2 text-[11px] leading-5 text-slate-500">
                  日志开关和路径由后端固定控制，避免页面误改部署级文件系统参数。
                </p>
              </div>
              <div className="rounded-xl border border-white/90 bg-white/90 p-3 text-xs font-medium text-slate-700">
                <p>最大日志体长度</p>
                <p className="mt-2 text-sm text-slate-900">{runtimeLlmLogging?.max_body_chars ?? '-'}</p>
                <p className="mt-2 text-[11px] leading-5 text-slate-500">
                  请求或返回体超过上限时会自动截断，避免单条日志过大。
                </p>
              </div>
            </div>
            <div className="mt-3 rounded-xl border border-dashed border-sky-200 bg-white/80 p-3 text-[11px] text-slate-700">
              <p>当前生效开关: {runtimeLlmLogging?.enabled ? '开启' : '关闭'} · 来源: {formatRuntimeSource(runtimeLlmLogging?.source)}</p>
              <p className="mt-1">当前生效最大体长度: {runtimeLlmLogging?.max_body_chars ?? '-'}</p>
              <p className="mt-1 break-all font-mono text-slate-600">安全根目录: {runtimeLlmLogging?.safe_root || '未设置'}</p>
              <p className="mt-1 break-all font-mono text-slate-600">
                日志文件路径: {runtimeLlmLogging?.log_path || '未设置，当前仅输出到控制台'}
              </p>
            </div>
            {(runtimeLlmLogging?.recent_files?.length ?? 0) > 0 ? (
              <div className="mt-4 rounded-xl border border-white/90 bg-white/90 p-3">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">最近日志文件</p>
                    <p className="mt-1 text-[11px] text-slate-500">按最近更新时间展示，均位于受限安全目录中。</p>
                  </div>
                  <span className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-[10px] text-slate-500">
                    {runtimeLlmLogging?.recent_files?.length} 份
                  </span>
                </div>
                <div className="mt-3 space-y-2">
                  {runtimeLlmLogging?.recent_files?.map((file) => (
                    <div key={file.file_name} className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-slate-50/70 px-3 py-3 text-xs text-slate-700">
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <p className="truncate font-mono text-[11px] text-slate-900">{file.file_name}</p>
                          {file.current ? (
                            <span className="rounded-full bg-sky-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-sky-700">
                              当前
                            </span>
                          ) : null}
                        </div>
                        <p className="mt-1 text-[11px] text-slate-500">
                          {formatRelativeTimeLabel(file.updated_at)} · {formatBytes(file.size_bytes)}
                        </p>
                      </div>
                      <a
                        href={resolveAdminUrl(file.download_url)}
                        className="inline-flex items-center rounded-lg border border-sky-200 bg-white px-3 py-1.5 text-xs font-medium text-sky-800 transition hover:bg-sky-50"
                      >
                        下载
                      </a>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
          <div data-testid="marker-llm-panel" className="mt-4 rounded-2xl border border-slate-200 bg-slate-50/80 p-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">导入增强服务</p>
                <p className="mt-1 text-[11px] text-slate-600">用于同步 Marker `--use_llm` 配置，并在保存后回显运行态。仅在 Marker 总开关开启时生效。</p>
              </div>
              <label className="inline-flex items-center gap-2 text-xs font-medium text-slate-700">
                <input
                  data-testid="marker-llm-use-toggle"
                  type="checkbox"
                  checked={markerLlm.use_llm}
                  onChange={(event) => setMarkerLlmField('use_llm', event.target.checked)}
                />
                启用导入增强
              </label>
            </div>
            <label className="mt-3 block text-xs font-medium text-slate-600">
              服务类型
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
            {markerEnabled && markerLlm.use_llm ? (
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
                          来源: {formatRuntimeSource(pipelineConfig.effective_source.marker_llm[field])}
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
              <p className="mt-3 text-[11px] text-slate-500">
                {markerEnabled ? '关闭后仍保留已保存字段，但导入链路不会请求 Marker LLM 增强。' : 'Marker 总开关关闭时保留已保存字段，但当前不会尝试任何 Marker 增强。'}
              </p>
            )}
            <div className="mt-3 rounded-xl border border-dashed border-slate-200 bg-white p-2 text-[11px] text-slate-600">
              <p className="font-medium text-slate-700">当前生效导入增强摘要</p>
              <p className="mt-1">
                状态: {runtimeOverview?.pipeline.marker_llm?.status || 'disabled'} · 配置完整:{' '}
                {runtimeOverview?.pipeline.marker_llm?.configured ? 'yes' : 'no'}
              </p>
              <ul className="mt-1 space-y-0.5">
                {(runtimeOverview?.pipeline.marker_llm?.summary_fields ?? []).map((item) => (
                  <li key={item.field}>
                    {item.field}: <span className="font-mono">{item.value}</span>{' '}
                    <span className="text-slate-400">({formatRuntimeSource(item.source)})</span>
                  </li>
                ))}
                {!(runtimeOverview?.pipeline.marker_llm?.summary_fields ?? []).length ? <li>暂无额外字段摘要</li> : null}
              </ul>
            </div>
          </div>
          {pipelineStatusText ? <p className="mt-2 text-xs text-emerald-700">{pipelineStatusText}</p> : null}
          {pipelineGlobalError ? <p className="mt-2 text-xs text-rose-600">{pipelineGlobalError}</p> : null}
        </article>

        <article data-testid="planner-runtime-panel" className="xl:col-span-2 rounded-[28px] border border-amber-200 bg-[linear-gradient(135deg,#fff8ef,#ffffff_52%,#fff7d6)] p-6 shadow-[0_18px_50px_rgba(15,23,42,0.05)]">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-amber-700">对话路线模型</p>
              <h3 className="mt-2 text-xl font-semibold text-slate-950">对话如何组织，主要看这里</h3>
              <p className="mt-2 text-sm leading-6 text-slate-600">
                这块决定系统会不会先想一步，再决定澄清、继续检索还是直接回答。因为它会影响整个回答路径，所以单独放在这里。
              </p>
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                data-testid="planner-detect-btn"
                onClick={() => void handleDetectPlannerModel()}
                disabled={controlsDisabled || plannerDetectLoading || !plannerConfig.apiBase.trim() || !plannerConfig.apiKey.trim()}
                className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {plannerDetectLoading ? '检测中...' : '测试连接'}
              </button>
              <button
                type="button"
                data-testid="planner-save-btn"
                onClick={() => void handleSavePlanner()}
                disabled={controlsDisabled || plannerSaveLoading}
                className="rounded-lg border border-amber-200 bg-amber-100 px-3 py-1.5 text-xs font-medium text-amber-900 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {plannerSaveLoading ? '保存中...' : '保存规划模型'}
              </button>
            </div>
          </div>

          <div className="mt-4 rounded-2xl border border-amber-200/70 bg-white/80 p-4">
            <p className="text-[11px] leading-5 text-slate-600">
              中文说明：
              正式模式下，聊天会先看这里能不能工作；诊断模式只用于排查，不代表用户真的能正常对话。
            </p>
          </div>

          <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <label className="block text-xs font-medium text-slate-600">
              运行模式
              <select
                data-testid="planner-service-mode-select"
                value={plannerConfig.serviceMode}
                onChange={(event) => setPlannerField('serviceMode', event.target.value as PlannerConfigForm['serviceMode'])}
                disabled={controlsDisabled}
                className="mt-1 h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-800 outline-none ring-amber-300 transition focus:ring-2"
              >
                <option value="production">正式模式</option>
                <option value="diagnostic">诊断模式</option>
              </select>
            </label>
            <label className="block text-xs font-medium text-slate-600">
              服务商
              <select
                data-testid="planner-provider-select"
                value={plannerConfig.provider}
                onChange={(event) => {
                  const provider = event.target.value;
                  setPlannerConfig((prev) => ({
                    ...prev,
                    provider,
                    apiBase: providerPresets[provider]?.apiBase ?? prev.apiBase
                  }));
                }}
                disabled={controlsDisabled}
                className="mt-1 h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-800 outline-none ring-amber-300 transition focus:ring-2"
              >
                {providerOptions.map((provider) => (
                  <option key={`planner-${provider.value}`} value={provider.value}>
                    {provider.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="block text-xs font-medium text-slate-600">
              服务地址
              <input
                data-testid="planner-api-base-input"
                value={plannerConfig.apiBase}
                onChange={(event) => setPlannerField('apiBase', event.target.value)}
                disabled={controlsDisabled}
                className="mt-1 h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-800 outline-none ring-amber-300 transition focus:ring-2"
              />
            </label>
            <label className="block text-xs font-medium text-slate-600">
              访问密钥
              <input
                data-testid="planner-api-key-input"
                type="password"
                value={plannerConfig.apiKey}
                onChange={(event) => setPlannerField('apiKey', event.target.value)}
                disabled={controlsDisabled}
                placeholder={plannerPersisted.apiKey ? '已保存，如需更新请重新填写' : 'sk-...'}
                className="mt-1 h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-800 outline-none ring-amber-300 transition focus:ring-2"
              />
            </label>
            <label className="block text-xs font-medium text-slate-600">
              模型名称
              <select
                data-testid="planner-model-select"
                value={plannerConfig.model}
                onChange={(event) => setPlannerField('model', event.target.value)}
                disabled={controlsDisabled}
                className="mt-1 h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-800 outline-none ring-amber-300 transition focus:ring-2"
              >
                <option value="">请选择模型</option>
                {plannerModels.map((model) => (
                  <option key={`planner-${model.id}`} value={model.id}>
                    {model.id}
                  </option>
                ))}
              </select>
            </label>
            <label className="block text-xs font-medium text-slate-600">
              超时时间（毫秒）
              <input
                data-testid="planner-timeout-input"
                type="number"
                min={1000}
                value={plannerConfig.timeoutMs}
                onChange={(event) => setPlannerField('timeoutMs', Number(event.target.value) || defaultPlannerConfig.timeoutMs)}
                disabled={controlsDisabled}
                className="mt-1 h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-800 outline-none ring-amber-300 transition focus:ring-2"
              />
            </label>
          </div>
          <div className="mt-4 rounded-xl border border-dashed border-amber-200 bg-white/80 p-4 text-[11px] text-slate-600">
            <p className="font-medium text-slate-800">当前生效配置</p>
            <p className="mt-1">
              模式: {runtimeOverview?.planner?.service_mode === 'diagnostic' ? '诊断模式' : '正式模式'} · 来源: {formatRuntimeSource(runtimeOverview?.planner?.source)}
            </p>
            <p className="mt-1 break-all font-mono">
              {(runtimeOverview?.planner?.provider || '-') +
                ' / ' +
                (runtimeOverview?.planner?.model || '-') +
                ' / ' +
                String(runtimeOverview?.planner?.timeout_ms ?? defaultPlannerConfig.timeoutMs)}
            </p>
            <p className="mt-1">
              正式聊天可用: {runtimeOverview?.planner?.formal_chat_available ? '是' : '否'}
              {runtimeOverview?.planner?.block_reason_message ? ` · ${runtimeOverview.planner.block_reason_message}` : ''}
            </p>
          </div>
          {plannerStatusText ? <p className="mt-2 text-xs text-emerald-700">{plannerStatusText}</p> : null}
          {plannerGlobalError ? <p data-testid="planner-error" className="mt-2 text-xs text-rose-600">{plannerGlobalError}</p> : null}
        </article>
      </section>

      <section className="mb-4">
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">可编辑配置</p>
        <h3 className="mt-2 text-xl font-semibold text-slate-950">按模型分别调整，需要时再单独保存</h3>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
          下面每张卡片对应一路可在线调整的模型。修改后可以只保存当前卡片，不会把其他卡片里还没确认的改动一起提交。
        </p>
      </section>

      <div className="grid gap-4 xl:grid-cols-3">
        {stageMeta.map((stage) => {
          const item = configs[stage.key];
          const inherited = isInheritMode(stage.key);
          const showUnsaved = (field: keyof DraftConfig) => dirtyFieldsByStage[stage.key]?.[field];
          return (
            <article key={stage.key} className="magic-card rounded-2xl p-[1px]">
              <div className="h-full rounded-2xl bg-white p-4">
                <div className="mb-3 flex items-start justify-between gap-2">
                  <h3 className="text-sm font-semibold text-slate-900">{stage.title}</h3>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      data-testid={`llm-${stage.key}-detect-btn`}
                      onClick={() => void handleDetectModels(stage.key)}
                      disabled={
                        controlsDisabled ||
                        item.detectLoading ||
                        item.saveLoading ||
                        !(inherited ? configs.answer.apiBase : item.apiBase).trim() ||
                        !(inherited ? configs.answer.apiKey : item.apiKey).trim()
                      }
                      className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {item.detectLoading ? '检测中...' : '测试连接'}
                    </button>
                    <button
                      type="button"
                      data-testid={`llm-${stage.key}-save-btn`}
                      onClick={() => void handleSaveStage(stage.key)}
                      disabled={controlsDisabled || item.saveLoading}
                      className="rounded-lg border border-sky-200 bg-sky-50 px-3 py-1.5 text-xs font-medium text-sky-700 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {item.saveLoading ? '保存中...' : '保存本模型'}
                    </button>
                  </div>
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
                {item.status ? (
                  <p data-testid={`llm-${stage.key}-status`} className="mt-2 text-xs text-emerald-700">
                    {item.status}
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
          {saveLoading ? '保存中...' : '保存全部模型'}
        </button>
        <span className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs text-slate-600">每张卡片都可单独保存；顶部按钮会一次保存全部</span>
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
          </div>
        </div>
      </div>
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
