"use client";

import React, { useState } from 'react';
import Link from 'next/link';
import {
  Layers,
  Cpu,
  Activity,
  Settings,
  ChevronDown,
  Key,
  GitBranch,
  FolderGit2,
  ListTodo,
} from 'lucide-react';
import { Github } from './GithubIcon';
import { ConnectedRepoState, GitHubUser } from '../hooks/useGitHub';

interface HeaderProps {
  modelName: string;
  availableModels: string[];
  onModelChange: (model: string) => void;
  onOpenLiveBox: () => void;
  onOpenApiKeyModal?: () => void;
  onOpenRepoModal?: () => void;
  onOpenIssuesDrawer?: () => void;
  connectedRepo?: ConnectedRepoState | null;
  githubUser?: GitHubUser | null;
  runCount: number;
}

export const Header: React.FC<HeaderProps> = ({
  modelName,
  availableModels,
  onModelChange,
  onOpenLiveBox,
  onOpenApiKeyModal,
  onOpenRepoModal,
  onOpenIssuesDrawer,
  connectedRepo,
  githubUser,
  runCount,
}) => {
  const [showModelDropdown, setShowModelDropdown] = useState(false);

  return (
    <header
      className="border-b border-gray-800 bg-[#111827] px-6 py-3.5 flex items-center justify-between shrink-0 gap-4 flex-wrap"
      role="banner"
    >
      {/* Left Branding */}
      <div className="flex items-center space-x-4">
        <div
          className="h-9 w-9 rounded-lg bg-gradient-to-br from-indigo-600 to-indigo-800 flex items-center justify-center font-bold text-white shadow-lg shadow-indigo-500/30 shrink-0"
          aria-hidden="true"
        >
          <Layers className="h-5 w-5" />
        </div>
        <div>
          <h1 className="text-xl font-bold tracking-tight text-white flex items-center gap-2">
            Loom
            <span className="text-xs bg-indigo-500/20 text-indigo-400 px-2 py-0.5 rounded-full border border-indigo-500/30 font-medium">
              Harness Core
            </span>
          </h1>
          <p className="text-xs text-gray-400">Unified Agentic Coding Harness & Live Execution Dashboard</p>
        </div>
      </div>

      {/* Center / Right Action Controls */}
      <div className="flex items-center space-x-3 flex-wrap">
        {/* Connected Repository Pill */}
        {onOpenRepoModal && (
          <button
            onClick={onOpenRepoModal}
            className="flex items-center gap-2 text-xs bg-gray-900/90 border border-gray-800 hover:border-indigo-500/50 px-3 py-1.5 rounded-lg transition text-gray-200 group"
            title="Manage Connected Repository"
          >
            <FolderGit2 className="h-3.5 w-3.5 text-indigo-400 group-hover:scale-110 transition shrink-0" />
            <span className="font-mono text-xs max-w-[160px] truncate text-indigo-300">
              {connectedRepo?.fullName || 'Connect Repo'}
            </span>
            {connectedRepo?.selectedBranch && (
              <span className="text-[10px] bg-emerald-500/10 text-emerald-400 px-1.5 py-0.5 rounded border border-emerald-500/30 font-mono flex items-center gap-0.5">
                <GitBranch className="h-2.5 w-2.5" />
                {connectedRepo.selectedBranch}
              </span>
            )}
          </button>
        )}

        {/* GitHub Issues Drawer Button */}
        {connectedRepo && onOpenIssuesDrawer && (
          <button
            onClick={onOpenIssuesDrawer}
            className="hidden sm:flex items-center gap-1.5 text-xs text-indigo-300 bg-indigo-950/40 border border-indigo-500/30 hover:border-indigo-500 px-3 py-1.5 rounded-lg transition font-medium"
            title="Browse Open GitHub Issues"
          >
            <ListTodo className="h-3.5 w-3.5 text-indigo-400" />
            <span>GitHub Issues</span>
          </button>
        )}

        {/* GitHub Connection Badge */}
        {onOpenRepoModal && (
          <button
            onClick={onOpenRepoModal}
            className={`flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border transition font-medium ${
              githubUser
                ? 'bg-gray-900 border-indigo-500/40 text-gray-200 hover:border-indigo-500'
                : 'bg-gray-900 border-gray-800 text-gray-300 hover:border-gray-700'
            }`}
            title={githubUser ? `Connected as @${githubUser.login}` : 'Connect GitHub Account'}
          >
            {githubUser?.avatar_url ? (
              <img
                src={githubUser.avatar_url}
                alt={githubUser.login}
                className="h-4 w-4 rounded-full border border-indigo-400"
              />
            ) : (
              <Github size={14} className="text-indigo-400" />
            )}
            <span className="font-mono">
              {githubUser ? `@${githubUser.login}` : 'GitHub'}
            </span>
            {githubUser && (
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 shadow-sm shadow-emerald-400" />
            )}
          </button>
        )}

        {/* Total Runs Badge */}
        <div className="hidden lg:flex items-center gap-1.5 text-xs text-gray-400 bg-gray-900 border border-gray-800 px-3 py-1.5 rounded-lg">
          <Activity className="h-3.5 w-3.5 text-emerald-400" />
          <span className="font-mono">{runCount} runs</span>
        </div>

        {/* Model Settings Link */}
        <Link
          href="/settings/models"
          className="flex items-center gap-1.5 text-xs text-gray-300 bg-gray-900 border border-gray-800 px-3 py-1.5 rounded-lg hover:border-indigo-500/50 hover:text-white transition font-medium"
          title="Model Settings"
        >
          <Settings className="h-3.5 w-3.5 text-indigo-400" />
          <span className="hidden sm:inline">Model Settings</span>
        </Link>

        {/* API Key Modal Button */}
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

        {/* Model Dropdown */}
        <div className="relative">
          <button
            onClick={() => setShowModelDropdown(!showModelDropdown)}
            className="flex items-center gap-2 text-xs text-gray-400 bg-gray-900 border border-gray-800 px-3 py-1.5 rounded-lg hover:border-gray-700 transition"
          >
            <Cpu className="h-3.5 w-3.5 text-indigo-400" />
            <span className="font-mono max-w-[130px] truncate">{modelName}</span>
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
                    onClick={() => {
                      onModelChange(m);
                      setShowModelDropdown(false);
                    }}
                    className={`w-full text-left px-3 py-2 text-xs font-mono transition flex items-center gap-2 ${
                      m === modelName
                        ? 'bg-indigo-500/10 text-indigo-400 border-l-2 border-indigo-500'
                        : 'text-gray-400 hover:bg-gray-800/50 hover:text-white border-l-2 border-transparent'
                    }`}
                  >
                    <Cpu className="h-3 w-3 opacity-60" />
                    <span className="truncate">{m}</span>
                    {m === modelName && (
                      <span className="ml-auto text-[10px] bg-indigo-500/20 px-1.5 py-0.5 rounded shrink-0">
                        active
                      </span>
                    )}
                  </button>
                ))}
              </div>
            </>
          )}
        </div>

        {/* Live Box Trigger */}
        <button
          onClick={onOpenLiveBox}
          className="flex items-center gap-1.5 text-xs bg-gradient-to-r from-cyan-600 to-indigo-600 hover:from-cyan-500 hover:to-indigo-500 text-white px-4 py-2 rounded-lg font-semibold transition shadow-lg shadow-cyan-600/20 shrink-0"
        >
          ⚡ Open Live Box
        </button>
      </div>
    </header>
  );
};