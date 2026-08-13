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

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4 z-50"
      role="dialog"
      aria-modal="true"
    >
      <div className="bg-[#111827] border border-gray-800 rounded-xl p-6 max-w-md w-full shadow-2xl space-y-5">
        <div className="flex items-center justify-between border-b border-gray-800 pb-3">
          <div className="flex items-center gap-2 text-white font-bold text-base">
            <Key className="h-5 w-5 text-indigo-400" />
            <span>Manage Loom API Keys</span>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white p-1 rounded-lg hover:bg-gray-800 transition"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Key Generation Section */}
        <div className="space-y-3">
          <label className="block text-xs font-semibold text-gray-300 uppercase tracking-wider">
            Create New API Key
          </label>
          <div className="flex gap-2">
            <input
              type="text"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="Key label (e.g. dev_key)"
              className="flex-1 bg-gray-900 border border-gray-800 rounded-lg px-3 py-2 text-xs text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 font-mono"
            />
            <button
              onClick={handleGenerateKey}
              disabled={isGenerating || !label.trim()}
              className="flex items-center gap-1.5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white px-3 py-2 rounded-lg text-xs font-semibold transition"
            >
              {isGenerating ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}
              Generate
            </button>
          </div>
        </div>

        {/* Generated Key Alert Box */}
        {generatedKey && (
          <div className="bg-emerald-950/40 border border-emerald-800/60 rounded-xl p-3.5 space-y-2">
            <div className="flex items-center justify-between text-xs text-emerald-400 font-semibold">
              <span>API Key Generated! Copy now (won&apos;t be shown again)</span>
            </div>
            <div className="flex items-center gap-2 bg-gray-950 border border-emerald-900/50 rounded-lg p-2 font-mono text-xs text-emerald-300 overflow-x-auto">
              <span className="flex-1 truncate">{generatedKey}</span>
              <button
                onClick={handleCopy}
                className="flex items-center gap-1 bg-emerald-800/40 hover:bg-emerald-800/70 text-emerald-200 px-2 py-1 rounded text-[10px] transition"
              >
                {copied ? <Check className="h-3 w-3 text-emerald-300" /> : <Copy className="h-3 w-3" />}
                {copied ? 'Copied' : 'Copy'}
              </button>
            </div>
          </div>
        )}

        {error && (
          <div className="text-xs text-red-400 bg-red-950/40 border border-red-900/50 rounded-lg p-2">
            {error}
          </div>
        )}

        {/* Active Keys List */}
        <div className="space-y-2 pt-2 border-t border-gray-800">
          <div className="flex items-center justify-between text-xs font-semibold text-gray-400">
            <span>Active Keys ({tokens.length})</span>
            {isLoadingList && <Loader2 className="h-3 w-3 animate-spin text-gray-500" />}
          </div>

          {tokens.length === 0 ? (
            <p className="text-xs text-gray-500 italic py-2">No active API keys found.</p>
          ) : (
            <div className="max-h-40 overflow-y-auto space-y-1.5 pr-1">
              {tokens.map((tok) => (
                <div
                  key={tok.id}
                  className="flex items-center justify-between bg-gray-900 border border-gray-800 rounded-lg px-3 py-2 text-xs"
                >
                  <div>
                    <div className="font-semibold text-white flex items-center gap-2">
                      <span>{tok.label || 'API Key'}</span>
                      <span className="font-mono text-[10px] bg-gray-800 text-gray-400 px-1.5 py-0.5 rounded">
                        {tok.prefix}...
                      </span>
                    </div>
                    <div className="text-[10px] text-gray-500">ID: {tok.id}</div>
                  </div>
                  <button
                    onClick={() => handleRevoke(tok.id)}
                    title="Revoke key"
                    className="text-gray-500 hover:text-red-400 p-1 transition"
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
            className="px-4 py-1.5 bg-gray-800 hover:bg-gray-700 text-gray-300 text-xs font-medium rounded-lg transition"
          >
            Done
          </button>
        </div>
      </div>
    </div>
  );
};
