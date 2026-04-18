import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { X, Key, Server, Brain, Check, AlertCircle, Eye, EyeOff, RefreshCw, ChevronDown, Loader2, Search } from 'lucide-react';
import {
  loadSettings,
  saveSettings,
  getProviderDisplayName,
  fetchOpenRouterModels,
} from '../core/llm/settings-service';
import type { LLMSettings, LLMProvider } from '../core/llm/types';

interface SettingsPanelProps {
  isOpen: boolean;
  onClose: () => void;
  onSettingsSaved?: () => void;
  backendUrl?: string;
  isBackendConnected?: boolean;
  onBackendUrlChange?: (url: string) => void;
}

/**
 * Searchable combobox for OpenRouter model selection
 */
interface OpenRouterModelComboboxProps {
  value: string;
  onChange: (model: string) => void;
  models: Array<{ id: string; name: string }>;
  isLoading: boolean;
  onLoadModels: () => void;
}

const OpenRouterModelCombobox = ({ value, onChange, models, isLoading, onLoadModels }: OpenRouterModelComboboxProps) => {
  const [isOpen, setIsOpen] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Filter models based on search term
  const filteredModels = useMemo(() => {
    if (!searchTerm.trim()) return models;
    const lower = searchTerm.toLowerCase();
    return models.filter(m =>
      m.id.toLowerCase().includes(lower) ||
      m.name.toLowerCase().includes(lower)
    );
  }, [models, searchTerm]);

  // Find display name for current value
  const displayValue = useMemo(() => {
    if (!value) return '';
    const found = models.find(m => m.id === value);
    return found ? found.name : value;
  }, [value, models]);

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
        setSearchTerm('');
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Load models when opening
  const handleOpen = () => {
    setIsOpen(true);
    if (models.length === 0 && !isLoading) {
      onLoadModels();
    }
    setTimeout(() => inputRef.current?.focus(), 10);
  };

  const handleSelect = (modelId: string) => {
    onChange(modelId);
    setIsOpen(false);
    setSearchTerm('');
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value;
    setSearchTerm(val);
    // Also allow direct typing of model ID
    if (val && models.length === 0) {
      onChange(val);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && searchTerm) {
      // If exact match in filtered, select it; otherwise use raw input
      const exact = filteredModels.find(m => m.id.toLowerCase() === searchTerm.toLowerCase());
      if (exact) {
        handleSelect(exact.id);
      } else if (filteredModels.length === 1) {
        handleSelect(filteredModels[0].id);
      } else {
        // Allow custom model ID input
        onChange(searchTerm);
        setIsOpen(false);
        setSearchTerm('');
      }
    } else if (e.key === 'Escape') {
      setIsOpen(false);
      setSearchTerm('');
    }
  };

  return (
    <div ref={containerRef} className="relative">
      {/* Main input/button */}
      <button
        type="button"
        onClick={handleOpen}
        className={`w-full px-4 py-3 bg-elevated border rounded-xl cursor-pointer transition-all flex items-center gap-2
          ${isOpen ? 'border-accent ring-2 ring-accent/20' : 'border-border-subtle hover:border-accent/50'}`}
      >
        {isOpen ? (
          <input
            ref={inputRef}
            type="text"
            value={searchTerm}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            placeholder="搜索或输入模型 ID…"
            className="flex-1 bg-transparent text-text-primary placeholder:text-text-muted outline-none font-mono text-sm"
            onClick={e => e.stopPropagation()}
          />
        ) : (
          <span className={`flex-1 font-mono text-sm truncate ${value ? 'text-text-primary' : 'text-text-muted'}`}>
            {displayValue || '选择模型，或直接输入模型 ID…'}
          </span>
        )}
        <div className="flex items-center gap-1">
          {isLoading && <Loader2 className="w-4 h-4 animate-spin text-text-muted" />}
          <ChevronDown className={`w-4 h-4 text-text-muted transition-transform ${isOpen ? 'rotate-180' : ''}`} />
        </div>
      </button>

      {/* Dropdown */}
      {isOpen && (
        <div className="absolute z-50 w-full mt-1 bg-elevated border border-border-subtle rounded-xl shadow-xl overflow-hidden">
          {isLoading ? (
            <div className="px-4 py-6 text-center text-text-muted text-sm flex items-center justify-center gap-2">
              <Loader2 className="w-4 h-4 animate-spin" />
               正在加载模型列表…
            </div>
          ) : filteredModels.length === 0 ? (
            <div className="px-4 py-4 text-center">
              {models.length === 0 ? (
                <div className="text-text-muted text-sm">
                  <Search className="w-5 h-5 mx-auto mb-2 opacity-50" />
                   <p>输入模型 ID 后按回车即可使用</p>
                   <p className="text-xs mt-1">例如：openai/gpt-4o</p>
                </div>
              ) : (
                <div className="text-text-muted text-sm">
                   <p>没有匹配 “{searchTerm}” 的模型</p>
                   <p className="text-xs mt-1">按回车可直接使用它作为自定义 ID</p>
                </div>
              )}
            </div>
          ) : (
            <div className="max-h-64 overflow-y-auto">
              {filteredModels.slice(0, 50).map(model => (
                <button
                  type="button"
                  key={model.id}
                  onClick={() => handleSelect(model.id)}
                  className={`w-full px-4 py-2.5 text-left hover:bg-hover transition-colors flex flex-col
                    ${model.id === value ? 'bg-accent/10' : ''}`}
                >
                  <span className="text-text-primary text-sm truncate">{model.name}</span>
                  <span className="text-text-muted text-xs font-mono truncate">{model.id}</span>
                </button>
              ))}
              {filteredModels.length > 50 && (
                <div className="px-4 py-2 text-xs text-text-muted text-center border-t border-border-subtle">
                   还有 {filteredModels.length - 50} 项，请继续缩小范围
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

/**
 * Check connection to local Ollama instance
 */
const checkOllamaStatus = async (baseUrl: string): Promise<{ ok: boolean; error: string | null }> => {
  try {
    const response = await fetch(`${baseUrl}/api/tags`, {
      method: 'GET',
      headers: { 'Content-Type': 'application/json' },
    });

    if (!response.ok) {
      if (response.status === 0 || response.status === 404) {
        return { ok: false, error: '无法连接 Ollama，请确认已执行 `ollama serve`' };
      }
      return { ok: false, error: `Ollama API 错误：${response.status}` };
    }

    return { ok: true, error: null };
  } catch (error) {
    return {
      ok: false,
      error: '无法连接 Ollama，请确认已执行 `ollama serve`'
    };
  }
};

export const SettingsPanel = ({ isOpen, onClose, onSettingsSaved, backendUrl, isBackendConnected, onBackendUrlChange }: SettingsPanelProps) => {
  const [settings, setSettings] = useState<LLMSettings>(loadSettings);
  const [showApiKey, setShowApiKey] = useState<Record<string, boolean>>({});
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saved' | 'error'>('idle');
  // Ollama connection state
  const [ollamaError, setOllamaError] = useState<string | null>(null);
  const [isCheckingOllama, setIsCheckingOllama] = useState(false);
  // OpenRouter models state
  const [openRouterModels, setOpenRouterModels] = useState<Array<{ id: string; name: string }>>([]);
  const [isLoadingModels, setIsLoadingModels] = useState(false);

  // Load settings when panel opens
  useEffect(() => {
    if (isOpen) {
      setSettings(loadSettings());
      setSaveStatus('idle');
      setOllamaError(null);
    }
  }, [isOpen]);

  // Check Ollama connection when provider is selected or base URL changes
  const checkOllamaConnection = useCallback(async (baseUrl: string) => {
    setIsCheckingOllama(true);
    setOllamaError(null);

    const { error } = await checkOllamaStatus(baseUrl);
    setIsCheckingOllama(false);
    setOllamaError(error);
  }, []);

  // Load OpenRouter models
  const loadOpenRouterModels = useCallback(async () => {
    setIsLoadingModels(true);
    const models = await fetchOpenRouterModels();
    setOpenRouterModels(models);
    setIsLoadingModels(false);
  }, []);

  useEffect(() => {
    if (settings.activeProvider === 'ollama') {
      const baseUrl = settings.ollama?.baseUrl ?? 'http://localhost:11434';
      const timer = setTimeout(() => {
        checkOllamaConnection(baseUrl);
      }, 300);
      return () => clearTimeout(timer);
    }
  }, [settings.ollama?.baseUrl, settings.activeProvider, checkOllamaConnection]);

  const handleProviderChange = (provider: LLMProvider) => {
    setSettings(prev => ({ ...prev, activeProvider: provider }));
  };

  const domesticProviderMeta = {
    deepseek: {
      docsUrl: 'https://platform.deepseek.com/api-docs/',
      keyPlaceholder: '输入 DeepSeek API Key',
      modelPlaceholder: 'deepseek-chat / deepseek-reasoner',
      baseUrlPlaceholder: 'https://api.deepseek.com/v1',
      requiredHint: '必填：API Key、Model。建议填写 Base URL（默认 https://api.deepseek.com/v1）。',
    },
    qwen: {
      docsUrl: 'https://docs.qwencloud.com/developer-guides/text-generation/quickstart',
      keyPlaceholder: '输入 DashScope / Qwen API Key',
      modelPlaceholder: 'qwen-plus / qwen-max / qwen3-coder-plus',
      baseUrlPlaceholder: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
      requiredHint: '必填：API Key、Model、Base URL（国内/国际域名按账号区域选择）。',
    },
    glm: {
      docsUrl: 'https://docs.z.ai/guides/llm/glm-4.5',
      keyPlaceholder: '输入 智谱 GLM API Key',
      modelPlaceholder: 'glm-4.5 / glm-4.7 / glm-5',
      baseUrlPlaceholder: 'https://open.bigmodel.cn/api/paas/v4',
      requiredHint: '必填：API Key、Model、Base URL（OpenAI 兼容端点）。',
    },
    kimi: {
      docsUrl: 'https://platform.kimi.ai/docs/guide/start-using-kimi-api',
      keyPlaceholder: '输入 Kimi (Moonshot) API Key',
      modelPlaceholder: 'kimi-k2.5 / moonshot-v1-8k',
      baseUrlPlaceholder: 'https://api.moonshot.ai/v1',
      requiredHint: '必填：API Key、Model、Base URL。组织/项目可在 Moonshot 平台控制台管理。',
    },
    minimax: {
      docsUrl: 'https://platform.minimax.io/docs/api-reference/text-openai-api',
      keyPlaceholder: '输入 MiniMax API Key',
      modelPlaceholder: 'MiniMax-M2.5 / MiniMax-M2.7',
      baseUrlPlaceholder: 'https://api.minimax.io/v1',
      requiredHint: '必填：API Key、Model、Base URL（OpenAI 兼容接口）。',
    },
    doubao: {
      docsUrl: 'https://www.volcengine.com/docs/82379/1494384',
      keyPlaceholder: '输入 豆包 Ark API Key',
      modelPlaceholder: 'doubao-seed-1-6-250615 / doubao-pro-32k',
      baseUrlPlaceholder: 'https://ark.cn-beijing.volces.com/api/v3',
      requiredHint: '必填：API Key、Model、Base URL（Ark 对话接口，OpenAI 兼容）。',
    },
  } as const;

  const activeDomesticProvider = (
    settings.activeProvider === 'deepseek'
    || settings.activeProvider === 'qwen'
    || settings.activeProvider === 'glm'
    || settings.activeProvider === 'kimi'
    || settings.activeProvider === 'minimax'
    || settings.activeProvider === 'doubao'
  ) ? settings.activeProvider : null;

  const activeDomesticConfig = activeDomesticProvider
    ? (
      activeDomesticProvider === 'deepseek' ? settings.deepseek
      : activeDomesticProvider === 'qwen' ? settings.qwen
      : activeDomesticProvider === 'glm' ? settings.glm
      : activeDomesticProvider === 'kimi' ? settings.kimi
      : activeDomesticProvider === 'minimax' ? settings.minimax
      : settings.doubao
    )
    : null;

  const updateActiveDomesticConfig = (updates: { apiKey?: string; model?: string; baseUrl?: string }) => {
    if (!activeDomesticProvider) return;
    setSettings((prev) => {
      switch (activeDomesticProvider) {
        case 'deepseek':
          return { ...prev, deepseek: { ...prev.deepseek!, ...updates } };
        case 'qwen':
          return { ...prev, qwen: { ...prev.qwen!, ...updates } };
        case 'glm':
          return { ...prev, glm: { ...prev.glm!, ...updates } };
        case 'kimi':
          return { ...prev, kimi: { ...prev.kimi!, ...updates } };
        case 'minimax':
          return { ...prev, minimax: { ...prev.minimax!, ...updates } };
        case 'doubao':
          return { ...prev, doubao: { ...prev.doubao!, ...updates } };
        default:
          return prev;
      }
    });
  };

  const handleSave = () => {
    try {
      saveSettings(settings);
      setSaveStatus('saved');
      onSettingsSaved?.();
      setTimeout(() => setSaveStatus('idle'), 2000);
    } catch {
      setSaveStatus('error');
    }
  };

  const toggleApiKeyVisibility = (key: string) => {
    setShowApiKey(prev => ({ ...prev, [key]: !prev[key] }));
  };

  if (!isOpen) return null;

  const providers: LLMProvider[] = ['openai', 'deepseek', 'qwen', 'glm', 'kimi', 'minimax', 'doubao', 'gemini', 'anthropic', 'azure-openai', 'ollama', 'openrouter'];


  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <button
        type="button"
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
        aria-label="关闭设置面板"
      />

      {/* Panel */}
      <div className="relative bg-surface border border-border-subtle rounded-2xl shadow-2xl max-w-lg w-full mx-4 overflow-hidden max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border-subtle bg-elevated/50">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 flex items-center justify-center bg-accent/20 rounded-xl">
              <Brain className="w-5 h-5 text-accent" />
            </div>
            <div>
               <h2 className="text-lg font-semibold text-text-primary">AI 设置</h2>
               <p className="text-xs text-text-muted">配置当前使用的 LLM 提供方</p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-2 text-text-muted hover:text-text-primary hover:bg-hover rounded-lg transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* Local Server */}
          {backendUrl !== undefined && onBackendUrlChange && (
            <div className="space-y-3">
              <div className="block text-sm font-medium text-text-secondary">
                 本地服务
              </div>
              <div className="space-y-2">
                <div className="flex items-center gap-2 mb-2">
                  <Server className="w-4 h-4 text-text-muted" />
                   <span className="text-sm text-text-secondary">后端地址</span>
                  <span className={`w-2 h-2 rounded-full ${isBackendConnected ? 'bg-green-400' : 'bg-red-400'}`} />
                  <span className="text-xs text-text-muted">
                     {isBackendConnected ? '已连接' : '未连接'}
                  </span>
                </div>
                <input
                  type="url"
                  value={backendUrl}
                  onChange={(e) => onBackendUrlChange(e.target.value)}
                  placeholder="http://localhost:4747"
                  className="w-full px-4 py-3 bg-elevated border border-border-subtle rounded-xl text-text-primary placeholder:text-text-muted focus:border-accent focus:ring-2 focus:ring-accent/20 outline-none transition-all font-mono text-sm"
                />
                <p className="text-xs text-text-muted">
                   运行对应后端启动命令后再连接本地服务
                </p>
              </div>
            </div>
          )}

          {/* Provider Selection */}
          <div className="space-y-3">
            <div className="block text-sm font-medium text-text-secondary">
               提供方
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              {providers.map(provider => (
                <button
                  type="button"
                  key={provider}
                  onClick={() => handleProviderChange(provider)}
                  className={`
                    flex items-center gap-3 p-4 rounded-xl border-2 transition-all
                    ${settings.activeProvider === provider
                      ? 'border-accent bg-accent/10 text-text-primary'
                      : 'border-border-subtle bg-elevated hover:border-accent/50 text-text-secondary'
                    }
                  `}
                >
                  <div className={`
                    w-8 h-8 rounded-lg flex items-center justify-center text-lg
                    ${settings.activeProvider === provider ? 'bg-accent/20' : 'bg-surface'}
                  `}>
                    {provider === 'openai' ? '🤖' : provider === 'deepseek' ? '🧭' : provider === 'qwen' ? '🌀' : provider === 'glm' ? '🧠' : provider === 'kimi' ? '🌙' : provider === 'minimax' ? '⚡' : provider === 'doubao' ? '🫘' : provider === 'gemini' ? '💎' : provider === 'anthropic' ? '🧠' : provider === 'ollama' ? '🦙' : provider === 'openrouter' ? '🌐' : '☁️'}
                  </div>
                  <span className="font-medium">{getProviderDisplayName(provider)}</span>
                </button>
              ))}
            </div>
          </div>

          {/* OpenAI Settings */}
          {settings.activeProvider === 'openai' && (
            <div className="space-y-4 animate-fade-in">
              <div className="space-y-2">
                <div className="flex items-center gap-2 text-sm font-medium text-text-secondary"><Key className="w-4 h-4" />
                密钥
                                </div>
                <div className="relative">
                  <input
                    type={showApiKey['openai'] ? 'text' : 'password'}
                    value={settings.openai?.apiKey ?? ''}
                    onChange={e => setSettings(prev => ({
                      ...prev,
                      openai: { ...prev.openai!, apiKey: e.target.value }
                    }))}
                     placeholder="输入 OpenAI API Key"
                    className="w-full px-4 py-3 pr-12 bg-elevated border border-border-subtle rounded-xl text-text-primary placeholder:text-text-muted focus:border-accent focus:ring-2 focus:ring-accent/20 outline-none transition-all"
                  />
                  <button
                    type="button"
                    onClick={() => toggleApiKeyVisibility('openai')}
                    className="absolute right-3 top-1/2 -translate-y-1/2 p-1 text-text-muted hover:text-text-primary transition-colors"
                  >
                    {showApiKey['openai'] ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
                <p className="text-xs text-text-muted">
                   可在{' '}
                  <a
                    href="https://platform.openai.com/api-keys"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-accent hover:underline"
                  >
                    OpenAI Platform
                  </a>
                </p>
              </div>

              <div className="space-y-2">
                <div className="text-sm font-medium text-text-secondary">模型</div>
                <input
                  type="text"
                  value={settings.openai?.model ?? 'gpt-5.2-chat'}
                  onChange={e => setSettings(prev => ({
                    ...prev,
                    openai: { ...prev.openai!, model: e.target.value }
                  }))}
                   placeholder="例如：gpt-4o、gpt-4-turbo、gpt-3.5-turbo"
                  className="w-full px-4 py-3 bg-elevated border border-border-subtle rounded-xl text-text-primary placeholder:text-text-muted focus:border-accent focus:ring-2 focus:ring-accent/20 outline-none transition-all font-mono text-sm"
                />
              </div>

              <div className="space-y-2">
                <div className="flex items-center gap-2 text-sm font-medium text-text-secondary"><Server className="w-4 h-4" />
                 基础地址 <span className="text-text-muted font-normal">（可选）</span></div>
                <input
                  type="url"
                  value={settings.openai?.baseUrl ?? ''}
                  onChange={e => setSettings(prev => ({
                    ...prev,
                    openai: { ...prev.openai!, baseUrl: e.target.value }
                  }))}
                   placeholder="https://api.openai.com/v1（默认）"
                  className="w-full px-4 py-3 bg-elevated border border-border-subtle rounded-xl text-text-primary placeholder:text-text-muted focus:border-accent focus:ring-2 focus:ring-accent/20 outline-none transition-all"
                />
                <p className="text-xs text-text-muted">
                   留空则使用默认 OpenAI API；如需代理或兼容接口，可填写自定义地址。
                </p>
              </div>
            </div>
          )}

          {/* Domestic OpenAI-compatible Providers */}
          {activeDomesticProvider && activeDomesticConfig && (
            <div className="space-y-4 animate-fade-in">
              <div className="space-y-2">
                <div className="flex items-center gap-2 text-sm font-medium text-text-secondary"><Key className="w-4 h-4" />
                密钥
                                </div>
                <div className="relative">
                  <input
                    type={showApiKey[`domestic-${activeDomesticProvider}`] ? 'text' : 'password'}
                    value={activeDomesticConfig.apiKey ?? ''}
                    onChange={e => updateActiveDomesticConfig({ apiKey: e.target.value })}
                    placeholder={domesticProviderMeta[activeDomesticProvider].keyPlaceholder}
                    className="w-full px-4 py-3 pr-12 bg-elevated border border-border-subtle rounded-xl text-text-primary placeholder:text-text-muted focus:border-accent focus:ring-2 focus:ring-accent/20 outline-none transition-all"
                  />
                  <button
                    type="button"
                    onClick={() => toggleApiKeyVisibility(`domestic-${activeDomesticProvider}`)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 p-1 text-text-muted hover:text-text-primary transition-colors"
                  >
                    {showApiKey[`domestic-${activeDomesticProvider}`] ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
              </div>

              <div className="space-y-2">
                <div className="text-sm font-medium text-text-secondary">模型</div>
                <input
                  type="text"
                  value={activeDomesticConfig.model ?? ''}
                  onChange={e => updateActiveDomesticConfig({ model: e.target.value })}
                  placeholder={domesticProviderMeta[activeDomesticProvider].modelPlaceholder}
                  className="w-full px-4 py-3 bg-elevated border border-border-subtle rounded-xl text-text-primary placeholder:text-text-muted focus:border-accent focus:ring-2 focus:ring-accent/20 outline-none transition-all font-mono text-sm"
                />
              </div>

              <div className="space-y-2">
                <div className="flex items-center gap-2 text-sm font-medium text-text-secondary"><Server className="w-4 h-4" />
                 基础地址
                                </div>
                <input
                  type="url"
                  value={activeDomesticConfig.baseUrl ?? ''}
                  onChange={e => updateActiveDomesticConfig({ baseUrl: e.target.value })}
                  placeholder={domesticProviderMeta[activeDomesticProvider].baseUrlPlaceholder}
                  className="w-full px-4 py-3 bg-elevated border border-border-subtle rounded-xl text-text-primary placeholder:text-text-muted focus:border-accent focus:ring-2 focus:ring-accent/20 outline-none transition-all"
                />
              </div>

              <div className="p-3 bg-elevated/50 border border-border-subtle rounded-xl text-xs text-text-muted leading-relaxed">
                <p>{domesticProviderMeta[activeDomesticProvider].requiredHint}</p>
                <p className="mt-1">
                  官方文档：
                  <a
                    href={domesticProviderMeta[activeDomesticProvider].docsUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-accent hover:underline ml-1"
                  >
                    {domesticProviderMeta[activeDomesticProvider].docsUrl}
                  </a>
                </p>
              </div>
            </div>
          )}

          {/* Gemini Settings */}
          {settings.activeProvider === 'gemini' && (
            <div className="space-y-4 animate-fade-in">
              <div className="space-y-2">
                <div className="flex items-center gap-2 text-sm font-medium text-text-secondary"><Key className="w-4 h-4" />
                密钥
                                </div>
                <div className="relative">
                  <input
                    type={showApiKey['gemini'] ? 'text' : 'password'}
                    value={settings.gemini?.apiKey ?? ''}
                    onChange={e => setSettings(prev => ({
                      ...prev,
                      gemini: { ...prev.gemini!, apiKey: e.target.value }
                    }))}
                     placeholder="输入 Google AI API Key"
                    className="w-full px-4 py-3 pr-12 bg-elevated border border-border-subtle rounded-xl text-text-primary placeholder:text-text-muted focus:border-accent focus:ring-2 focus:ring-accent/20 outline-none transition-all"
                  />
                  <button
                    type="button"
                    onClick={() => toggleApiKeyVisibility('gemini')}
                    className="absolute right-3 top-1/2 -translate-y-1/2 p-1 text-text-muted hover:text-text-primary transition-colors"
                  >
                    {showApiKey['gemini'] ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
                <p className="text-xs text-text-muted">
                   可在{' '}
                  <a
                    href="https://aistudio.google.com/app/apikey"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-accent hover:underline"
                  >
                    Google AI Studio
                  </a>
                </p>
              </div>

              <div className="space-y-2">
                <div className="text-sm font-medium text-text-secondary">模型</div>
                <input
                  type="text"
                  value={settings.gemini?.model ?? 'gemini-2.0-flash'}
                  onChange={e => setSettings(prev => ({
                    ...prev,
                    gemini: { ...prev.gemini!, model: e.target.value }
                  }))}
                   placeholder="例如：gemini-2.0-flash、gemini-1.5-pro"
                  className="w-full px-4 py-3 bg-elevated border border-border-subtle rounded-xl text-text-primary placeholder:text-text-muted focus:border-accent focus:ring-2 focus:ring-accent/20 outline-none transition-all font-mono text-sm"
                />
              </div>
            </div>
          )}

          {/* Anthropic Settings */}
          {settings.activeProvider === 'anthropic' && (
            <div className="space-y-4 animate-fade-in">
              <div className="space-y-2">
                <div className="flex items-center gap-2 text-sm font-medium text-text-secondary"><Key className="w-4 h-4" />
                密钥
                                </div>
                <div className="relative">
                  <input
                    type={showApiKey['anthropic'] ? 'text' : 'password'}
                    value={settings.anthropic?.apiKey ?? ''}
                    onChange={e => setSettings(prev => ({
                      ...prev,
                      anthropic: { ...prev.anthropic!, apiKey: e.target.value }
                    }))}
                     placeholder="输入 Anthropic API Key"
                    className="w-full px-4 py-3 pr-12 bg-elevated border border-border-subtle rounded-xl text-text-primary placeholder:text-text-muted focus:border-accent focus:ring-2 focus:ring-accent/20 outline-none transition-all"
                  />
                  <button
                    type="button"
                    onClick={() => toggleApiKeyVisibility('anthropic')}
                    className="absolute right-3 top-1/2 -translate-y-1/2 p-1 text-text-muted hover:text-text-primary transition-colors"
                  >
                    {showApiKey['anthropic'] ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
                <p className="text-xs text-text-muted">
                   可在{' '}
                  <a
                    href="https://console.anthropic.com/settings/keys"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-accent hover:underline"
                  >
                    Anthropic Console
                  </a>
                </p>
              </div>

              <div className="space-y-2">
                <div className="text-sm font-medium text-text-secondary">模型</div>
                <input
                  type="text"
                  value={settings.anthropic?.model ?? 'claude-sonnet-4-20250514'}
                  onChange={e => setSettings(prev => ({
                    ...prev,
                    anthropic: { ...prev.anthropic!, model: e.target.value }
                  }))}
                   placeholder="例如：claude-sonnet-4-20250514、claude-3-opus"
                  className="w-full px-4 py-3 bg-elevated border border-border-subtle rounded-xl text-text-primary placeholder:text-text-muted focus:border-accent focus:ring-2 focus:ring-accent/20 outline-none transition-all font-mono text-sm"
                />
              </div>
            </div>
          )}

          {/* Azure OpenAI Settings */}
          {settings.activeProvider === 'azure-openai' && (
            <div className="space-y-4 animate-fade-in">
              <div className="space-y-2">
                <div className="flex items-center gap-2 text-sm font-medium text-text-secondary"><Key className="w-4 h-4" />
                密钥
                                </div>
                <div className="relative">
                  <input
                    type={showApiKey['azure'] ? 'text' : 'password'}
                    value={settings.azureOpenAI?.apiKey ?? ''}
                    onChange={e => setSettings(prev => ({
                      ...prev,
                      azureOpenAI: { ...prev.azureOpenAI!, apiKey: e.target.value }
                    }))}
                    placeholder="输入 Azure OpenAI API Key"
                    className="w-full px-4 py-3 pr-12 bg-elevated border border-border-subtle rounded-xl text-text-primary placeholder:text-text-muted focus:border-accent focus:ring-2 focus:ring-accent/20 outline-none transition-all"
                  />
                  <button
                    type="button"
                    onClick={() => toggleApiKeyVisibility('azure')}
                    className="absolute right-3 top-1/2 -translate-y-1/2 p-1 text-text-muted hover:text-text-primary transition-colors"
                  >
                    {showApiKey['azure'] ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
              </div>

              <div className="space-y-2">
                <div className="flex items-center gap-2 text-sm font-medium text-text-secondary"><Server className="w-4 h-4" />
                 接入地址
                                </div>
                <input
                  type="url"
                  value={settings.azureOpenAI?.endpoint ?? ''}
                  onChange={e => setSettings(prev => ({
                    ...prev,
                    azureOpenAI: { ...prev.azureOpenAI!, endpoint: e.target.value }
                  }))}
                  placeholder="https://your-resource.openai.azure.com"
                  className="w-full px-4 py-3 bg-elevated border border-border-subtle rounded-xl text-text-primary placeholder:text-text-muted focus:border-accent focus:ring-2 focus:ring-accent/20 outline-none transition-all"
                />
              </div>

              <div className="space-y-2">
                <div className="text-sm font-medium text-text-secondary">部署名称</div>
                <input
                  type="text"
                  value={settings.azureOpenAI?.deploymentName ?? ''}
                  onChange={e => setSettings(prev => ({
                    ...prev,
                    azureOpenAI: { ...prev.azureOpenAI!, deploymentName: e.target.value }
                  }))}
                  placeholder="例如：gpt-4o-deployment"
                  className="w-full px-4 py-3 bg-elevated border border-border-subtle rounded-xl text-text-primary placeholder:text-text-muted focus:border-accent focus:ring-2 focus:ring-accent/20 outline-none transition-all"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <div className="text-sm font-medium text-text-secondary">模型</div>
                  <input
                    type="text"
                    value={settings.azureOpenAI?.model ?? 'gpt-4o'}
                    onChange={e => setSettings(prev => ({
                      ...prev,
                      azureOpenAI: { ...prev.azureOpenAI!, model: e.target.value }
                    }))}
                    placeholder="gpt-4o"
                    className="w-full px-4 py-3 bg-elevated border border-border-subtle rounded-xl text-text-primary placeholder:text-text-muted focus:border-accent focus:ring-2 focus:ring-accent/20 outline-none transition-all"
                  />
                </div>

                <div className="space-y-2">
                  <div className="text-sm font-medium text-text-secondary">API 版本</div>
                  <input
                    type="text"
                    value={settings.azureOpenAI?.apiVersion ?? '2024-08-01-preview'}
                    onChange={e => setSettings(prev => ({
                      ...prev,
                      azureOpenAI: { ...prev.azureOpenAI!, apiVersion: e.target.value }
                    }))}
                    placeholder="2024-08-01-preview"
                    className="w-full px-4 py-3 bg-elevated border border-border-subtle rounded-xl text-text-primary placeholder:text-text-muted focus:border-accent focus:ring-2 focus:ring-accent/20 outline-none transition-all"
                  />
                </div>
              </div>

              <p className="text-xs text-text-muted">
                 可在{' '}
                <a
                  href="https://portal.azure.com/#view/Microsoft_Azure_ProjectOxford/CognitiveServicesHub/~/OpenAI"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-accent hover:underline"
                >
                  Azure Portal
                </a>
              </p>
            </div>
          )}

          {/* Ollama Settings */}
          {settings.activeProvider === 'ollama' && (
            <div className="space-y-4 animate-fade-in">
              {/* How to run Ollama */}
              <div className="p-3 bg-amber-500/10 border border-amber-500/30 rounded-xl">
                <p className="text-xs text-amber-300 leading-relaxed">
                   <span className="font-medium">📋 快速开始：</span>先从{' '}
                  <a
                    href="https://ollama.ai"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-accent hover:underline"
                  >
                    ollama.ai
                   </a> 安装 Ollama，然后运行：
                </p>
                <code className="block mt-2 px-3 py-2 bg-black/30 rounded-lg text-amber-200 font-mono text-sm">
                  ollama serve
                </code>
              </div>

              <div className="space-y-2">
                <div className="flex items-center gap-2 text-sm font-medium text-text-secondary"><Server className="w-4 h-4" />
                基础地址
                                </div>
                <div className="flex gap-2">
                  <input
                    type="url"
                    value={settings.ollama?.baseUrl ?? 'http://localhost:11434'}
                    onChange={e => setSettings(prev => ({
                      ...prev,
                      ollama: { ...prev.ollama!, baseUrl: e.target.value }
                    }))}
                    placeholder="http://localhost:11434"
                    className="flex-1 px-4 py-3 bg-elevated border border-border-subtle rounded-xl text-text-primary placeholder:text-text-muted focus:border-accent focus:ring-2 focus:ring-accent/20 outline-none transition-all font-mono text-sm"
                  />
                  <button
                    type="button"
                    onClick={() => checkOllamaConnection(settings.ollama?.baseUrl ?? 'http://localhost:11434')}
                    disabled={isCheckingOllama}
                    className="px-3 py-3 bg-elevated border border-border-subtle rounded-xl text-text-secondary hover:text-text-primary hover:border-accent/50 transition-colors disabled:opacity-50"
                     title="检查连接"
                  >
                    <RefreshCw className={`w-4 h-4 ${isCheckingOllama ? 'animate-spin' : ''}`} />
                  </button>
                </div>
                <p className="text-xs text-text-muted">
                  默认端口为 <code className="px-1 py-0.5 bg-elevated rounded">11434</code>。
                </p>
              </div>

              <div className="space-y-2">
                <div className="text-sm font-medium text-text-secondary">模型</div>

                {ollamaError && !isCheckingOllama && (
                  <div className="p-2 bg-red-500/10 border border-red-500/30 rounded-lg">
                    <p className="text-xs text-red-400 flex items-center gap-1">
                      <AlertCircle className="w-3 h-3" />
                      {ollamaError}
                    </p>
                  </div>
                )}

                <input
                  type="text"
                  value={settings.ollama?.model ?? ''}
                  onChange={e => setSettings(prev => ({
                    ...prev,
                    ollama: { ...prev.ollama!, model: e.target.value }
                  }))}
                  placeholder="例如：llama3.2、mistral、codellama"
                  className="w-full px-4 py-3 bg-elevated border border-border-subtle rounded-xl text-text-primary placeholder:text-text-muted focus:border-accent focus:ring-2 focus:ring-accent/20 outline-none transition-all font-mono text-sm"
                />
                <p className="text-xs text-text-muted">
                   可通过 <code className="px-1 py-0.5 bg-elevated rounded">ollama pull llama3.2</code> 拉取模型。
                </p>
              </div>
            </div>
          )}

          {/* OpenRouter Settings */}
          {settings.activeProvider === 'openrouter' && (
            <div className="space-y-4 animate-fade-in">
              <div className="space-y-2">
                <div className="flex items-center gap-2 text-sm font-medium text-text-secondary"><Key className="w-4 h-4" />
                密钥
                                </div>
                <div className="relative">
                  <input
                    type={showApiKey['openrouter'] ? 'text' : 'password'}
                    value={settings.openrouter?.apiKey ?? ''}
                    onChange={e => setSettings(prev => ({
                      ...prev,
                      openrouter: { ...prev.openrouter!, apiKey: e.target.value }
                    }))}
                     placeholder="输入 OpenRouter API Key"
                    className="w-full px-4 py-3 pr-12 bg-elevated border border-border-subtle rounded-xl text-text-primary placeholder:text-text-muted focus:border-accent focus:ring-2 focus:ring-accent/20 outline-none transition-all"
                  />
                  <button
                    type="button"
                    onClick={() => toggleApiKeyVisibility('openrouter')}
                    className="absolute right-3 top-1/2 -translate-y-1/2 p-1 text-text-muted hover:text-text-primary transition-colors"
                  >
                    {showApiKey['openrouter'] ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
                <p className="text-xs text-text-muted">
                   可在{' '}
                  <a
                    href="https://openrouter.ai/keys"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-accent hover:underline"
                  >
                    OpenRouter Keys
                  </a>
                </p>
              </div>

              <div className="space-y-2">
                <div className="text-sm font-medium text-text-secondary">模型</div>
                <OpenRouterModelCombobox
                  value={settings.openrouter?.model ?? ''}
                  onChange={(model) => setSettings(prev => ({
                    ...prev,
                    openrouter: { ...prev.openrouter!, model }
                  }))}
                  models={openRouterModels}
                  isLoading={isLoadingModels}
                  onLoadModels={loadOpenRouterModels}
                />
                <p className="text-xs text-text-muted">
                   完整模型列表见{' '}
                  <a
                    href="https://openrouter.ai/models"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-accent hover:underline"
                  >
                    OpenRouter Models
                  </a>
                </p>
              </div>
            </div>
          )}



          {/* Privacy Note */}
          <div className="p-4 bg-elevated/50 border border-border-subtle rounded-xl">
            <div className="flex gap-3">
              <div className="w-8 h-8 flex items-center justify-center bg-green-500/20 rounded-lg text-green-400 flex-shrink-0">
                🔒
              </div>
              <div className="text-xs text-text-muted leading-relaxed">
                 <span className="text-text-secondary font-medium">隐私说明：</span>API Key 仅保存在当前浏览器本地存储中。
                 在“AI 问答”模式会直接请求模型提供方；在“问答”模式会随会话请求发送到你的本地服务用于后端推理。
              </div>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-6 py-4 border-t border-border-subtle bg-elevated/30">
          <div className="flex items-center gap-2 text-sm">
            {saveStatus === 'saved' && (
              <span className="flex items-center gap-1.5 text-green-400 animate-fade-in">
                <Check className="w-4 h-4" />
                 设置已保存
              </span>
            )}
            {saveStatus === 'error' && (
              <span className="flex items-center gap-1.5 text-red-400 animate-fade-in">
                <AlertCircle className="w-4 h-4" />
                 保存失败
              </span>
            )}
          </div>
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-sm text-text-secondary hover:text-text-primary transition-colors"
            >
               取消
            </button>
            <button
              type="button"
              onClick={handleSave}
              className="px-5 py-2 bg-accent text-white text-sm font-medium rounded-lg hover:bg-accent-dim transition-colors"
            >
               保存设置
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
