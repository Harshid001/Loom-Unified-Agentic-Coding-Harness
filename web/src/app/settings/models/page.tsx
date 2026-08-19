"use client";

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { AuthGate } from '@/components/AuthGate';
import {
  Cpu,
  Key,
  CheckCircle2,
  AlertCircle,
  Loader2,
  ArrowLeft,
  RefreshCw,
  Sparkles,
  Shield,
  ChevronDown,
  Check,
  Eye,
  EyeOff,
  Server,
  ExternalLink,
  Zap,
  Trash2,
} from 'lucide-react';

type ProviderKey = 'anthropic' | 'openai' | 'deepseek' | 'gemini' | 'openrouter';

interface ProviderMeta {
  id: ProviderKey;
  name: string;
  badge: string;
  placeholder: string;
  docUrl: string;
  description: string;
  defaultModels: string[];
}

const PROVIDERS: Record<ProviderKey, ProviderMeta> = {
  anthropic: {
    id: 'anthropic',
    name: 'Anthropic',
    badge: 'Claude',
    placeholder: 'sk-ant-api03-...',
    docUrl: 'https://console.anthropic.com/settings/keys',
    description: 'Premier coding and reasoning models including Claude 3.5 Sonnet and Claude 3.7 Sonnet.',
    defaultModels: [
      'claude-3-5-sonnet-20241022',
      'claude-3-7-sonnet-20250219',
      'claude-3-5-haiku-20241022',
      'claude-3-opus-20240229',
    ],
  },
  openai: {
    id: 'openai',
    name: 'OpenAI',
    badge: 'GPT / o1',
    placeholder: 'sk-proj-...',
    docUrl: 'https://platform.openai.com/api-keys',
    description: 'High-throughput tool-calling and reasoning models including GPT-4o, GPT-4o-mini, and o3-mini.',
    defaultModels: ['gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo', 'o1', 'o1-mini', 'o3-mini'],
  },
  deepseek: {
    id: 'deepseek',
    name: 'DeepSeek',
    badge: 'V3 / Reasoner',
    placeholder: 'sk-...',
    docUrl: 'https://platform.deepseek.com/api_keys',
    description: 'Cost-efficient frontier open-architecture models optimized for coding and mathematical reasoning.',
    defaultModels: ['deepseek-chat', 'deepseek-reasoner', 'deepseek-v3', 'deepseek/deepseek-chat'],
  },
  gemini: {
    id: 'gemini',
    name: 'Google Gemini',
    badge: 'Gemini 1.5/2.0',
    placeholder: 'AIzaSy...',
    docUrl: 'https://aistudio.google.com/app/apikey',
    description: 'Ultra-long context window models with 1M+ token capacity and fast multimodal generation.',
    defaultModels: ['gemini-1.5-pro', 'gemini-1.5-flash', 'gemini-2.0-flash', 'gemini-pro'],
  },
  openrouter: {
    id: 'openrouter',
    name: 'OpenRouter / Free',
    badge: 'Free / Router',
    placeholder: 'sk-or-v1-...',
    docUrl: 'https://openrouter.ai/keys',
    description: 'Unified endpoint with free tier access to Gemini 2.0 Flash, DeepSeek R1, Llama 3.3, and Claude models.',
    defaultModels: [
      'google/gemini-2.0-flash-exp:free',
      'google/gemini-2.5-pro',
      'deepseek/deepseek-r1:free',
      'meta-llama/llama-3.3-70b-instruct:free',
      'anthropic/claude-3.7-sonnet',
      'openai/gpt-4o',
    ],
  },
};

interface ProviderStatus {
  configured: boolean;
  models: string[];
}

interface ModelConfig {
  active_model: string;
  available_models: string[];
  providers: Record<string, ProviderStatus>;
}

function ModelSettingsContent() {
  const [selectedProvider, setSelectedProvider] = useState<ProviderKey>('anthropic');
  const [apiKeys, setApiKeys] = useState<Record<ProviderKey, string>>({
    anthropic: '',
    openai: '',
    deepseek: '',
    gemini: '',
    openrouter: '',
  });
  const [showKey, setShowKey] = useState<Record<ProviderKey, boolean>>({
    anthropic: false,
    openai: false,
    deepseek: false,
    gemini: false,
    openrouter: false,
  });

  const [activeModel, setActiveModel] = useState<string>('claude-3-5-sonnet-20241022');
  const [selectedModel, setSelectedModel] = useState<string>('claude-3-5-sonnet-20241022');
  const [detectedModels, setDetectedModels] = useState<Record<ProviderKey, string[]>>({
    anthropic: PROVIDERS.anthropic.defaultModels,
    openai: PROVIDERS.openai.defaultModels,
    deepseek: PROVIDERS.deepseek.defaultModels,
    gemini: PROVIDERS.gemini.defaultModels,
    openrouter: PROVIDERS.openrouter.defaultModels,
  });

  const [providerConfigured, setProviderConfigured] = useState<Record<ProviderKey, boolean>>({
    anthropic: false,
    openai: false,
    deepseek: false,
    gemini: false,
    openrouter: false,
  });

  const [isDetecting, setIsDetecting] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isLoadingConfig, setIsLoadingConfig] = useState(true);
  const [feedback, setFeedback] = useState<{ type: 'success' | 'error' | 'info'; message: string } | null>(null);

  // Fetch initial config from backend
  const fetchConfig = async () => {
    setIsLoadingConfig(true);
    if (typeof window !== 'undefined') {
      const savedModel = localStorage.getItem('loom_active_model');
      if (savedModel) {
        setActiveModel(savedModel);
        setSelectedModel(savedModel);
      }
      const savedProvider = localStorage.getItem('loom_active_provider') as ProviderKey | null;
      if (savedProvider && PROVIDERS[savedProvider]) {
        setSelectedProvider(savedProvider);
      }
      const savedAnthropic = localStorage.getItem('loom_provider_anthropic_key') || '';
      const savedOpenai = localStorage.getItem('loom_provider_openai_key') || '';
      const savedDeepseek = localStorage.getItem('loom_provider_deepseek_key') || '';
      const savedGemini = localStorage.getItem('loom_provider_gemini_key') || '';
      const savedOpenRouter = localStorage.getItem('loom_provider_openrouter_key') || '';
      setApiKeys({
        anthropic: savedAnthropic,
        openai: savedOpenai,
        deepseek: savedDeepseek,
        gemini: savedGemini,
        openrouter: savedOpenRouter,
      });
    }
    try {
      const loomApiKey = typeof window !== 'undefined' ? (localStorage.getItem('loom_api_key') || localStorage.getItem('loom_auth_token') || '') : '';
      const headers: Record<string, string> = {};
      if (loomApiKey) headers['X-API-Key'] = loomApiKey;

      const res = await fetch('/api/settings/model', { headers });
      if (res.ok) {
        const data: ModelConfig = await res.json();
        if (data.active_model) {
          setActiveModel(data.active_model);
          setSelectedModel(data.active_model);
          if (typeof window !== 'undefined') {
            localStorage.setItem('loom_active_model', data.active_model);
          }
        }
        if (data.providers) {
          const updatedConfigured: Record<ProviderKey, boolean> = {
            anthropic: data.providers.anthropic?.configured || false,
            openai: data.providers.openai?.configured || false,
            deepseek: data.providers.deepseek?.configured || false,
            gemini: data.providers.gemini?.configured || false,
            openrouter: data.providers.openrouter?.configured || false,
          };
          setProviderConfigured(updatedConfigured);

          const updatedDetected: Record<ProviderKey, string[]> = {
            anthropic: data.providers.anthropic?.models?.length
              ? data.providers.anthropic.models
              : PROVIDERS.anthropic.defaultModels,
            openai: data.providers.openai?.models?.length
              ? data.providers.openai.models
              : PROVIDERS.openai.defaultModels,
            deepseek: data.providers.deepseek?.models?.length
              ? data.providers.deepseek.models
              : PROVIDERS.deepseek.defaultModels,
            gemini: data.providers.gemini?.models?.length
              ? data.providers.gemini.models
              : PROVIDERS.gemini.defaultModels,
            openrouter: data.providers.openrouter?.models?.length
              ? data.providers.openrouter.models
              : PROVIDERS.openrouter.defaultModels,
          };
          setDetectedModels(updatedDetected);
        }
      }
    } catch (err) {
      console.error('Failed to fetch model settings:', err);
    } finally {
      setIsLoadingConfig(false);
    }
  };

  const handleClearAllKeys = () => {
    if (typeof window !== 'undefined') {
      localStorage.removeItem('loom_provider_anthropic_key');
      localStorage.removeItem('loom_provider_openai_key');
      localStorage.removeItem('loom_provider_deepseek_key');
      localStorage.removeItem('loom_provider_gemini_key');
      localStorage.removeItem('loom_provider_openrouter_key');
      localStorage.removeItem('loom_provider_deepseek_base_url');
    }
    setApiKeys({
      anthropic: '',
      openai: '',
      deepseek: '',
      gemini: '',
      openrouter: '',
    });
    setProviderConfigured({
      anthropic: false,
      openai: false,
      deepseek: false,
      gemini: false,
      openrouter: false,
    });
    setFeedback({
      type: 'info',
      message: 'All stored API keys have been wiped from browser memory.',
    });
  };

  useEffect(() => {
    fetchConfig();
  }, []);

  const currentProviderMeta = PROVIDERS[selectedProvider];
  const currentDetectedModels = detectedModels[selectedProvider] || currentProviderMeta.defaultModels;

  const handleDetect = async () => {
    const key = apiKeys[selectedProvider]?.trim();
    if (!key) {
      setFeedback({
        type: 'error',
        message: `Please enter a valid API key for ${currentProviderMeta.name} before detecting models.`,
      });
      return;
    }

    setIsDetecting(true);
    setFeedback(null);

    if (typeof window !== 'undefined') {
      localStorage.setItem(`loom_provider_${selectedProvider}_key`, key);
    }

    try {
      const loomApiKey = typeof window !== 'undefined' ? (localStorage.getItem('loom_api_key') || localStorage.getItem('loom_auth_token') || '') : '';
      const headers: Record<string, string> = { 'Content-Type': 'application/json' };
      if (loomApiKey) headers['X-API-Key'] = loomApiKey;

      const res = await fetch('/api/models/detect', {
        method: 'POST',
        headers,
        body: JSON.stringify({
          provider: selectedProvider,
          api_key: key,
        }),
      });

      const data = await res.json();
      if (res.ok && data.valid) {
        const modelsList = data.models && data.models.length > 0 ? data.models : currentProviderMeta.defaultModels;
        setDetectedModels(prev => ({
          ...prev,
          [selectedProvider]: modelsList,
        }));
        setProviderConfigured(prev => ({
          ...prev,
          [selectedProvider]: true,
        }));
        if (modelsList.length > 0) {
          setSelectedModel(modelsList[0]);
        }
        setFeedback({
          type: 'success',
          message: `Successfully validated ${currentProviderMeta.name} key and detected ${modelsList.length} models.`,
        });
      } else {
        setFeedback({
          type: 'error',
          message: data.detail || `Validation failed for ${currentProviderMeta.name}. Please verify your API key.`,
        });
      }
    } catch (err: unknown) {
      setFeedback({
        type: 'error',
        message: err instanceof Error ? err.message : 'Network error during model detection',
      });
    } finally {
      setIsDetecting(false);
    }
  };

  const handleSetActiveModel = async () => {
    if (!selectedModel) return;

    setIsSaving(true);
    setFeedback(null);

    const key = apiKeys[selectedProvider]?.trim();
    if (typeof window !== 'undefined' && key) {
      localStorage.setItem(`loom_provider_${selectedProvider}_key`, key);
    }

    try {
      const loomApiKey = typeof window !== 'undefined' ? (localStorage.getItem('loom_api_key') || localStorage.getItem('loom_auth_token') || '') : '';
      const headers: Record<string, string> = { 'Content-Type': 'application/json' };
      if (loomApiKey) headers['X-API-Key'] = loomApiKey;

      const res = await fetch('/api/settings/model', {
        method: 'PUT',
        headers,
        body: JSON.stringify({
          model: selectedModel,
          provider: selectedProvider,
          api_key: key || undefined,
          loom_api_key: loomApiKey || undefined,
        }),
      });

      const data = await res.json();
      if (res.ok) {
        setActiveModel(selectedModel);
        if (typeof window !== 'undefined') {
          localStorage.setItem('loom_active_model', selectedModel);
          localStorage.setItem('loom_active_provider', selectedProvider);
          window.dispatchEvent(new CustomEvent('loom_active_model_changed', { detail: selectedModel }));
        }
        setFeedback({
          type: 'success',
          message: `Active model set to "${selectedModel}". All subsequent tasks will execute using this model.`,
        });
      } else {
        setFeedback({
          type: 'error',
          message: data.detail || 'Failed to update active model configuration.',
        });
      }
    } catch (err: unknown) {
      setFeedback({
        type: 'error',
        message: err instanceof Error ? err.message : 'Network error updating active model',
      });
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="min-h-screen bg-[var(--bg-root)] text-[var(--text-primary)] flex flex-col font-sans">
      {/* 1. Header Bar */}
      <header className="border-b border-[var(--border-subtle)] bg-[var(--bg-sidebar)] px-6 py-3 flex items-center justify-between shrink-0">
        <div className="flex items-center space-x-3.5">
          <Link
            href="/"
            className="btn-secondary h-8 px-2.5 text-xs gap-1.5 font-mono"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            <span>Dashboard</span>
          </Link>
          <div className="h-4 w-px bg-[var(--border-subtle)]" />
          <div className="flex items-center gap-2">
            <div className="h-7 w-7 rounded-lg bg-[var(--brand)] flex items-center justify-center text-white shrink-0">
              <Cpu className="h-3.5 w-3.5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-xs font-bold uppercase font-mono tracking-tight text-[var(--text-primary)]">
                  Model Settings
                </h1>
                <span className="status-pill status-pill-idle text-[9px] py-0 px-1.5">
                  DYNAMIC ROUTER
                </span>
              </div>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2.5">
          <div className="status-pill status-pill-running h-8">
            <Sparkles className="h-3 w-3 fill-current" />
            <span>ACTIVE: {activeModel}</span>
          </div>

          <button
            onClick={handleClearAllKeys}
            className="btn-secondary h-8 px-2.5 text-xs text-[var(--danger)] hover:border-[var(--danger)]/50 gap-1.5 font-mono"
            title="Clear all stored provider API keys"
            aria-label="Clear all stored provider API keys"
          >
            <Trash2 className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">Clear Stored Keys</span>
          </button>

          <button
            onClick={fetchConfig}
            disabled={isLoadingConfig}
            className="btn-secondary h-8 w-8 p-0 flex items-center justify-center"
            title="Refresh configuration"
            aria-label="Refresh configuration"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${isLoadingConfig ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </header>

      {/* 2. Main Content Area */}
      <main className="flex-1 max-w-[1400px] w-full mx-auto p-8 space-y-6">
        {/* Banner Card */}
        <div className="loom-card-elevated flex items-start justify-between flex-wrap gap-4">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="text-[10px] font-mono font-bold text-[var(--brand-hover)] bg-[var(--brand-soft)] px-2 py-0.5 rounded border border-[var(--brand)]/30">
                INFERENCE CONTROL
              </span>
            </div>
            <h2 className="text-base font-bold text-[var(--text-primary)] uppercase font-mono tracking-tight">
              Runtime Model Detection & Switching
            </h2>
            <p className="text-xs text-[var(--text-secondary)] mt-0.5 max-w-2xl">
              Connect frontier model provider keys. Loom dynamically discovers supported models via LiteLLM,
              overrides runtime environment keys per session, and enables instant fallback-aware routing.
            </p>
          </div>
        </div>

        {/* Feedback Alert */}
        {feedback && (
          <div
            className={`p-3.5 rounded-xl border flex items-start gap-3 transition font-mono text-xs ${
              feedback.type === 'success'
                ? 'bg-[var(--success)]/10 border-[var(--success)]/30 text-[var(--success)]'
                : feedback.type === 'error'
                ? 'bg-[var(--danger)]/10 border-[var(--danger)]/30 text-[var(--danger)]'
                : 'bg-[var(--brand-soft)] border-[var(--brand)]/30 text-[var(--brand-hover)]'
            }`}
            role="alert"
          >
            {feedback.type === 'success' ? (
              <CheckCircle2 className="h-4 w-4 shrink-0 mt-0.5" />
            ) : feedback.type === 'error' ? (
              <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
            ) : (
              <Shield className="h-4 w-4 shrink-0 mt-0.5" />
            )}
            <div className="leading-relaxed flex-1">{feedback.message}</div>
            <button
              onClick={() => setFeedback(null)}
              className="text-xs opacity-60 hover:opacity-100 transition px-1"
              aria-label="Dismiss alert"
            >
              ✕
            </button>
          </div>
        )}

        {/* Provider Tabs + Configuration */}
        <div className="loom-card space-y-6">
          <div>
            <label className="text-[10px] font-mono font-bold text-[var(--text-muted)] uppercase tracking-wider block mb-2 px-1">
              SELECT PROVIDER
            </label>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
              {(Object.keys(PROVIDERS) as ProviderKey[]).map(key => {
                const p = PROVIDERS[key];
                const isSelected = selectedProvider === key;
                const isConfigured = providerConfigured[key];

                return (
                  <button
                    key={p.id}
                    onClick={() => {
                      setSelectedProvider(p.id);
                      setFeedback(null);
                      const currentList = detectedModels[p.id] || p.defaultModels;
                      if (currentList.length > 0) {
                        setSelectedModel(currentList[0]);
                      }
                    }}
                    className={`p-3.5 rounded-xl border text-left transition flex flex-col justify-between min-h-[90px] ${
                      isSelected
                        ? 'bg-[var(--brand-soft)] border-[var(--brand)] ring-1 ring-[var(--brand)]/40'
                        : 'bg-[var(--bg-elevated)] border-[var(--border-subtle)] hover:border-[var(--border-default)]'
                    }`}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <span className="font-bold text-xs font-mono text-[var(--text-primary)]">{p.name}</span>
                      {isConfigured && (
                        <span className="h-2 w-2 rounded-full bg-[var(--success)] shadow-sm shadow-[var(--success)]" title="Configured" />
                      )}
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-[10px] font-mono text-[var(--text-muted)] bg-[var(--bg-surface)] px-1.5 py-0.5 rounded border border-[var(--border-subtle)]">
                        {p.badge}
                      </span>
                      {isSelected && <Check className="h-3.5 w-3.5 text-[var(--brand)] stroke-[3]" />}
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Provider Configuration Card */}
          <div className="bg-[var(--bg-elevated)] border border-[var(--border-subtle)] rounded-xl p-5 space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-3 border-b border-[var(--border-subtle)]">
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-xs font-bold text-[var(--text-primary)] font-mono uppercase">
                    {currentProviderMeta.name} Authentication
                  </h3>
                  {providerConfigured[selectedProvider] && (
                    <span className="status-pill status-pill-verified text-[9px] py-0">
                      Ready
                    </span>
                  )}
                </div>
                <p className="text-xs text-[var(--text-secondary)] mt-0.5">{currentProviderMeta.description}</p>
              </div>
              <a
                href={currentProviderMeta.docUrl}
                target="_blank"
                rel="noreferrer"
                className="btn-tertiary text-xs p-0 gap-1 shrink-0 font-mono"
              >
                <span>Get API Key</span>
                <ExternalLink className="h-3 w-3" />
              </a>
            </div>

            {/* API Key Input Field */}
            <div className="space-y-1.5">
              <label htmlFor="api-key-input" className="text-[11px] font-mono font-bold text-[var(--text-muted)] uppercase flex items-center justify-between">
                <span>{currentProviderMeta.name} API Key</span>
                <span className="text-[10px] text-[var(--text-muted)] font-normal">Stored in memory per session</span>
              </label>

              <div className="flex flex-col sm:flex-row gap-2.5">
                <div className="relative flex-1">
                  <Key className="h-3.5 w-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-muted)]" />
                  <input
                    id="api-key-input"
                    type={showKey[selectedProvider] ? 'text' : 'password'}
                    value={apiKeys[selectedProvider]}
                    onChange={e =>
                      setApiKeys(prev => ({
                        ...prev,
                        [selectedProvider]: e.target.value,
                      }))
                    }
                    placeholder={currentProviderMeta.placeholder}
                    className="w-full bg-[var(--bg-root)] border border-[var(--border-subtle)] focus:border-[var(--brand)] rounded-lg pl-8 pr-9 py-2 text-xs font-mono text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:outline-none transition"
                  />
                  <button
                    type="button"
                    onClick={() =>
                      setShowKey(prev => ({
                        ...prev,
                        [selectedProvider]: !prev[selectedProvider],
                      }))
                    }
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-[var(--text-muted)] hover:text-[var(--text-primary)] transition"
                    title={showKey[selectedProvider] ? 'Hide key' : 'Show key'}
                    aria-label={showKey[selectedProvider] ? 'Hide API key' : 'Show API key'}
                  >
                    {showKey[selectedProvider] ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                  </button>
                </div>

                <button
                  type="button"
                  onClick={handleDetect}
                  disabled={isDetecting || !apiKeys[selectedProvider]?.trim()}
                  className="btn-secondary h-9 px-4 text-xs gap-1.5 shrink-0"
                >
                  {isDetecting ? (
                    <>
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      <span>Detecting...</span>
                    </>
                  ) : (
                    <>
                      <Sparkles className="h-3.5 w-3.5 text-[var(--brand)]" />
                      <span>Test & Detect</span>
                    </>
                  )}
                </button>
              </div>
            </div>

            {/* Model Selection Dropdown & Action */}
            <div className="pt-3 border-t border-[var(--border-subtle)] space-y-3">
              <div>
                <label htmlFor="detected-model-select" className="text-[11px] font-mono font-bold text-[var(--text-muted)] uppercase block mb-1.5">
                  Detected {currentProviderMeta.name} Models ({currentDetectedModels.length})
                </label>

                <div className="relative">
                  <select
                    id="detected-model-select"
                    value={selectedModel}
                    onChange={e => setSelectedModel(e.target.value)}
                    className="w-full appearance-none bg-[var(--bg-root)] border border-[var(--border-subtle)] focus:border-[var(--brand)] rounded-lg px-3.5 py-2 text-xs font-mono text-[var(--text-primary)] focus:outline-none transition pr-9 cursor-pointer"
                  >
                    {currentDetectedModels.map(m => (
                      <option key={m} value={m} className="bg-[var(--bg-elevated)] text-[var(--text-primary)] font-mono py-1">
                        {m} {m === activeModel ? '★ (Current Active)' : ''}
                      </option>
                    ))}
                  </select>
                  <ChevronDown className="h-3.5 w-3.5 absolute right-3 top-1/2 -translate-y-1/2 text-[var(--text-muted)] pointer-events-none" />
                </div>
              </div>

              {/* Set Active Model Button */}
              <div className="flex flex-col sm:flex-row items-center justify-between gap-3 pt-1">
                <div className="text-xs text-[var(--text-muted)] flex items-center gap-2 font-mono">
                  <span>Selected:</span>
                  <span className="text-[var(--text-primary)] font-bold bg-[var(--bg-surface)] px-2 py-0.5 rounded border border-[var(--border-subtle)]">
                    {selectedModel}
                  </span>
                </div>

                <button
                  type="button"
                  onClick={handleSetActiveModel}
                  disabled={isSaving || !selectedModel || selectedModel === activeModel}
                  className="btn-primary h-8 px-4 text-xs gap-1.5"
                >
                  {isSaving ? (
                    <>
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      <span>Setting Active...</span>
                    </>
                  ) : selectedModel === activeModel ? (
                    <>
                      <CheckCircle2 className="h-3.5 w-3.5" />
                      <span>Active Model</span>
                    </>
                  ) : (
                    <>
                      <Cpu className="h-3.5 w-3.5" />
                      <span>Set Active Model</span>
                    </>
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* 3. All Providers Status Matrix */}
        <div className="loom-card space-y-4">
          <div className="flex items-center justify-between border-b border-[var(--border-subtle)] pb-2.5">
            <h3 className="text-xs font-bold text-[var(--text-primary)] uppercase tracking-wider font-mono flex items-center gap-2">
              <Server className="h-3.5 w-3.5 text-[var(--brand)]" />
              <span>Configured Providers Overview</span>
            </h3>
            <span className="text-[11px] font-mono text-[var(--text-muted)]">{Object.keys(PROVIDERS).length} Providers Supported</span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {(Object.keys(PROVIDERS) as ProviderKey[]).map(key => {
              const p = PROVIDERS[key];
              const isConfigured = providerConfigured[key];
              const models = detectedModels[key] || p.defaultModels;
              const hasActiveModel = models.includes(activeModel);

              return (
                <div
                  key={p.id}
                  onClick={() => {
                    setSelectedProvider(p.id);
                    setSelectedModel(models[0]);
                  }}
                  className={`p-3.5 rounded-xl border transition cursor-pointer ${
                    hasActiveModel
                      ? 'bg-[var(--brand-soft)] border-[var(--brand)]'
                      : 'bg-[var(--bg-elevated)] border-[var(--border-subtle)] hover:border-[var(--border-default)]'
                  }`}
                >
                  <div className="flex items-center justify-between mb-1.5">
                    <div className="flex items-center gap-2">
                      <span className="font-bold text-xs font-mono text-[var(--text-primary)]">{p.name}</span>
                      <span className="text-[10px] font-mono text-[var(--text-muted)] bg-[var(--bg-surface)] px-1.5 py-0.2 rounded border border-[var(--border-subtle)]">
                        {p.badge}
                      </span>
                    </div>
                    <span
                      className={`status-pill ${
                        isConfigured ? 'status-pill-verified' : 'status-pill-idle'
                      } text-[9px] py-0 px-1.5`}
                    >
                      {isConfigured ? 'Connected' : 'Not Configured'}
                    </span>
                  </div>

                  <p className="text-[11px] text-[var(--text-secondary)] font-mono mb-2 truncate">
                    Models: {models.slice(0, 3).join(', ')}
                    {models.length > 3 ? ` +${models.length - 3} more` : ''}
                  </p>

                  <div className="flex items-center justify-between pt-2 border-t border-[var(--border-subtle)] text-[10px] font-mono text-[var(--text-muted)]">
                    <span>{models.length} detected</span>
                    {hasActiveModel && (
                      <span className="text-[var(--brand-hover)] flex items-center gap-1 font-semibold">
                        <Check className="h-3 w-3 stroke-[3]" /> Active: {activeModel}
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </main>
    </div>
  );
}

export { ModelSettingsContent };

export default function ModelSettingsPage() {
  return (
    <AuthGate>
      <ModelSettingsContent />
    </AuthGate>
  );
}
