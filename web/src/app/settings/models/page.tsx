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
  Layers,
  Zap,
  Server,
  ExternalLink,
} from 'lucide-react';

type ProviderKey = 'anthropic' | 'openai' | 'deepseek' | 'gemini';

interface ProviderMeta {
  id: ProviderKey;
  name: string;
  badge: string;
  badgeColor: string;
  colorBorder: string;
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
    badgeColor: 'bg-amber-500/20 text-amber-400 border-amber-500/30',
    colorBorder: 'border-amber-500/40',
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
    badgeColor: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
    colorBorder: 'border-emerald-500/40',
    placeholder: 'sk-proj-...',
    docUrl: 'https://platform.openai.com/api-keys',
    description: 'High-throughput tool-calling and reasoning models including GPT-4o, GPT-4o-mini, and o3-mini.',
    defaultModels: ['gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo', 'o1', 'o1-mini', 'o3-mini'],
  },
  deepseek: {
    id: 'deepseek',
    name: 'DeepSeek',
    badge: 'V3 / Reasoner',
    badgeColor: 'bg-cyan-500/20 text-cyan-400 border-cyan-500/30',
    colorBorder: 'border-cyan-500/40',
    placeholder: 'sk-...',
    docUrl: 'https://platform.deepseek.com/api_keys',
    description: 'Cost-efficient frontier open-architecture models optimized for coding and mathematical reasoning.',
    defaultModels: ['deepseek-chat', 'deepseek-reasoner', 'deepseek-v3', 'deepseek/deepseek-chat'],
  },
  gemini: {
    id: 'gemini',
    name: 'Google Gemini',
    badge: 'Gemini 1.5/2.0',
    badgeColor: 'bg-purple-500/20 text-purple-400 border-purple-500/30',
    colorBorder: 'border-purple-500/40',
    placeholder: 'AIzaSy...',
    docUrl: 'https://aistudio.google.com/app/apikey',
    description: 'Ultra-long context window models with 1M+ token capacity and fast multimodal generation.',
    defaultModels: ['gemini-1.5-pro', 'gemini-1.5-flash', 'gemini-2.0-flash', 'gemini-pro'],
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
  });
  const [showKey, setShowKey] = useState<Record<ProviderKey, boolean>>({
    anthropic: false,
    openai: false,
    deepseek: false,
    gemini: false,
  });

  const [activeModel, setActiveModel] = useState<string>('claude-3-5-sonnet-20241022');
  const [selectedModel, setSelectedModel] = useState<string>('claude-3-5-sonnet-20241022');
  const [detectedModels, setDetectedModels] = useState<Record<ProviderKey, string[]>>({
    anthropic: PROVIDERS.anthropic.defaultModels,
    openai: PROVIDERS.openai.defaultModels,
    deepseek: PROVIDERS.deepseek.defaultModels,
    gemini: PROVIDERS.gemini.defaultModels,
  });

  const [providerConfigured, setProviderConfigured] = useState<Record<ProviderKey, boolean>>({
    anthropic: false,
    openai: false,
    deepseek: false,
    gemini: false,
  });

  const [isDetecting, setIsDetecting] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isLoadingConfig, setIsLoadingConfig] = useState(true);
  const [feedback, setFeedback] = useState<{ type: 'success' | 'error' | 'info'; message: string } | null>(null);

  // Fetch initial config from backend
  const fetchConfig = async () => {
    setIsLoadingConfig(true);
    try {
      const res = await fetch('/api/settings/model');
      if (res.ok) {
        const data: ModelConfig = await res.json();
        if (data.active_model) {
          setActiveModel(data.active_model);
          setSelectedModel(data.active_model);
        }
        if (data.providers) {
          const updatedConfigured: Record<ProviderKey, boolean> = {
            anthropic: data.providers.anthropic?.configured || false,
            openai: data.providers.openai?.configured || false,
            deepseek: data.providers.deepseek?.configured || false,
            gemini: data.providers.gemini?.configured || false,
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

    try {
      const res = await fetch('/api/models/detect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
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

    try {
      const res = await fetch('/api/settings/model', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          model: selectedModel,
          provider: selectedProvider,
          api_key: apiKeys[selectedProvider]?.trim() || undefined,
        }),
      });

      const data = await res.json();
      if (res.ok) {
        setActiveModel(selectedModel);
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
    <div className="min-h-screen bg-[#0d1117] text-gray-100 flex flex-col font-sans selection:bg-indigo-500 selection:text-white">
      {/* Header Bar */}
      <header className="border-b border-gray-800 bg-[#111827] px-6 py-4 flex items-center justify-between shrink-0">
        <div className="flex items-center space-x-4">
          <Link
            href="/"
            className="flex items-center gap-2 text-xs text-gray-400 hover:text-white bg-gray-900 border border-gray-800 px-3 py-1.5 rounded-lg transition"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            <span>Dashboard</span>
          </Link>
          <div className="h-5 w-px bg-gray-800" />
          <div className="flex items-center gap-2">
            <div className="h-8 w-8 rounded-lg bg-gradient-to-br from-indigo-600 to-indigo-800 flex items-center justify-center text-white shadow-lg shadow-indigo-500/20">
              <Cpu className="h-4 w-4" />
            </div>
            <div>
              <h1 className="text-lg font-bold tracking-tight text-white flex items-center gap-2">
                Model Settings
                <span className="text-[10px] bg-indigo-500/20 text-indigo-400 px-2 py-0.5 rounded-full border border-indigo-500/30 font-medium">
                  Dynamic Router
                </span>
              </h1>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 text-xs bg-gray-900 border border-gray-800 px-3 py-1.5 rounded-lg">
            <span className="text-gray-500">Active Model:</span>
            <span className="font-mono text-indigo-400 font-medium flex items-center gap-1.5">
              <Sparkles className="h-3 w-3 text-indigo-400 animate-pulse" />
              {activeModel}
            </span>
          </div>

          <button
            onClick={fetchConfig}
            disabled={isLoadingConfig}
            className="p-1.5 text-gray-400 hover:text-white bg-gray-900 border border-gray-800 rounded-lg hover:border-gray-700 transition disabled:opacity-50"
            title="Refresh configuration"
            aria-label="Refresh configuration"
          >
            <RefreshCw className={`h-4 w-4 ${isLoadingConfig ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="flex-1 max-w-5xl w-full mx-auto p-6 space-y-6">
        {/* Banner Card */}
        <div className="bg-gradient-to-r from-indigo-950/40 via-gray-900 to-gray-900 border border-indigo-500/20 rounded-2xl p-6 relative overflow-hidden">
          <div className="absolute right-0 top-0 w-96 h-96 bg-indigo-600/5 rounded-full blur-3xl pointer-events-none" />
          <div className="relative z-10">
            <h2 className="text-xl font-bold text-white mb-2 flex items-center gap-2">
              <Zap className="h-5 w-5 text-indigo-400" />
              Runtime Model Detection & Switching
            </h2>
            <p className="text-sm text-gray-400 max-w-2xl leading-relaxed">
              Connect your frontier model provider keys. Loom dynamically discovers supported models via LiteLLM,
              overrides runtime environment keys per session, and enables instant fallback-aware model routing.
            </p>
          </div>
        </div>

        {/* Feedback Alert */}
        {feedback && (
          <div
            className={`p-4 rounded-xl border flex items-start gap-3 transition-all ${
              feedback.type === 'success'
                ? 'bg-emerald-950/40 border-emerald-500/30 text-emerald-300'
                : feedback.type === 'error'
                ? 'bg-red-950/40 border-red-500/30 text-red-300'
                : 'bg-indigo-950/40 border-indigo-500/30 text-indigo-300'
            }`}
            role="alert"
          >
            {feedback.type === 'success' ? (
              <CheckCircle2 className="h-5 w-5 text-emerald-400 shrink-0 mt-0.5" />
            ) : feedback.type === 'error' ? (
              <AlertCircle className="h-5 w-5 text-red-400 shrink-0 mt-0.5" />
            ) : (
              <Shield className="h-5 w-5 text-indigo-400 shrink-0 mt-0.5" />
            )}
            <div className="text-sm leading-relaxed flex-1">{feedback.message}</div>
            <button
              onClick={() => setFeedback(null)}
              className="text-xs opacity-60 hover:opacity-100 transition px-1"
              aria-label="Dismiss alert"
            >
              ✕
            </button>
          </div>
        )}

        {/* Provider Tabs */}
        <div className="bg-[#111827] border border-gray-800 rounded-2xl p-6 space-y-6">
          <div>
            <label className="text-xs font-semibold text-gray-400 uppercase tracking-wider block mb-3">
              Select Provider
            </label>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
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
                    className={`p-3.5 rounded-xl border text-left transition flex flex-col justify-between relative overflow-hidden ${
                      isSelected
                        ? `bg-indigo-950/40 ${p.colorBorder} shadow-lg shadow-indigo-950/50`
                        : 'bg-gray-900/60 border-gray-800 hover:border-gray-700 hover:bg-gray-850'
                    }`}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <span className="font-semibold text-sm text-white">{p.name}</span>
                      {isConfigured && (
                        <span className="h-2 w-2 rounded-full bg-emerald-400 shadow-sm shadow-emerald-400/50" title="Configured" />
                      )}
                    </div>
                    <div className="flex items-center justify-between">
                      <span className={`text-[10px] px-2 py-0.5 rounded-full border font-medium ${p.badgeColor}`}>
                        {p.badge}
                      </span>
                      {isSelected && <Check className="h-3.5 w-3.5 text-indigo-400" />}
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Provider Configuration Card */}
          <div className="bg-gray-900/70 border border-gray-800/80 rounded-xl p-5 space-y-5">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-4 border-b border-gray-800/80">
              <div>
                <h3 className="text-base font-bold text-white flex items-center gap-2">
                  <span>{currentProviderMeta.name} Authentication</span>
                  {providerConfigured[selectedProvider] && (
                    <span className="text-[10px] bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 px-2 py-0.5 rounded-full">
                      Ready
                    </span>
                  )}
                </h3>
                <p className="text-xs text-gray-400 mt-1">{currentProviderMeta.description}</p>
              </div>
              <a
                href={currentProviderMeta.docUrl}
                target="_blank"
                rel="noreferrer"
                className="text-xs text-indigo-400 hover:text-indigo-300 flex items-center gap-1 shrink-0"
              >
                <span>Get API Key</span>
                <ExternalLink className="h-3 w-3" />
              </a>
            </div>

            {/* API Key Input Field */}
            <div className="space-y-2">
              <label htmlFor="api-key-input" className="text-xs font-medium text-gray-300 flex items-center justify-between">
                <span>{currentProviderMeta.name} API Key</span>
                <span className="text-[11px] text-gray-500">Stored in memory per session</span>
              </label>

              <div className="flex flex-col sm:flex-row gap-3">
                <div className="relative flex-1">
                  <Key className="h-4 w-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
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
                    className="w-full bg-black/40 border border-gray-800 rounded-xl pl-9 pr-10 py-2.5 text-xs font-mono text-gray-200 placeholder-gray-600 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition"
                  />
                  <button
                    type="button"
                    onClick={() =>
                      setShowKey(prev => ({
                        ...prev,
                        [selectedProvider]: !prev[selectedProvider],
                      }))
                    }
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300 transition"
                    title={showKey[selectedProvider] ? 'Hide key' : 'Show key'}
                    aria-label={showKey[selectedProvider] ? 'Hide API key' : 'Show API key'}
                  >
                    {showKey[selectedProvider] ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>

                <button
                  type="button"
                  onClick={handleDetect}
                  disabled={isDetecting || !apiKeys[selectedProvider]?.trim()}
                  className="px-5 py-2.5 bg-gradient-to-r from-indigo-600 to-indigo-700 hover:from-indigo-500 hover:to-indigo-600 text-white text-xs font-semibold rounded-xl transition flex items-center justify-center gap-2 shadow-lg shadow-indigo-600/20 disabled:opacity-40 disabled:cursor-not-allowed shrink-0"
                >
                  {isDetecting ? (
                    <>
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      <span>Detecting...</span>
                    </>
                  ) : (
                    <>
                      <Sparkles className="h-3.5 w-3.5" />
                      <span>Test & Detect</span>
                    </>
                  )}
                </button>
              </div>
            </div>

            {/* Model Selection Dropdown & Action */}
            <div className="pt-4 border-t border-gray-800/80 space-y-4">
              <div>
                <label htmlFor="detected-model-select" className="text-xs font-semibold text-gray-300 block mb-2">
                  Detected {currentProviderMeta.name} Models ({currentDetectedModels.length})
                </label>

                <div className="relative">
                  <select
                    id="detected-model-select"
                    value={selectedModel}
                    onChange={e => setSelectedModel(e.target.value)}
                    className="w-full appearance-none bg-black/40 border border-gray-800 rounded-xl px-4 py-3 text-xs font-mono text-gray-200 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition pr-10 cursor-pointer"
                  >
                    {currentDetectedModels.map(m => (
                      <option key={m} value={m} className="bg-gray-900 text-gray-200 font-mono py-1">
                        {m} {m === activeModel ? '★ (Current Active)' : ''}
                      </option>
                    ))}
                  </select>
                  <ChevronDown className="h-4 w-4 absolute right-3.5 top-1/2 -translate-y-1/2 text-gray-500 pointer-events-none" />
                </div>
              </div>

              {/* Set Active Model Button */}
              <div className="flex flex-col sm:flex-row items-center justify-between gap-3 pt-2">
                <div className="text-xs text-gray-400 flex items-center gap-2">
                  <span>Selected Model:</span>
                  <span className="font-mono text-white bg-gray-800 px-2 py-0.5 rounded border border-gray-700">
                    {selectedModel}
                  </span>
                </div>

                <button
                  type="button"
                  onClick={handleSetActiveModel}
                  disabled={isSaving || !selectedModel || selectedModel === activeModel}
                  className={`w-full sm:w-auto px-6 py-2.5 text-xs font-semibold rounded-xl transition flex items-center justify-center gap-2 shadow-lg ${
                    selectedModel === activeModel
                      ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 cursor-default'
                      : 'bg-gradient-to-r from-cyan-600 to-indigo-600 hover:from-cyan-500 hover:to-indigo-500 text-white shadow-indigo-600/20'
                  } disabled:opacity-50`}
                >
                  {isSaving ? (
                    <>
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      <span>Setting Active Model...</span>
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

        {/* All Providers Status Matrix */}
        <div className="bg-[#111827] border border-gray-800 rounded-2xl p-6 space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-gray-300 uppercase tracking-wider flex items-center gap-2">
              <Server className="h-4 w-4 text-indigo-400" />
              Configured Providers Overview
            </h3>
            <span className="text-xs text-gray-500">4 Providers Supported</span>
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
                  className={`p-4 rounded-xl border transition ${
                    hasActiveModel
                      ? 'bg-indigo-950/30 border-indigo-500/40'
                      : 'bg-gray-900/40 border-gray-800/80'
                  }`}
                >
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-xs text-white">{p.name}</span>
                      <span className={`text-[9px] px-1.5 py-0.5 rounded font-medium ${p.badgeColor}`}>
                        {p.badge}
                      </span>
                    </div>
                    <span
                      className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${
                        isConfigured
                          ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/20'
                          : 'bg-gray-800 text-gray-500 border border-gray-700'
                      }`}
                    >
                      {isConfigured ? 'Connected' : 'Not Configured'}
                    </span>
                  </div>

                  <p className="text-[11px] text-gray-400 font-mono mb-2 truncate">
                    Models: {models.slice(0, 3).join(', ')}
                    {models.length > 3 ? ` +${models.length - 3} more` : ''}
                  </p>

                  <div className="flex items-center justify-between pt-2 border-t border-gray-800/60 text-[10px]">
                    <span className="text-gray-500">{models.length} detected</span>
                    {hasActiveModel && (
                      <span className="text-indigo-400 font-mono flex items-center gap-1 font-semibold">
                        <Check className="h-3 w-3" /> Active: {activeModel}
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
