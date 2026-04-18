/**
 * Settings Service
 *
 * Handles localStorage persistence for LLM provider settings.
 * All API keys are stored locally - never sent to any server except the LLM provider.
 */

import {
  LLMSettings,
  DEFAULT_LLM_SETTINGS,
  LLMProvider,
  OpenAIConfig,
  AzureOpenAIConfig,
  GeminiConfig,
  AnthropicConfig,
  OllamaConfig,
  OpenRouterConfig,
  DeepSeekConfig,
  QwenConfig,
  GLMConfig,
  KimiConfig,
  MiniMaxConfig,
  DoubaoConfig,
  OpenAICompatibleProvider,
  ProviderConfig,
} from './types';

const STORAGE_KEY = 'create-graph-llm-settings';

const OPENAI_COMPATIBLE_PROVIDERS: Set<LLMProvider> = new Set([
  'openai',
  'openrouter',
  'deepseek',
  'qwen',
  'glm',
  'kimi',
  'minimax',
  'doubao',
]);

/**
 * Load settings from localStorage
 */
export const loadSettings = (): LLMSettings => {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (!stored) {
      return DEFAULT_LLM_SETTINGS;
    }

    const parsed = JSON.parse(stored) as Partial<LLMSettings>;

    // Merge with defaults to handle new fields
    return {
      ...DEFAULT_LLM_SETTINGS,
      ...parsed,
      openai: {
        ...DEFAULT_LLM_SETTINGS.openai,
        ...parsed.openai,
      },
      azureOpenAI: {
        ...DEFAULT_LLM_SETTINGS.azureOpenAI,
        ...parsed.azureOpenAI,
      },
      gemini: {
        ...DEFAULT_LLM_SETTINGS.gemini,
        ...parsed.gemini,
      },
      anthropic: {
        ...DEFAULT_LLM_SETTINGS.anthropic,
        ...parsed.anthropic,
      },
      ollama: {
        ...DEFAULT_LLM_SETTINGS.ollama,
        ...parsed.ollama,
      },
      openrouter: {
        ...DEFAULT_LLM_SETTINGS.openrouter,
        ...parsed.openrouter,
      },
      deepseek: {
        ...DEFAULT_LLM_SETTINGS.deepseek,
        ...parsed.deepseek,
      },
      qwen: {
        ...DEFAULT_LLM_SETTINGS.qwen,
        ...parsed.qwen,
      },
      glm: {
        ...DEFAULT_LLM_SETTINGS.glm,
        ...parsed.glm,
      },
      kimi: {
        ...DEFAULT_LLM_SETTINGS.kimi,
        ...parsed.kimi,
      },
      minimax: {
        ...DEFAULT_LLM_SETTINGS.minimax,
        ...parsed.minimax,
      },
      doubao: {
        ...DEFAULT_LLM_SETTINGS.doubao,
        ...parsed.doubao,
      },
    };
  } catch (error) {
    console.warn('Failed to load LLM settings:', error);
    return DEFAULT_LLM_SETTINGS;
  }
};

/**
 * Save settings to localStorage
 */
export const saveSettings = (settings: LLMSettings): void => {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
  } catch (error) {
    console.error('Failed to save LLM settings:', error);
  }
};

/**
 * Update a specific provider's settings
 */
export const updateProviderSettings = <T extends LLMProvider>(
  provider: T,
  updates: Partial<
    T extends 'openai' ? Partial<Omit<OpenAIConfig, 'provider'>> :
    T extends 'azure-openai' ? Partial<Omit<AzureOpenAIConfig, 'provider'>> :
    T extends 'gemini' ? Partial<Omit<GeminiConfig, 'provider'>> :
    T extends 'anthropic' ? Partial<Omit<AnthropicConfig, 'provider'>> :
    T extends 'ollama' ? Partial<Omit<OllamaConfig, 'provider'>> :
    T extends 'openrouter' ? Partial<Omit<OpenRouterConfig, 'provider'>> :
    T extends 'deepseek' ? Partial<Omit<DeepSeekConfig, 'provider'>> :
    T extends 'qwen' ? Partial<Omit<QwenConfig, 'provider'>> :
    T extends 'glm' ? Partial<Omit<GLMConfig, 'provider'>> :
    T extends 'kimi' ? Partial<Omit<KimiConfig, 'provider'>> :
    T extends 'minimax' ? Partial<Omit<MiniMaxConfig, 'provider'>> :
    T extends 'doubao' ? Partial<Omit<DoubaoConfig, 'provider'>> :
    never
  >
): LLMSettings => {
  const current = loadSettings();

  switch (provider) {
    case 'openai': {
      const updated: LLMSettings = {
        ...current,
        openai: {
          ...(current.openai ?? {}),
          ...(updates as Partial<Omit<OpenAIConfig, 'provider'>>),
        },
      };
      saveSettings(updated);
      return updated;
    }
    case 'azure-openai': {
      const updated: LLMSettings = {
        ...current,
        azureOpenAI: {
          ...(current.azureOpenAI ?? {}),
          ...(updates as Partial<Omit<AzureOpenAIConfig, 'provider'>>),
        },
      };
      saveSettings(updated);
      return updated;
    }
    case 'gemini': {
      const updated: LLMSettings = {
        ...current,
        gemini: {
          ...(current.gemini ?? {}),
          ...(updates as Partial<Omit<GeminiConfig, 'provider'>>),
        },
      };
      saveSettings(updated);
      return updated;
    }
    case 'anthropic': {
      const updated: LLMSettings = {
        ...current,
        anthropic: {
          ...(current.anthropic ?? {}),
          ...(updates as Partial<Omit<AnthropicConfig, 'provider'>>),
        },
      };
      saveSettings(updated);
      return updated;
    }
    case 'ollama': {
      const updated: LLMSettings = {
        ...current,
        ollama: {
          ...(current.ollama ?? {}),
          ...(updates as Partial<Omit<OllamaConfig, 'provider'>>),
        },
      };
      saveSettings(updated);
      return updated;
    }
    case 'openrouter': {
      const updated: LLMSettings = {
        ...current,
        openrouter: {
          ...(current.openrouter ?? {}),
          ...(updates as Partial<Omit<OpenRouterConfig, 'provider'>>),
        },
      };
      saveSettings(updated);
      return updated;
    }
    case 'deepseek': {
      const updated: LLMSettings = {
        ...current,
        deepseek: {
          ...(current.deepseek ?? {}),
          ...(updates as Partial<Omit<DeepSeekConfig, 'provider'>>),
        },
      };
      saveSettings(updated);
      return updated;
    }
    case 'qwen': {
      const updated: LLMSettings = {
        ...current,
        qwen: {
          ...(current.qwen ?? {}),
          ...(updates as Partial<Omit<QwenConfig, 'provider'>>),
        },
      };
      saveSettings(updated);
      return updated;
    }
    case 'glm': {
      const updated: LLMSettings = {
        ...current,
        glm: {
          ...(current.glm ?? {}),
          ...(updates as Partial<Omit<GLMConfig, 'provider'>>),
        },
      };
      saveSettings(updated);
      return updated;
    }
    case 'kimi': {
      const updated: LLMSettings = {
        ...current,
        kimi: {
          ...(current.kimi ?? {}),
          ...(updates as Partial<Omit<KimiConfig, 'provider'>>),
        },
      };
      saveSettings(updated);
      return updated;
    }
    case 'minimax': {
      const updated: LLMSettings = {
        ...current,
        minimax: {
          ...(current.minimax ?? {}),
          ...(updates as Partial<Omit<MiniMaxConfig, 'provider'>>),
        },
      };
      saveSettings(updated);
      return updated;
    }
    case 'doubao': {
      const updated: LLMSettings = {
        ...current,
        doubao: {
          ...(current.doubao ?? {}),
          ...(updates as Partial<Omit<DoubaoConfig, 'provider'>>),
        },
      };
      saveSettings(updated);
      return updated;
    }
    default: {
      const updated: LLMSettings = { ...current };
      saveSettings(updated);
      return updated;
    }
  }
};

/**
 * Set the active provider
 */
export const setActiveProvider = (provider: LLMProvider): LLMSettings => {
  const current = loadSettings();
  const updated: LLMSettings = {
    ...current,
    activeProvider: provider,
  };
  saveSettings(updated);
  return updated;
};

/**
 * Get the current provider configuration
 */
export const getActiveProviderConfig = (): ProviderConfig | null => {
  const settings = loadSettings();

  switch (settings.activeProvider) {
    case 'openai':
      if (!settings.openai?.apiKey || !settings.openai?.model) {
        return null;
      }
      return {
        provider: 'openai',
        ...settings.openai,
      } as OpenAIConfig;

    case 'azure-openai':
      if (!settings.azureOpenAI?.apiKey || !settings.azureOpenAI?.endpoint || !settings.azureOpenAI?.deploymentName) {
        return null;
      }
      return {
        provider: 'azure-openai',
        ...settings.azureOpenAI,
      } as AzureOpenAIConfig;

    case 'gemini':
      if (!settings.gemini?.apiKey || !settings.gemini?.model) {
        return null;
      }
      return {
        provider: 'gemini',
        ...settings.gemini,
      } as GeminiConfig;

    case 'anthropic':
      if (!settings.anthropic?.apiKey || !settings.anthropic?.model) {
        return null;
      }
      return {
        provider: 'anthropic',
        ...settings.anthropic,
      } as AnthropicConfig;

    case 'ollama':
      if (!settings.ollama?.model) {
        return null;
      }
      return {
        provider: 'ollama',
        ...settings.ollama,
      } as OllamaConfig;

    case 'openrouter':
      if (!settings.openrouter?.apiKey || !settings.openrouter?.model) {
        return null;
      }
      return {
        provider: 'openrouter',
        apiKey: settings.openrouter.apiKey,
        model: settings.openrouter.model,
        baseUrl: settings.openrouter.baseUrl || 'https://openrouter.ai/api/v1',
        temperature: settings.openrouter.temperature,
        maxTokens: settings.openrouter.maxTokens,
      } as OpenRouterConfig;

    case 'deepseek':
      if (!settings.deepseek?.apiKey || !settings.deepseek?.model || !settings.deepseek?.baseUrl) {
        return null;
      }
      return {
        provider: 'deepseek',
        apiKey: settings.deepseek.apiKey,
        model: settings.deepseek.model,
        baseUrl: settings.deepseek.baseUrl,
        temperature: settings.deepseek.temperature,
        maxTokens: settings.deepseek.maxTokens,
      } as DeepSeekConfig;

    case 'qwen':
      if (!settings.qwen?.apiKey || !settings.qwen?.model || !settings.qwen?.baseUrl) {
        return null;
      }
      return {
        provider: 'qwen',
        apiKey: settings.qwen.apiKey,
        model: settings.qwen.model,
        baseUrl: settings.qwen.baseUrl,
        temperature: settings.qwen.temperature,
        maxTokens: settings.qwen.maxTokens,
      } as QwenConfig;

    case 'glm':
      if (!settings.glm?.apiKey || !settings.glm?.model || !settings.glm?.baseUrl) {
        return null;
      }
      return {
        provider: 'glm',
        apiKey: settings.glm.apiKey,
        model: settings.glm.model,
        baseUrl: settings.glm.baseUrl,
        temperature: settings.glm.temperature,
        maxTokens: settings.glm.maxTokens,
      } as GLMConfig;

    case 'kimi':
      if (!settings.kimi?.apiKey || !settings.kimi?.model || !settings.kimi?.baseUrl) {
        return null;
      }
      return {
        provider: 'kimi',
        apiKey: settings.kimi.apiKey,
        model: settings.kimi.model,
        baseUrl: settings.kimi.baseUrl,
        temperature: settings.kimi.temperature,
        maxTokens: settings.kimi.maxTokens,
      } as KimiConfig;

    case 'minimax':
      if (!settings.minimax?.apiKey || !settings.minimax?.model || !settings.minimax?.baseUrl) {
        return null;
      }
      return {
        provider: 'minimax',
        apiKey: settings.minimax.apiKey,
        model: settings.minimax.model,
        baseUrl: settings.minimax.baseUrl,
        temperature: settings.minimax.temperature,
        maxTokens: settings.minimax.maxTokens,
      } as MiniMaxConfig;

    case 'doubao':
      if (!settings.doubao?.apiKey || !settings.doubao?.model || !settings.doubao?.baseUrl) {
        return null;
      }
      return {
        provider: 'doubao',
        apiKey: settings.doubao.apiKey,
        model: settings.doubao.model,
        baseUrl: settings.doubao.baseUrl,
        temperature: settings.doubao.temperature,
        maxTokens: settings.doubao.maxTokens,
      } as DoubaoConfig;

    default:
      return null;
  }
};

/**
 * Check if the active provider is properly configured
 */
export const isProviderConfigured = (): boolean => {
  return getActiveProviderConfig() !== null;
};

export const hasActiveLocalProviderConfig = (): boolean => {
  return isProviderConfigured();
};

export const isOpenAICompatibleProvider = (provider: LLMProvider): provider is OpenAICompatibleProvider => {
  return OPENAI_COMPATIBLE_PROVIDERS.has(provider);
};

export interface BackendConversationLLMConfig {
  provider: OpenAICompatibleProvider;
  api_key: string;
  base_url: string;
  model: string;
}

/**
 * Build backend runtime config for conversation APIs.
 *
 * Backend conversation currently uses an OpenAI-compatible request shape.
 */
export const buildBackendConversationLLMConfig = (): BackendConversationLLMConfig | null => {
  const active = getActiveProviderConfig();
  if (!active) {
    return null;
  }

  if (!isOpenAICompatibleProvider(active.provider)) {
    return null;
  }

  const apiKey = 'apiKey' in active ? String(active.apiKey || '').trim() : '';
  const model = String(active.model || '').trim();
  const baseUrl = (
    'baseUrl' in active
      ? String(active.baseUrl || '').trim()
      : active.provider === 'openai'
        ? 'https://api.openai.com/v1'
        : ''
  );

  if (!apiKey || !model || !baseUrl) {
    return null;
  }

  return {
    provider: active.provider,
    api_key: apiKey,
    base_url: baseUrl,
    model,
  };
};

/**
 * Clear all settings (reset to defaults)
 */
export const clearSettings = (): void => {
  localStorage.removeItem(STORAGE_KEY);
};

/**
 * Get display name for a provider
 */
export const getProviderDisplayName = (provider: LLMProvider): string => {
  switch (provider) {
    case 'openai':
      return 'OpenAI';
    case 'azure-openai':
      return 'Azure OpenAI';
    case 'gemini':
      return 'Google Gemini';
    case 'anthropic':
      return 'Anthropic';
    case 'ollama':
      return 'Ollama (Local)';
    case 'openrouter':
      return 'OpenRouter';
    case 'deepseek':
      return 'DeepSeek';
    case 'qwen':
      return 'Qwen';
    case 'glm':
      return 'GLM (智谱)';
    case 'kimi':
      return 'Kimi (Moonshot)';
    case 'minimax':
      return 'MiniMax';
    case 'doubao':
      return '豆包 (Ark)';
    default:
      return provider;
  }
};

/**
 * Get available models for a provider
 */
export const getAvailableModels = (provider: LLMProvider): string[] => {
  switch (provider) {
    case 'openai':
      return ['gpt-4.5-preview', 'gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo', 'gpt-4', 'gpt-3.5-turbo'];
    case 'azure-openai':
      return ['gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo', 'gpt-4', 'gpt-35-turbo'];
    case 'gemini':
      return ['gemini-2.0-flash', 'gemini-1.5-pro', 'gemini-1.5-flash', 'gemini-1.0-pro'];
    case 'anthropic':
      return ['claude-sonnet-4-20250514', 'claude-3-5-sonnet-20241022', 'claude-3-5-haiku-20241022', 'claude-3-opus-20240229'];
    case 'ollama':
      return ['llama3.2', 'llama3.1', 'mistral', 'codellama', 'deepseek-coder'];
    case 'deepseek':
      return ['deepseek-chat', 'deepseek-reasoner'];
    case 'qwen':
      return ['qwen-plus', 'qwen-max', 'qwen3-coder-plus'];
    case 'glm':
      return ['glm-4.5', 'glm-4.7', 'glm-5'];
    case 'kimi':
      return ['kimi-k2.5', 'moonshot-v1-8k', 'moonshot-v1-32k'];
    case 'minimax':
      return ['MiniMax-M2.5', 'MiniMax-M2.5-highspeed', 'MiniMax-M2.7'];
    case 'doubao':
      return ['doubao-seed-1-6-250615', 'doubao-pro-32k', 'doubao-lite-32k'];
    default:
      return [];
  }
};

/**
 * Fetch available models from OpenRouter API
 */
export const fetchOpenRouterModels = async (): Promise<Array<{ id: string; name: string }>> => {
  try {
    const response = await fetch('https://openrouter.ai/api/v1/models');
    if (!response.ok) throw new Error('Failed to fetch models');
    const data = await response.json();
    return data.data.map((model: any) => ({
      id: model.id,
      name: model.name || model.id,
    }));
  } catch (error) {
    console.error('Error fetching OpenRouter models:', error);
    return [];
  }
};
