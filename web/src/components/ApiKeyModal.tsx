"use client";

import React, { useState, useEffect, useCallback } from 'react';
import { Key, Copy, Check, Trash2, Loader2, Plus, X } from 'lucide-react';

interface ApiToken {
  id: string;
  user_id: string;
  org_id: string;
  label: string;
  prefix: string;
  active: boolean;
  created_at: number;
}

interface ApiKeyModalProps {
  isOpen: boolean;
  onClose: () => void;
  onKeyGenerated?: (token: string) => void;
}

export const ApiKeyModal: React.FC<ApiKeyModalProps> = ({
  isOpen,
  onClose,
  onKeyGenerated,
}) => {
  const [label, setLabel] = useState('dashboard_key');
  const [tokens, setTokens] = useState<ApiToken[]>([]);
  const [generatedKey, setGeneratedKey] = useState<string | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [isLoadingList, setIsLoadingList] = useState(false);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchTokens = useCallback(async () => {
    setIsLoadingList(true);
    try {
      const res = await fetch('/api/v1/auth/tokens');
      if (res.ok) {
        const data = await res.json();
        setTokens(data);
      }
    } catch {
      // Ignore network errors in mock environments
    } finally {
      setIsLoadingList(false);
    }
  }, []);

  useEffect(() => {
    if (isOpen) {
      fetchTokens();
      setGeneratedKey(null);
      setError(null);
    }
  }, [isOpen, fetchTokens]);

  const handleGenerateKey = async () => {
    setIsGenerating(true);
    setError(null);
    try {
      const res = await fetch('/api/v1/auth/tokens', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: 'dev_user', org_id: 'default', label }),
      });

      if (!res.ok) {
        throw new Error('Failed to generate API key');
      }

      const data = await res.json();
      setGeneratedKey(data.token);
      if (onKeyGenerated) {
        onKeyGenerated(data.token);
      }
      fetchTokens();
    } catch (err: any) {
      setError(err.message || 'Error generating key');
    } finally {
      setIsGenerating(false);
    }
  };

  const handleCopy = () => {
    if (generatedKey) {
      navigator.clipboard.writeText(generatedKey);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handleRevoke = async (tokenId: string) => {
    try {
      const res = await fetch(`/api/v1/auth/tokens/${tokenId}`, { method: 'DELETE' });
      if (res.ok) {
        fetchTokens();
      }
    } catch {
      // Ignore errors
    }
  };

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!isOpen) return;
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 bg-black/85 backdrop-blur-md flex items-center justify-center p-4 z-50 animate-fadeIn cursor-pointer"
      role="dialog"
      aria-modal="true"
      onClick={onClose}
    >
      <div
        className="bg-[var(--bg-surface)] border border-[var(--border-default)] rounded-2xl p-6 max-w-md w-full shadow-2xl space-y-4 cursor-default"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-[var(--border-subtle)] pb-3">
          <div className="flex items-center gap-2">
            <div className="h-7 w-7 rounded-lg bg-[var(--brand-soft)] border border-[var(--brand)]/30 flex items-center justify-center text-[var(--brand)]">
              <Key className="h-3.5 w-3.5" />
            </div>
            <span className="text-xs font-bold font-mono text-[var(--text-primary)] uppercase">
              Manage Loom API Keys
            </span>
          </div>
          <button
            onClick={onClose}
            className="text-[var(--text-muted)] hover:text-[var(--text-primary)] p-1 rounded-lg hover:bg-[var(--bg-hover)] transition"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Key Generation Section */}
        <div className="space-y-2">
          <label className="block text-[11px] font-mono font-bold text-[var(--text-muted)] uppercase">
            Create New API Key
          </label>
          <div className="flex gap-2">
            <input
              type="text"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="Key label (e.g. dev_key)"
              className="flex-1 bg-[var(--bg-root)] border border-[var(--border-subtle)] focus:border-[var(--brand)] rounded-lg px-3 py-1.5 text-xs text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:outline-none font-mono"
            />
            <button
              onClick={handleGenerateKey}
              disabled={isGenerating || !label.trim()}
              className="btn-primary h-8 px-3 text-xs gap-1.5"
            >
              {isGenerating ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}
              <span>Generate</span>
            </button>
          </div>
        </div>

        {/* Generated Key Alert Box */}
        {generatedKey && (
          <div className="bg-[var(--success)]/10 border border-[var(--success)]/30 rounded-xl p-3 space-y-2">
            <div className="flex items-center justify-between text-xs text-[var(--success)] font-semibold font-mono">
              <span>API Key Generated! Copy now (one-time view)</span>
            </div>
            <div className="flex items-center gap-2 bg-[var(--bg-root)] border border-[var(--border-subtle)] rounded-lg p-2 font-mono text-xs text-[var(--text-primary)] overflow-x-auto">
              <span className="flex-1 truncate">{generatedKey}</span>
              <button
                onClick={handleCopy}
                className="btn-secondary h-6 px-2 text-[10px] gap-1"
              >
                {copied ? <Check className="h-3 w-3 text-[var(--success)]" /> : <Copy className="h-3 w-3" />}
                <span>{copied ? 'Copied' : 'Copy'}</span>
              </button>
            </div>
          </div>
        )}

        {error && (
          <div className="text-xs text-[var(--danger)] bg-[var(--danger)]/10 border border-[var(--danger)]/30 rounded-lg p-2 font-mono">
            {error}
          </div>
        )}

        {/* Active Keys List */}
        <div className="space-y-2 pt-2 border-t border-[var(--border-subtle)]">
          <div className="flex items-center justify-between text-xs font-mono font-bold text-[var(--text-muted)] uppercase">
            <span>Active Keys ({tokens.length})</span>
            {isLoadingList && <Loader2 className="h-3 w-3 animate-spin text-[var(--brand)]" />}
          </div>

          {tokens.length === 0 ? (
            <p className="text-xs text-[var(--text-muted)] italic py-2">No active API keys found.</p>
          ) : (
            <div className="max-h-40 overflow-y-auto space-y-1.5 pr-1">
              {tokens.map((tok) => (
                <div
                  key={tok.id}
                  className="flex items-center justify-between bg-[var(--bg-elevated)] border border-[var(--border-subtle)] rounded-lg px-3 py-2 text-xs"
                >
                  <div>
                    <div className="font-semibold text-[var(--text-primary)] flex items-center gap-2">
                      <span>{tok.label || 'API Key'}</span>
                      <span className="font-mono text-[10px] bg-[var(--bg-surface)] text-[var(--text-muted)] px-1.5 py-0.2 rounded border border-[var(--border-subtle)]">
                        {tok.prefix}...
                      </span>
                    </div>
                    <div className="text-[10px] text-[var(--text-muted)] font-mono">ID: {tok.id}</div>
                  </div>
                  <button
                    onClick={() => handleRevoke(tok.id)}
                    title="Revoke key"
                    className="text-[var(--text-muted)] hover:text-[var(--danger)] p-1 transition"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="flex justify-end pt-2">
          <button
            onClick={onClose}
            className="btn-secondary h-8 px-4 text-xs"
          >
            Done
          </button>
        </div>
      </div>
    </div>
  );
};
