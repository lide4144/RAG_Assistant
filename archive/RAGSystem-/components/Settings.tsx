import React, { useState, useEffect } from 'react';
import { User, Cpu, Database, Key, Save, RefreshCw, Eye, EyeOff, CheckCircle2, AlertCircle, Box, Globe, Link } from 'lucide-react';

type SettingsTab = 'account' | 'llm' | 'rag';

interface ModelOption {
  id: string;
  name: string;
  contextWindow: string;
}

interface ProviderConfig {
  id: string;
  name: string;
  defaultBaseUrl: string;
  defaultModels: ModelOption[]; // Fallback or preset models
}

// Configuration Presets
const PROVIDERS: ProviderConfig[] = [
  {
    id: 'openai',
    name: 'OpenAI',
    defaultBaseUrl: 'https://api.openai.com/v1',
    defaultModels: [
      { id: 'gpt-4-turbo', name: 'GPT-4 Turbo', contextWindow: '128k' },
      { id: 'gpt-4o', name: 'GPT-4o', contextWindow: '128k' },
    ]
  },
  {
    id: 'anthropic',
    name: 'Anthropic',
    defaultBaseUrl: 'https://api.anthropic.com/v1',
    defaultModels: [
      { id: 'claude-3-opus', name: 'Claude 3 Opus', contextWindow: '200k' },
      { id: 'claude-3-5-sonnet', name: 'Claude 3.5 Sonnet', contextWindow: '200k' },
    ]
  },
  {
    id: 'google',
    name: 'Google Gemini',
    defaultBaseUrl: 'https://generativelanguage.googleapis.com/v1beta',
    defaultModels: [
      { id: 'gemini-1.5-pro', name: 'Gemini 1.5 Pro', contextWindow: '1M' },
    ]
  },
  {
    id: 'local',
    name: 'Local / Ollama',
    defaultBaseUrl: 'http://localhost:11434/v1',
    defaultModels: [
      { id: 'llama3', name: 'Llama 3 (Local)', contextWindow: '8k' },
    ]
  },
  {
    id: 'custom',
    name: 'Custom / Compatible',
    defaultBaseUrl: '',
    defaultModels: []
  }
];

const ProviderLogo: React.FC<{ providerId: string; className?: string }> = ({ providerId, className }) => {
  switch (providerId) {
    case 'openai':
      return (
        <svg viewBox="0 0 24 24" fill="currentColor" className={className}>
          <path d="M22.2819 9.8211a5.9847 5.9847 0 0 0-.5157-4.9108 6.0462 6.0462 0 0 0-6.5098-2.9A6.0651 6.0651 0 0 0 4.9807 4.1818a5.9847 5.9847 0 0 0-3.9977 2.9 6.0462 6.0462 0 0 0 .7427 7.0966 5.98 5.98 0 0 0 .511 4.9107 6.0462 6.0462 0 0 0 6.5146 2.9001A5.9847 5.9847 0 0 0 13.2599 24a6.0557 6.0557 0 0 0 5.7718-4.2058 5.9894 5.9894 0 0 0 3.9977-2.9001 6.0557 6.0557 0 0 0-.7475-7.0729zm-9.022 12.6081a4.4755 4.4755 0 0 1-2.8764-1.0408l.1419-.0804 4.7783-2.7582a.7948.7948 0 0 0 .3927-.6813v-6.7369l2.02 1.1686a.071.071 0 0 1 .038.052v5.5826a4.504 4.504 0 0 1-4.4945 4.4944zm-9.6607-4.1254a4.4708 4.4708 0 0 1-.5346-3.0137l.142.0852 4.783 2.7582a.7712.7712 0 0 0 .7806 0l5.8428-3.3685v2.3324a.0804.0804 0 0 1-.0332.0615L9.74 19.9502a4.4992 4.4992 0 0 1-6.1408-1.6464zM2.3408 7.8956a4.485 4.485 0 0 1 2.3655-1.9728V11.6a.7664.7664 0 0 0 .3879.6765l5.8144 3.3543-2.0201 1.1685a.0757.0757 0 0 1-.071 0l-4.8303-2.7865A4.504 4.504 0 0 1 2.3408 7.872zm16.5963 3.8558L13.1038 8.364 15.1195 7.2a.0757.0757 0 0 1 .071 0l4.8303 2.7913a4.4944 4.4944 0 0 1-.6765 8.1042v-5.6772a.79.79 0 0 0-.407-.667zm2.0107-3.0231l-.142-.0852-4.7735-2.7818a.7759.7759 0 0 0-.7854 0L9.409 9.2297V6.8974a.0662.0662 0 0 1 .0284-.0615l4.8303-2.7866a4.4992 4.4992 0 0 1 6.6802 4.66zM8.3065 12.863l-2.02-1.1638a.0804.0804 0 0 1-.038-.0567V6.0742a4.4992 4.4992 0 0 1 7.3757-3.453l-.142.0805L8.704 5.4596a.7948.7948 0 0 0-.3927.6813zm1.0976-2.3654l3.1028-1.7999 3.1028 1.7999v3.5916l-3.1028 1.8-3.1028-1.8z" />
        </svg>
      );
    case 'anthropic':
      return (
        <svg viewBox="0 0 24 24" fill="currentColor" className={className}>
          <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8z" opacity="0.5"/>
          <path d="M12 6L16.5 16H14.5L13.4 13.5H10.6L9.5 16H7.5L12 6ZM12.9 12L12 9.5L11.1 12H12.9Z" fill="currentColor" />
        </svg>
      );
    case 'google':
      return (
        <svg viewBox="0 0 24 24" fill="currentColor" className={className}>
          <path d="M21.363 8.769h-9.827v4.061h6.059a5.558 5.558 0 0 1-2.35 3.666v2.793h3.639c2.235-2.057 3.427-5.23 3.427-8.688 0-.847-.07-1.428-.198-1.832z" className="text-blue-400" fill="currentColor"/>
          <path d="M11.536 19.33c2.766 0 5.066-.9 6.744-2.433l-3.639-2.793c-1.002.695-2.222 1.056-3.105 1.056-2.454 0-4.524-1.636-5.275-3.836H2.435v2.738c1.722 3.402 5.253 5.268 9.101 5.268z" className="text-green-400" fill="currentColor"/>
          <path d="M6.261 11.324c-.183-.55-.285-1.139-.285-1.748 0-.609.102-1.198.285-1.748V5.09H2.435C1.037 7.868 1.037 11.282 2.435 14.06l3.826-2.736z" className="text-yellow-400" fill="currentColor"/>
          <path d="M11.536 4.821c1.94 0 3.327.832 4.092 1.545l2.977-2.924C16.666 1.624 14.301.667 11.536.667c-3.848 0-7.379 1.866-9.101 5.268l3.826 2.736c.751-2.2 2.821-3.85 5.275-3.85z" className="text-red-400" fill="currentColor"/>
        </svg>
      );
    case 'local':
      return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
          <rect x="2" y="4" width="20" height="16" rx="2" />
          <path d="M6 10l2 2-2 2" />
          <path d="M10 14h4" />
        </svg>
      );
    case 'custom':
      return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
           <circle cx="12" cy="12" r="10"/>
           <line x1="2" x2="22" y1="12" y2="12"/>
           <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>
        </svg>
      );
    default:
      return <Cpu className={className} />;
  }
};

const Settings: React.FC = () => {
  const [activeTab, setActiveTab] = useState<SettingsTab>('llm');

  const tabs: { id: SettingsTab; label: string; icon: any }[] = [
    { id: 'llm', label: '模型与接口', icon: Cpu },
    { id: 'rag', label: 'RAG 引擎', icon: Database },
    { id: 'account', label: '个人账户', icon: User },
  ];

  return (
    <div className="p-8 h-full animate-fade-in flex flex-col">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-white tracking-tight mb-2">系统设置</h1>
        <p className="text-slate-400">管理模型连接、RAG 参数及个人偏好。</p>
      </div>

      <div className="flex-1 flex gap-8 min-h-0">
        {/* Left Sidebar Navigation */}
        <div className="w-64 flex flex-col gap-2 shrink-0">
          {tabs.map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium transition-all duration-200
                ${activeTab === tab.id 
                  ? 'bg-gradient-to-r from-cyan-500/20 to-transparent border-l-2 border-cyan-400 text-white' 
                  : 'text-slate-400 hover:text-white hover:bg-white/5 border-l-2 border-transparent'
                }`}
            >
              <tab.icon className={`w-5 h-5 ${activeTab === tab.id ? 'text-cyan-400' : ''}`} />
              {tab.label}
            </button>
          ))}
        </div>

        {/* Right Content Area */}
        <div className="flex-1 bg-slate-900/50 backdrop-blur-sm rounded-3xl border border-white/5 overflow-hidden flex flex-col relative">
          <div className="absolute top-0 right-0 w-96 h-96 bg-cyan-500/5 rounded-full blur-3xl pointer-events-none -mr-32 -mt-32"></div>
          
          <div className="flex-1 overflow-y-auto p-8 custom-scrollbar relative z-10">
            {activeTab === 'account' && <AccountSettings />}
            {activeTab === 'llm' && <LLMSettings />}
            {activeTab === 'rag' && <RagSettings />}
          </div>

          {/* Action Footer */}
          <div className="p-6 border-t border-white/5 bg-slate-900/80 backdrop-blur flex justify-end gap-4 z-10">
            <button className="px-6 py-2 rounded-xl text-sm font-medium text-slate-400 hover:text-white transition-colors">
              重置默认
            </button>
            <button className="px-6 py-2 rounded-xl text-sm font-medium bg-cyan-500 hover:bg-cyan-400 text-white shadow-lg shadow-cyan-500/20 flex items-center gap-2 transition-all active:scale-95">
              <Save className="w-4 h-4" />
              保存更改
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

// --- Sub Components ---

const SectionTitle: React.FC<{ title: string; desc: string }> = ({ title, desc }) => (
  <div className="mb-6">
    <h2 className="text-xl font-semibold text-white mb-1">{title}</h2>
    <p className="text-sm text-slate-500">{desc}</p>
  </div>
);

const InputGroup: React.FC<{ label: string; children: React.ReactNode; subLabel?: string }> = ({ label, children, subLabel }) => (
  <div className="space-y-2">
    <div className="flex justify-between">
      <label className="block text-sm font-medium text-slate-300">{label}</label>
      {subLabel && <span className="text-xs text-slate-500">{subLabel}</span>}
    </div>
    {children}
  </div>
);

const LLMSettings = () => {
  const [selectedProvider, setSelectedProvider] = useState('openai');
  const [baseUrl, setBaseUrl] = useState('https://api.openai.com/v1');
  const [apiKey, setApiKey] = useState('');
  const [showKey, setShowKey] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState<'idle' | 'loading' | 'success' | 'error'>('idle');
  const [availableModels, setAvailableModels] = useState<ModelOption[]>([]);
  const [selectedModel, setSelectedModel] = useState('');
  
  // Params
  const [temp, setTemp] = useState(0.7);
  const [maxTokens, setMaxTokens] = useState(2048);

  // Initialize Base URL when provider changes
  useEffect(() => {
    const provider = PROVIDERS.find(p => p.id === selectedProvider);
    if (provider) {
      setBaseUrl(provider.defaultBaseUrl);
      setApiKey(''); // Clear key for security when switching providers
      setConnectionStatus('idle');
      setAvailableModels([]);
      setSelectedModel('');
    }
  }, [selectedProvider]);

  // Simulate Backend API Verification & Model Fetching
  const verifyAndFetchModels = () => {
    if (!baseUrl) {
      setConnectionStatus('error');
      return;
    }

    setConnectionStatus('loading');
    
    // Simulate Network Request latency
    setTimeout(() => {
      // MOCK LOGIC: In a real app, this would be a fetch to the backend
      // which proxies the request to `${baseUrl}/models`
      
      let fetchedModels: ModelOption[] = [];
      const provider = PROVIDERS.find(p => p.id === selectedProvider);
      
      if (selectedProvider === 'custom') {
        // Mocking a response for a custom provider (e.g., DeepSeek, Moonshot)
        fetchedModels = [
          { id: 'custom-model-v1', name: 'Custom Model V1 (7B)', contextWindow: '32k' },
          { id: 'custom-model-chat', name: 'Custom Chat Alpha', contextWindow: '16k' },
          { id: 'deepseek-coder', name: 'DeepSeek Coder', contextWindow: '128k' },
        ];
      } else if (provider) {
        fetchedModels = provider.defaultModels;
      }

      if (Math.random() > 0.1) { // 90% success rate simulation
        setAvailableModels(fetchedModels);
        if (fetchedModels.length > 0) {
          setSelectedModel(fetchedModels[0].id);
        }
        setConnectionStatus('success');
      } else {
        setConnectionStatus('error');
      }
    }, 1200);
  };

  return (
    <div className="max-w-3xl space-y-10 animate-fade-in">
      {/* 1. Provider Selection */}
      <div>
        <SectionTitle title="LLM 来源配置" desc="选择预设提供商或配置自定义兼容接口。" />
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          {PROVIDERS.map((provider) => {
             const isSelected = selectedProvider === provider.id;
             return (
              <button
                key={provider.id}
                onClick={() => setSelectedProvider(provider.id)}
                className={`relative p-3 rounded-xl border flex flex-col items-center gap-2 transition-all duration-200
                  ${isSelected 
                    ? 'bg-cyan-500/10 border-cyan-500/50 shadow-[0_0_20px_rgba(6,182,212,0.15)]' 
                    : 'bg-slate-800/50 border-white/5 hover:bg-slate-800 hover:border-white/10'
                  }`}
              >
                <div className={`p-2 rounded-lg ${isSelected ? 'bg-cyan-500 text-white' : 'bg-slate-700 text-slate-400'}`}>
                  <ProviderLogo providerId={provider.id} className="w-6 h-6" />
                </div>
                <span className={`text-xs font-medium text-center ${isSelected ? 'text-white' : 'text-slate-400'}`}>{provider.name}</span>
                {isSelected && (
                  <div className="absolute top-2 right-2 w-1.5 h-1.5 rounded-full bg-cyan-400 shadow-[0_0_8px_rgba(34,211,238,0.8)]"></div>
                )}
              </button>
             );
          })}
        </div>
      </div>

      {/* 2. Connection Details */}
      <div className="p-6 rounded-2xl bg-white/5 border border-white/5 space-y-6 relative overflow-hidden">
         {/* Background decoration */}
         <div className="absolute top-0 right-0 w-64 h-64 bg-cyan-500/5 rounded-full blur-3xl -mr-32 -mt-32 pointer-events-none"></div>

         <div className="flex items-center justify-between relative z-10">
           <h3 className="text-lg font-medium text-white flex items-center gap-2">
             <Link className="w-5 h-5 text-slate-400" />
             接口连接参数
           </h3>
           <div className={`flex items-center gap-2 text-xs font-medium px-3 py-1 rounded-full border transition-all duration-300
             ${connectionStatus === 'success' ? 'bg-green-500/20 border-green-500/30 text-green-400' : 
               connectionStatus === 'error' ? 'bg-red-500/20 border-red-500/30 text-red-400' : 
               'bg-slate-800/50 border-white/10 text-slate-400'}`}>
             {connectionStatus === 'success' && <CheckCircle2 className="w-3.5 h-3.5" />}
             {connectionStatus === 'error' && <AlertCircle className="w-3.5 h-3.5" />}
             {connectionStatus === 'loading' && <RefreshCw className="w-3.5 h-3.5 animate-spin" />}
             {connectionStatus === 'idle' && <div className="w-2 h-2 rounded-full bg-slate-500" />}
             <span>
               {connectionStatus === 'idle' ? '未连接' : 
                connectionStatus === 'loading' ? '正在获取模型列表...' : 
                connectionStatus === 'success' ? '已连接' : '连接失败'}
             </span>
           </div>
         </div>

         <div className="space-y-4 relative z-10">
            {/* Base URL Input */}
            <div className="space-y-2">
              <label className="text-sm font-medium text-slate-300 flex justify-between">
                <span>API Base URL</span>
                <span className="text-xs text-slate-500">后端将通过此地址获取模型</span>
              </label>
              <div className="relative group">
                <div className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500 group-focus-within:text-cyan-400 transition-colors">
                  <Globe className="w-4 h-4" />
                </div>
                <input 
                  type="text" 
                  value={baseUrl}
                  onChange={(e) => setBaseUrl(e.target.value)}
                  placeholder="e.g. https://api.openai.com/v1"
                  className="w-full bg-slate-900/50 border border-white/10 rounded-xl pl-10 pr-4 py-3 text-white focus:outline-none focus:border-cyan-500/50 font-mono text-sm transition-all"
                />
              </div>
            </div>

            {/* API Key Input */}
            <div className="flex gap-4 items-end">
              <div className="flex-1 space-y-2">
                <label className="text-sm font-medium text-slate-300">API Key</label>
                <div className="relative group">
                  <div className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500 group-focus-within:text-cyan-400 transition-colors">
                    <Key className="w-4 h-4" />
                  </div>
                  <input 
                    type={showKey ? "text" : "password"} 
                    value={apiKey}
                    onChange={(e) => setApiKey(e.target.value)}
                    placeholder={selectedProvider === 'local' ? "本地模式通常无需 Key" : "sk-..."}
                    className={`w-full bg-slate-900/50 border rounded-xl pl-10 pr-12 py-3 text-white focus:outline-none font-mono text-sm transition-all
                      ${connectionStatus === 'error' ? 'border-red-500/50 focus:border-red-500' : 'border-white/10 focus:border-cyan-500/50'}
                    `}
                  />
                  <button 
                    onClick={() => setShowKey(!showKey)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-white transition-colors"
                  >
                    {showKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
              </div>
              <button 
                onClick={verifyAndFetchModels}
                disabled={connectionStatus === 'loading' || !baseUrl}
                className="px-6 py-3 rounded-xl bg-slate-800 hover:bg-slate-700 hover:text-white text-slate-300 font-medium text-sm border border-white/10 transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2 min-w-[140px] justify-center shadow-lg active:scale-95"
              >
                {connectionStatus === 'loading' ? (
                  <RefreshCw className="w-4 h-4 animate-spin" />
                ) : (
                  <>
                    <RefreshCw className="w-4 h-4" />
                    获取模型列表
                  </>
                )}
              </button>
            </div>
         </div>
      </div>

      {/* 3. Model Configuration (Conditional) */}
      {availableModels.length > 0 && (
        <div className="space-y-8 animate-fade-in-up">
          <SectionTitle title="模型参数配置" desc="从获取到的列表中选择模型并调整参数。" />
          
          <InputGroup label="选择模型 (Model)">
            <div className="relative">
              <select 
                value={selectedModel}
                onChange={(e) => setSelectedModel(e.target.value)}
                className="w-full bg-slate-800/50 border border-white/10 rounded-xl px-4 py-3 text-white focus:outline-none focus:border-cyan-500/50 appearance-none"
              >
                {availableModels.map(model => (
                  <option key={model.id} value={model.id}>
                    {model.name} (Context: {model.contextWindow})
                  </option>
                ))}
              </select>
              <div className="absolute right-4 top-1/2 -translate-y-1/2 pointer-events-none text-slate-400">
                <Box className="w-4 h-4" />
              </div>
            </div>
          </InputGroup>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
            <div className="space-y-4 p-5 bg-white/5 rounded-2xl border border-white/5">
              <div className="flex justify-between items-center">
                 <label className="text-sm font-medium text-slate-200">温度 (Temperature)</label>
                 <span className="text-cyan-400 font-mono text-sm">{temp}</span>
              </div>
              <input 
                type="range" 
                min="0" 
                max="2" 
                step="0.1" 
                value={temp} 
                onChange={(e) => setTemp(parseFloat(e.target.value))}
                className="w-full h-2 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-cyan-500" 
              />
              <p className="text-xs text-slate-500 leading-relaxed">
                控制输出的随机性。0 为最确定，2 为最具创造性。
              </p>
            </div>

            <div className="space-y-4 p-5 bg-white/5 rounded-2xl border border-white/5">
               <div className="flex justify-between items-center">
                 <label className="text-sm font-medium text-slate-200">最大 Token (Max Tokens)</label>
                 <span className="text-cyan-400 font-mono text-sm">{maxTokens}</span>
              </div>
               <input 
                type="range" 
                min="256" 
                max="8192" 
                step="256" 
                value={maxTokens} 
                onChange={(e) => setMaxTokens(parseFloat(e.target.value))}
                className="w-full h-2 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-cyan-500" 
              />
              <p className="text-xs text-slate-500 leading-relaxed">
                限制单次响应生成的最大长度。设置过低可能导致回答被截断。
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

const RagSettings = () => {
  const [chunkSize, setChunkSize] = useState(512);
  const [overlap, setOverlap] = useState(50);
  const [topK, setTopK] = useState(5);

  return (
    <div className="max-w-2xl space-y-8 animate-fade-in">
      <SectionTitle title="RAG 引擎设置" desc="调整文档切片策略和检索召回参数。" />

      <div className="space-y-8">
        {/* Indexing Strategy */}
        <div className="space-y-6">
          <h3 className="text-sm uppercase tracking-wider text-slate-400 font-bold border-b border-white/5 pb-2">索引策略</h3>
          
          <div className="space-y-4">
            <div className="flex justify-between">
              <label className="text-sm font-medium text-slate-200">切片大小 (Chunk Size)</label>
              <span className="text-cyan-400 font-mono text-sm">{chunkSize} chars</span>
            </div>
            <input 
              type="range" min="128" max="2048" step="64" value={chunkSize} onChange={(e) => setChunkSize(parseInt(e.target.value))}
              className="w-full h-2 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-cyan-500" 
            />
          </div>

          <div className="space-y-4">
            <div className="flex justify-between">
              <label className="text-sm font-medium text-slate-200">重叠大小 (Chunk Overlap)</label>
              <span className="text-cyan-400 font-mono text-sm">{overlap} chars</span>
            </div>
            <input 
              type="range" min="0" max="200" step="10" value={overlap} onChange={(e) => setOverlap(parseInt(e.target.value))}
              className="w-full h-2 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-cyan-500" 
            />
          </div>
        </div>

        {/* Retrieval Strategy */}
        <div className="space-y-6 pt-6">
           <h3 className="text-sm uppercase tracking-wider text-slate-400 font-bold border-b border-white/5 pb-2">检索策略</h3>
           
           <div className="flex items-center justify-between p-4 bg-white/5 rounded-xl border border-white/5">
             <div>
               <div className="text-sm font-medium text-white">混合检索 (Hybrid Search)</div>
               <div className="text-xs text-slate-500">结合关键词搜索与向量语义检索以提高准确性</div>
             </div>
             <div className="relative inline-flex items-center cursor-pointer">
               <input type="checkbox" defaultChecked className="sr-only peer" />
               <div className="w-11 h-6 bg-slate-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full rtl:peer-checked:after:-translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:start-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-cyan-500"></div>
             </div>
           </div>

           <div className="space-y-4">
            <div className="flex justify-between">
              <label className="text-sm font-medium text-slate-200">召回数量 (Top K)</label>
              <span className="text-cyan-400 font-mono text-sm">{topK} docs</span>
            </div>
            <input 
              type="range" min="1" max="20" step="1" value={topK} onChange={(e) => setTopK(parseInt(e.target.value))}
              className="w-full h-2 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-cyan-500" 
            />
          </div>
        </div>
      </div>
    </div>
  );
};

const AccountSettings = () => (
  <div className="max-w-2xl space-y-8 animate-fade-in">
    <SectionTitle title="个人资料" desc="更新您的个人信息和登录凭证。" />
    
    <div className="flex items-center gap-6 mb-8">
      <div className="w-24 h-24 rounded-full bg-gradient-to-tr from-purple-500 to-indigo-500 flex items-center justify-center text-3xl font-bold text-white shadow-xl ring-4 ring-slate-800">
        JD
      </div>
      <div>
        <button className="px-4 py-2 bg-white/10 hover:bg-white/20 text-white text-sm font-medium rounded-lg transition-colors border border-white/10">
          更换头像
        </button>
        <p className="text-xs text-slate-500 mt-2">支持 JPG, PNG 格式，最大 2MB</p>
      </div>
    </div>

    <div className="grid grid-cols-2 gap-6">
      <InputGroup label="显示名称">
        <input type="text" defaultValue="John Doe" className="w-full bg-slate-800/50 border border-white/10 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:border-cyan-500/50 focus:ring-1 focus:ring-cyan-500/20 transition-all" />
      </InputGroup>
      <InputGroup label="电子邮箱">
        <input type="email" defaultValue="john.doe@research.lab" disabled className="w-full bg-slate-900/50 border border-white/5 rounded-xl px-4 py-2.5 text-slate-400 cursor-not-allowed" />
      </InputGroup>
    </div>

    <div className="pt-6 border-t border-white/5">
       <h3 className="text-lg font-medium text-white mb-4">修改密码</h3>
       <div className="grid grid-cols-2 gap-6">
        <InputGroup label="当前密码">
          <input type="password" placeholder="••••••••" className="w-full bg-slate-800/50 border border-white/10 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:border-cyan-500/50 transition-all" />
        </InputGroup>
        <InputGroup label="新密码">
          <input type="password" placeholder="••••••••" className="w-full bg-slate-800/50 border border-white/10 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:border-cyan-500/50 transition-all" />
        </InputGroup>
       </div>
    </div>
  </div>
);

export default Settings;