import React, { useEffect } from 'react';
import { Loader2 } from 'lucide-react';

interface NewRunModalProps {
  isOpen: boolean;
  onClose: () => void;
  newIssue: string;
  setNewIssue: (val: string) => void;
  isExecuting: boolean;
  onSubmit: () => void;
}

export const NewRunModal: React.FC<NewRunModalProps> = ({
  isOpen,
  onClose,
  newIssue,
  setNewIssue,
  isExecuting,
  onSubmit
}) => {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!isOpen) return;
      if (e.key === 'Escape') {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div 
      className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4 z-50"
      role="dialog"
      aria-modal="true"
      aria-labelledby="modal-title"
    >
      <div className="bg-[#111827] border border-gray-800 rounded-xl p-6 max-w-lg w-full shadow-2xl space-y-4">
        <h2 id="modal-title" className="text-lg font-bold text-white flex items-center justify-between">
          <span>Start New Loom Harness Run</span>
          <button 
            onClick={onClose}
            aria-label="Close dialog"
            className="text-gray-400 hover:text-white text-sm"
          >
            ✕
          </button>
        </h2>
        <p className="text-xs text-gray-400">
          Enter an issue description to trigger the multi-agent DAG task pipeline (Reproduction, Patch Proposal, Verification).
        </p>

        <div>
          <label 
            htmlFor="issue-description-input" 
            className="block text-xs font-semibold text-gray-300 uppercase tracking-wider mb-2"
          >
            Issue Description / Prompt
          </label>
          <textarea
            id="issue-description-input"
            rows={4}
            value={newIssue}
            onChange={(e) => setNewIssue(e.target.value)}
            placeholder="e.g. Fix memory leak when processing large JSON payloads in telemetry tracer"
            className="w-full bg-gray-900 border border-gray-800 rounded-lg p-3 text-xs text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 font-mono"
            aria-required="true"
          />
        </div>

        <div className="flex items-center justify-end gap-3 pt-2">
          <button
            onClick={onClose}
            disabled={isExecuting}
            className="px-4 py-2 text-xs font-medium text-gray-400 hover:text-white transition focus:outline-none"
          >
            Cancel
          </button>
          <button
            onClick={onSubmit}
            disabled={isExecuting || !newIssue.trim()}
            className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded-lg text-xs font-medium transition shadow-md shadow-indigo-600/20 focus:ring-2 focus:ring-indigo-400 focus:outline-none"
          >
            {isExecuting && <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />}
            {isExecuting ? 'Dispatching Run...' : 'Execute Harness Run'}
          </button>
        </div>
      </div>
    </div>
  );
};
