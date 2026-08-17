"use client";

import React, { useState } from 'react';
import Link from 'next/link';
import { Layers, Cpu, Search, Activity, Settings, ChevronDown, Key } from 'lucide-react';

interface HeaderProps {
  modelName: string;
  availableModels: string[];
  onModelChange: (model: string) => void;
  onOpenLiveBox: () => void;
  onOpenApiKeyModal?: () => void;
  runCount: number;
}

export const Header: React.FC<HeaderProps> = ({
  modelName,
  availableModels,
  onModelChange,
  onOpenLiveBox,
  onOpenApiKeyModal,
  runCount,
}) => {
  const [showModelDropdown, setShowModelDropdown] = useState(false);

  return (
    <header className="border-b border-gray-800 bg-[#111827] px-6 py-4 flex items-center justify-between shrink-0" role="banner">
      <div className="flex items-center space-x-4">
        <div
          className="h-9 w-9 rounded-lg bg-gradient-to-br from-indigo-600 to-indigo-800 flex items-center justify-center font-bold text-white shadow-lg shadow-indigo-500/30"
          aria-hidden="true"
        >
          <Layers className="h-5 w-5" />
        </div>
        <div>
          <h1 className="text-xl font-bold tracking-tight text-white flex items-center gap-2">
            Loom
            <span className="text-xs bg-indigo-500/20 text-indigo-400 px-2 py-0.5 rounded-full border border-indigo-500/30 font-medium">Harness Core</span>
          </h1>
          <p className="text-xs text-gray-400">Unified Agentic Coding Harness & Live Execution Dashboard</p>
        </div>
      </div>

      <div className="flex items-center space-x-3">
        <div className="hidden md:flex items-center gap-1.5 text-xs text-gray-400 bg-gray-900 border border-gray-800 px-3 py-1.5 rounded-lg">
          <Activity className="h-3.5 w-3.5 text-emerald-400" />
          <span className="font-mono">{runCount} runs</span>
        </div>

        <Link
          href="/settings/models"
          className="flex items-center gap-1.5 text-xs text-gray-300 bg-gray-900 border border-gray-800 px-3 py-1.5 rounded-lg hover:border-indigo-500/50 hover:text-white transition font-medium"
          title="Model Settings"
        >
          <Settings className="h-3.5 w-3.5 text-indigo-400" />
          <span>Model Settings</span>
        </Link>

        {onOpenApiKeyModal && (
          <button
            onClick={onOpenApiKeyModal}
            className="flex items-center gap-1.5 text-xs text-gray-300 bg-gray-900 border border-gray-800 px-3 py-1.5 rounded-lg hover:border-indigo-500/50 hover:text-white transition font-medium"
            title="Manage API Keys"
          >
            <Key className="h-3.5 w-3.5 text-indigo-400" />
            <span>API Key</span>
          </button>
        )}

        <div className="relative">
          <button
            onClick={() => setShowModelDropdown(!showModelDropdown)}
            className="flex items-center gap-2 text-xs text-gray-400 bg-gray-900 border border-gray-800 px-3 py-1.5 rounded-lg hover:border-gray-700 transition"
          >
            <Cpu className="h-3.5 w-3.5 text-indigo-400" />
            <span className="font-mono max-w-[160px] truncate">{modelName}</span>
            <ChevronDown className="h-3 w-3" />
          </button>
          {showModelDropdown && (
            <>
              <div className="fixed inset-0 z-10" onClick={() => setShowModelDropdown(false)} />
              <div className="absolute right-0 mt-1.5 w-64 bg-[#111827] border border-gray-800 rounded-xl shadow-2xl z-20 py-1.5 overflow-hidden">
                <div className="px-3 py-1.5 text-[10px] text-gray-500 uppercase tracking-wider font-semibold flex items-center justify-between">
                  <span>Select Model</span>
                  <Link href="/settings/models" className="text-indigo-400 hover:underline text-[10px]">
                    Configure
                  </Link>
                </div>
                {availableModels.map(m => (
                  <button
                    key={m}
                    onClick={() => { onModelChange(m); setShowModelDropdown(false); }}
                    className={`w-full text-left px-3 py-2 text-xs font-mono transition flex items-center gap-2 ${
                      m === modelName
                        ? 'bg-indigo-500/10 text-indigo-400 border-l-2 border-indigo-500'
                        : 'text-gray-400 hover:bg-gray-800/50 hover:text-white border-l-2 border-transparent'
                    }`}
                  >
                    <Cpu className="h-3 w-3 opacity-60" />
                    {m}
                    {m === modelName && <span className="ml-auto text-[10px] bg-indigo-500/20 px-1.5 py-0.5 rounded">active</span>}
                  </button>
                ))}
              </div>
            </>
          )}
        </div>

        <button
          onClick={onOpenLiveBox}
          className="flex items-center gap-1.5 text-xs bg-gradient-to-r from-cyan-600 to-indigo-600 hover:from-cyan-500 hover:to-indigo-500 text-white px-4 py-2 rounded-lg font-semibold transition shadow-lg shadow-cyan-600/20"
        >
          ⚡ Open Live Box
        </button>
      </div>
    </header>
  );
};