import { useEffect, useCallback } from 'react';

interface ShortcutActions {
  onNewRun?: () => void;
  onSwitchTab?: (index: number) => void;
  onEscape?: () => void;
  onEvidence?: () => void;
  onAnalytics?: () => void;
  tabCount?: number;
}

export function useKeyboardShortcuts({
  onNewRun,
  onSwitchTab,
  onEscape,
  onEvidence,
  onAnalytics,
  tabCount = 9,
}: ShortcutActions) {
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    const isCmd = e.metaKey || e.ctrlKey;
    const target = e.target as HTMLElement;

    // Don't trigger shortcuts when typing in inputs
    if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable) {
      if (e.key === 'Escape') {
        onEscape?.();
      }
      return;
    }

    // Cmd+K — New Run
    if (isCmd && e.key === 'k') {
      e.preventDefault();
      onNewRun?.();
      return;
    }

    // Cmd+E — Evidence tab
    if (isCmd && e.key === 'e') {
      e.preventDefault();
      onEvidence?.();
      return;
    }

    // Cmd+Shift+A — Analytics
    if (isCmd && e.shiftKey && (e.key === 'a' || e.key === 'A')) {
      e.preventDefault();
      onAnalytics?.();
      return;
    }

    // Cmd+1-9 — Switch tabs
    if (isCmd && e.key >= '1' && e.key <= '9') {
      const idx = parseInt(e.key) - 1;
      if (idx < tabCount) {
        e.preventDefault();
        onSwitchTab?.(idx);
        return;
      }
    }

    // Escape — Close modals
    if (e.key === 'Escape') {
      onEscape?.();
      return;
    }
  }, [onNewRun, onSwitchTab, onEscape, onEvidence, onAnalytics, tabCount]);

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);
}
