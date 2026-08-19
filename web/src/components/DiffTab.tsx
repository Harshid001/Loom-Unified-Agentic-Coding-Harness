"use client";

import React, { useState, useMemo, useCallback } from 'react';
import { FileCode, Play, Copy, Check, ChevronDown, ChevronRight, File, Hash } from 'lucide-react';

interface DiffTabProps {
  displayData: any;
  onOpenLiveBox?: () => void;
}

/* ─── Syntax Tokenizer (Python / JS / TS) ─── */
const TOKEN_RULES: Array<{ className: string; pattern: RegExp }> = [
  { className: 'tok-comment', pattern: /(#[^\n]*|\/\/[^\n]*|\/\*[\s\S]*?\*\/)/g },
  { className: 'tok-decorator', pattern: /(@\w+)/g },
  { className: 'tok-string', pattern: /("""[\s\S]*?"""|'''[\s\S]*?'''|"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'|`(?:[^`\\]|\\.)*`)/g },
  { className: 'tok-keyword', pattern: /\b(def|class|import|from|return|if|elif|else|for|while|try|except|finally|with|as|yield|async|await|raise|pass|break|continue|lambda|not|and|or|in|is|None|True|False|self|const|let|var|function|export|default|interface|type|enum|extends|implements|new|this|super|throw|catch|typeof|instanceof|void|null|undefined|abstract|readonly)\b/g },
  { className: 'tok-builtin', pattern: /\b(print|len|range|str|int|float|list|dict|set|tuple|bool|map|filter|reduce|sorted|enumerate|zip|open|isinstance|hasattr|getattr|setattr|console|document|window|Promise|Array|Object|String|Number|Math|JSON|Error|require)\b/g },
  { className: 'tok-number', pattern: /\b(\d+\.?\d*(?:e[+-]?\d+)?|0x[\da-f]+|0o[0-7]+|0b[01]+)\b/gi },
  { className: 'tok-function', pattern: /\b([a-zA-Z_]\w*)(?=\s*\()/g },
];

function tokenizeLine(text: string): React.ReactNode {
  if (!text) return text;

  // Simple priority-based tokenization: apply rules in order, track occupied ranges
  interface Token { start: number; end: number; className: string; text: string; }
  const tokens: Token[] = [];
  const occupied = new Set<number>();

  for (const rule of TOKEN_RULES) {
    const regex = new RegExp(rule.pattern.source, rule.pattern.flags);
    let match;
    while ((match = regex.exec(text)) !== null) {
      const start = match.index;
      const end = start + match[0].length;
      let overlaps = false;
      for (let i = start; i < end; i++) {
        if (occupied.has(i)) { overlaps = true; break; }
      }
      if (!overlaps) {
        tokens.push({ start, end, className: rule.className, text: match[0] });
        for (let i = start; i < end; i++) occupied.add(i);
      }
    }
  }

  if (tokens.length === 0) return text;

  tokens.sort((a, b) => a.start - b.start);

  const parts: React.ReactNode[] = [];
  let cursor = 0;
  tokens.forEach((tok, i) => {
    if (tok.start > cursor) {
      parts.push(text.slice(cursor, tok.start));
    }
    parts.push(<span key={i} className={tok.className}>{tok.text}</span>);
    cursor = tok.end;
  });
  if (cursor < text.length) {
    parts.push(text.slice(cursor));
  }

  return <>{parts}</>;
}

/* ─── Parse multi-file diffs ─── */
interface DiffFile {
  filename: string;
  hunks: DiffHunk[];
}

interface DiffHunk {
  header: string;
  lines: DiffLine[];
}

interface DiffLine {
  type: 'add' | 'remove' | 'context' | 'header' | 'meta';
  content: string;
  oldLine?: number;
  newLine?: number;
}

function parseDiff(raw: string): DiffFile[] {
  if (!raw) return [];

  const files: DiffFile[] = [];
  const lines = raw.split('\n');
  let currentFile: DiffFile | null = null;
  let currentHunk: DiffHunk | null = null;
  let oldLine = 0;
  let newLine = 0;

  for (const line of lines) {
    // File header: diff --git a/... b/...
    if (line.startsWith('diff --git') || line.startsWith('--- a/') || line.startsWith('+++ b/')) {
      if (line.startsWith('diff --git')) {
        // Extract filename from "diff --git a/foo.py b/foo.py"
        const match = line.match(/diff --git a\/(.*?) b\/(.*)/);
        const name = match ? match[2] : 'unknown';
        currentFile = { filename: name, hunks: [] };
        files.push(currentFile);
      }
      continue;
    }

    // Hunk header: @@ -X,Y +A,B @@
    if (line.startsWith('@@')) {
      const match = line.match(/@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/);
      oldLine = match ? parseInt(match[1]) : 1;
      newLine = match ? parseInt(match[2]) : 1;
      currentHunk = { header: line, lines: [] };
      if (!currentFile) {
        currentFile = { filename: 'patch.diff', hunks: [] };
        files.push(currentFile);
      }
      currentFile.hunks.push(currentHunk);
      continue;
    }

    if (!currentHunk) {
      // Lines before any hunk — treat as meta for the current/new file
      if (line.startsWith('---') || line.startsWith('+++') || line.startsWith('index ') || line.startsWith('new file') || line.startsWith('deleted file')) {
        continue;
      }
      // If no file exists yet, create a generic one
      if (!currentFile && line.trim()) {
        currentFile = { filename: 'patch.diff', hunks: [] };
        files.push(currentFile);
        currentHunk = { header: '', lines: [] };
        currentFile.hunks.push(currentHunk);
      }
      if (!currentHunk) continue;
    }

    if (line.startsWith('+')) {
      currentHunk.lines.push({ type: 'add', content: line.slice(1), newLine: newLine++ });
    } else if (line.startsWith('-')) {
      currentHunk.lines.push({ type: 'remove', content: line.slice(1), oldLine: oldLine++ });
    } else {
      currentHunk.lines.push({ type: 'context', content: line.startsWith(' ') ? line.slice(1) : line, oldLine: oldLine++, newLine: newLine++ });
    }
  }

  // If no "diff --git" headers were found, wrap everything in a single file
  if (files.length === 0 && raw.trim()) {
    const singleFile: DiffFile = { filename: 'patch.diff', hunks: [] };
    const singleHunk: DiffHunk = { header: '', lines: [] };
    let ln = 1;
    for (const line of lines) {
      if (line.startsWith('@@')) {
        singleHunk.header = line;
        continue;
      }
      if (line.startsWith('+') && !line.startsWith('+++')) {
        singleHunk.lines.push({ type: 'add', content: line.slice(1), newLine: ln++ });
      } else if (line.startsWith('-') && !line.startsWith('---')) {
        singleHunk.lines.push({ type: 'remove', content: line.slice(1), oldLine: ln++ });
      } else if (!line.startsWith('diff') && !line.startsWith('---') && !line.startsWith('+++') && !line.startsWith('index')) {
        singleHunk.lines.push({ type: 'context', content: line.startsWith(' ') ? line.slice(1) : line, oldLine: ln, newLine: ln++ });
      }
    }
    singleFile.hunks.push(singleHunk);
    files.push(singleFile);
  }

  return files;
}

/* ─── Hunk Component ─── */
function DiffHunkView({ hunk, index, onCopyLine }: { hunk: DiffHunk; index: number; onCopyLine: (content: string) => void }) {
  const [collapsed, setCollapsed] = useState(false);

  return (
    <div>
      {hunk.header && (
        <button
          className="diff-hunk-toggle"
          onClick={() => setCollapsed(!collapsed)}
          aria-expanded={!collapsed}
        >
          {collapsed ? <ChevronRight className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
          <span>{hunk.header}</span>
          {collapsed && <span className="text-[var(--text-muted)] ml-auto">{hunk.lines.length} lines hidden</span>}
        </button>
      )}
      {!collapsed && (
        <div>
          {hunk.lines.map((line, i) => {
            let bgClass = '';
            let textClass = 'text-[var(--text-secondary)]';
            let prefix = ' ';

            if (line.type === 'add') {
              bgClass = 'bg-[var(--success)]/8';
              textClass = 'text-[var(--success)]';
              prefix = '+';
            } else if (line.type === 'remove') {
              bgClass = 'bg-[var(--danger)]/8';
              textClass = 'text-[var(--danger)]';
              prefix = '-';
            }

            return (
              <div key={`${index}-${i}`} className={`flex items-start ${bgClass} hover:bg-[var(--bg-hover)] transition-colors group`}>
                <span
                  className="diff-line-number"
                  onClick={() => onCopyLine(line.content)}
                  title="Click to copy line"
                >
                  {line.oldLine ?? ''}
                </span>
                <span
                  className="diff-line-number"
                  onClick={() => onCopyLine(line.content)}
                  title="Click to copy line"
                >
                  {line.newLine ?? ''}
                </span>
                <span className={`w-5 text-center font-mono text-[11px] shrink-0 select-none ${textClass}`}>
                  {prefix}
                </span>
                <pre className={`flex-1 font-mono text-[11px] whitespace-pre-wrap px-2 py-px ${textClass}`}>
                  {tokenizeLine(line.content)}
                </pre>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export const DiffTab: React.FC<DiffTabProps> = ({ displayData, onOpenLiveBox }) => {
  const [copied, setCopied] = useState(false);
  const [copiedLine, setCopiedLine] = useState(false);
  const [activeFileIdx, setActiveFileIdx] = useState(0);

  const parsedFiles = useMemo(() => {
    return displayData ? parseDiff(displayData.patchDiff || '') : [];
  }, [displayData]);

  const handleCopyLine = useCallback((content: string) => {
    navigator.clipboard.writeText(content);
    setCopiedLine(true);
    setTimeout(() => setCopiedLine(false), 1000);
  }, []);

  // ─── Empty State ───
  if (!displayData) {
    return (
      <div className="flex-1 loom-card relative overflow-hidden">
        <div className="flex flex-col items-center justify-center text-center gap-5 py-12 relative z-10">
          <div className="h-14 w-14 rounded-2xl bg-gradient-to-br from-[var(--brand-soft)] to-[var(--bg-elevated)] border border-[var(--brand)]/30 flex items-center justify-center text-[var(--brand)] shadow-lg shadow-[var(--brand)]/10">
            <FileCode className="h-6 w-6" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-[var(--text-primary)] font-mono mb-1">
              No Verified Patch Selected
            </h3>
            <p className="text-xs text-[var(--text-muted)] max-w-md mx-auto leading-relaxed">
              Loom&apos;s Patcher agent synthesizes surgical code diffs, verifies them in an isolated sandbox, and renders them here with syntax-aware highlighting, collapsible hunks, and multi-file navigation.
            </p>
          </div>

          {/* Mock Diff Preview */}
          <div className="w-full max-w-lg mock-diff-shimmer rounded-xl border border-[var(--border-subtle)] overflow-hidden text-left">
            <div className="bg-[var(--bg-elevated)] px-3 py-2 border-b border-[var(--border-subtle)] flex items-center gap-2">
              <File className="h-3 w-3 text-[var(--brand)]" />
              <span className="text-[10px] font-mono text-[var(--text-muted)]">src/utils/handler.py</span>
            </div>
            <div className="bg-[var(--bg-root)] font-mono text-[11px] p-0">
              {[
                { type: 'ctx', ln: 42, text: '    def process(self, data: Dict):' },
                { type: 'del', ln: 43, text: '        result = self._validate(data)' },
                { type: 'add', ln: 43, text: '        result = self._validate(data, strict=True)' },
                { type: 'ctx', ln: 44, text: '        if result.is_valid:' },
                { type: 'del', ln: 45, text: '            return self.execute(result)' },
                { type: 'add', ln: 45, text: '            return self.execute(result, timeout=30)' },
                { type: 'ctx', ln: 46, text: '        raise ValidationError(result.errors)' },
              ].map((line, i) => (
                <div
                  key={i}
                  className={`flex items-start ${
                    line.type === 'add' ? 'bg-[var(--success)]/8' : line.type === 'del' ? 'bg-[var(--danger)]/8' : ''
                  } opacity-60`}
                >
                  <span className="w-10 text-right px-2 text-[10px] text-[var(--text-muted)] select-none border-r border-[var(--border-subtle)]">
                    {line.ln}
                  </span>
                  <span className={`w-5 text-center text-[10px] ${
                    line.type === 'add' ? 'text-[var(--success)]' : line.type === 'del' ? 'text-[var(--danger)]' : 'text-[var(--text-muted)]'
                  }`}>
                    {line.type === 'add' ? '+' : line.type === 'del' ? '-' : ' '}
                  </span>
                  <pre className={`flex-1 px-2 py-px ${
                    line.type === 'add' ? 'text-[var(--success)]' : line.type === 'del' ? 'text-[var(--danger)]' : 'text-[var(--text-secondary)]'
                  }`}>
                    {tokenizeLine(line.text)}
                  </pre>
                </div>
              ))}
            </div>
          </div>

          <button
            onClick={onOpenLiveBox}
            aria-label="Launch run to generate verified patch"
            className="btn-primary gap-1.5"
          >
            <Play className="h-3.5 w-3.5 fill-current relative z-10" aria-hidden="true" />
            <span className="relative z-10">Launch Run to Generate Patch</span>
          </button>
        </div>
      </div>
    );
  }

  // ─── Active Diff View ───
  const patchDiff = displayData.patchDiff || '';

  const handleCopy = () => {
    navigator.clipboard.writeText(patchDiff);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const activeFile = parsedFiles[activeFileIdx] || parsedFiles[0];
  const addCount = activeFile?.hunks.reduce((sum, h) => sum + h.lines.filter(l => l.type === 'add').length, 0) || 0;
  const removeCount = activeFile?.hunks.reduce((sum, h) => sum + h.lines.filter(l => l.type === 'remove').length, 0) || 0;

  return (
    <div className="flex-1 loom-card flex flex-col gap-4" id="tabpanel-diff" role="tabpanel" aria-label="Verified unified patch diff viewer">
      <div className="flex items-center justify-between border-b border-[var(--border-subtle)] pb-3">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="text-xs font-bold text-[var(--text-primary)] uppercase tracking-wider font-mono">
              Verified Unified Patch Diff
            </h3>
            <span className="status-pill status-pill-verified text-[10px]">
              VALIDATED
            </span>
          </div>
          <p className="text-xs text-[var(--text-muted)] mt-0.5">
            {parsedFiles.length} file{parsedFiles.length !== 1 ? 's' : ''} changed · <span className="text-[var(--success)]">+{addCount}</span> <span className="text-[var(--danger)]">-{removeCount}</span>
          </p>
        </div>

        <div className="flex items-center gap-2">
          {copiedLine && (
            <span className="text-[10px] font-mono text-[var(--success)] animate-fade-in">Line copied</span>
          )}
          <button
            onClick={handleCopy}
            aria-label={copied ? "Patch diff copied to clipboard" : "Copy patch diff to clipboard"}
            className="btn-secondary h-8 px-3 text-xs gap-1.5"
          >
            {copied ? (
              <>
                <Check className="h-3.5 w-3.5 text-[var(--success)]" aria-hidden="true" />
                <span>Copied</span>
              </>
            ) : (
              <>
                <Copy className="h-3.5 w-3.5" aria-hidden="true" />
                <span>Copy Diff</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* Multi-file tabs */}
      {parsedFiles.length > 1 && (
        <div className="flex items-center gap-0 overflow-x-auto border-b border-[var(--border-subtle)]">
          {parsedFiles.map((file, idx) => (
            <button
              key={idx}
              className={`diff-file-tab ${activeFileIdx === idx ? 'active' : ''}`}
              onClick={() => setActiveFileIdx(idx)}
            >
              <File className="h-3 w-3" />
              <span className="truncate max-w-[160px]">{file.filename}</span>
            </button>
          ))}
        </div>
      )}

      {/* File header */}
      {activeFile && (
        <div className="flex items-center gap-2 px-1 text-[11px] font-mono text-[var(--text-muted)]">
          <File className="h-3.5 w-3.5 text-[var(--brand)]" />
          <span className="text-[var(--text-primary)] font-semibold">{activeFile.filename}</span>
          <span className="text-[var(--success)]">+{addCount}</span>
          <span className="text-[var(--danger)]">-{removeCount}</span>
        </div>
      )}

      {/* Diff content */}
      <div className="bg-[var(--bg-root)] border border-[var(--border-subtle)] rounded-xl overflow-hidden flex-1 overflow-x-auto">
        {activeFile?.hunks.map((hunk, idx) => (
          <DiffHunkView key={idx} hunk={hunk} index={idx} onCopyLine={handleCopyLine} />
        ))}
        {(!activeFile || activeFile.hunks.length === 0) && (
          <div className="p-6 text-center text-xs font-mono text-[var(--text-muted)]">
            No diff content to display.
          </div>
        )}
      </div>
    </div>
  );
};
