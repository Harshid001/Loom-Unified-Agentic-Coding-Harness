"use client";

import { X, Keyboard, Command } from 'lucide-react';

interface KeyboardShortcutsHelpProps {
  isOpen: boolean;
  onClose: () => void;
}

const SHORTCUTS = [
  { action: 'Launch New Run', keys: ['⌘', 'K'] },
  { action: 'View Evidence Tab', keys: ['⌘', 'E'] },
  { action: 'View Analytics Tab', keys: ['⌘', '⇧', 'A'] },
  { action: 'Switch to Overview', keys: ['⌘', '1'] },
  { action: 'Switch to DAG', keys: ['⌘', '2'] },
  { action: 'Switch to Agents', keys: ['⌘', '3'] },
  { action: 'Close Modals/Drawers', keys: ['Esc'] },
  { action: 'View Keyboard Shortcuts', keys: ['⌘', '/'] },
];

export const KeyboardShortcutsHelp: React.FC<KeyboardShortcutsHelpProps> = ({ isOpen, onClose }) => {
  if (!isOpen) return null;

  return (
    <>
      <div className="fixed inset-0 bg-[var(--bg-root)]/80 backdrop-blur-sm z-[200] animate-fade-in" onClick={onClose} />
      <div className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-full max-w-md bg-[var(--bg-surface)] border border-[var(--border-default)] rounded-xl shadow-2xl z-[201] animate-slide-in-from-top overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-[var(--border-subtle)] bg-[var(--bg-elevated)]">
          <div className="flex items-center gap-2">
            <Keyboard className="h-4 w-4 text-[var(--text-secondary)]" />
            <h2 className="text-sm font-bold font-mono text-[var(--text-primary)]">Keyboard Shortcuts</h2>
          </div>
          <button
            onClick={onClose}
            className="text-[var(--text-muted)] hover:text-[var(--text-primary)] transition rounded-md p-1"
            aria-label="Close shortcuts help"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Content */}
        <div className="p-2">
          {SHORTCUTS.map((shortcut, i) => (
            <div key={i} className="flex items-center justify-between p-3 rounded-lg hover:bg-[var(--bg-hover)] transition-colors">
              <span className="text-xs font-mono text-[var(--text-secondary)]">{shortcut.action}</span>
              <div className="flex items-center gap-1">
                {shortcut.keys.map((k, j) => (
                  <kbd key={j} className="kbd-hint">
                    {k === '⌘' ? <Command className="h-2.5 w-2.5 inline" /> : k}
                  </kbd>
                ))}
              </div>
            </div>
          ))}
        </div>

        {/* Footer */}
        <div className="p-3 bg-[var(--bg-elevated)] border-t border-[var(--border-subtle)] text-center">
          <p className="text-[10px] text-[var(--text-muted)] font-mono">
            Pro tip: Use <kbd className="kbd-hint bg-transparent border-none shadow-none text-[var(--text-primary)] mx-0.5"><Command className="h-2 w-2 inline"/>/</kbd> to toggle this menu anytime.
          </p>
        </div>
      </div>
    </>
  );
};
