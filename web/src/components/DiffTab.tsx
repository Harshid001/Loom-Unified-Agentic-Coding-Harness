import React from 'react';
import { FileCode } from 'lucide-react';

interface DiffTabProps {
  displayData: any;
  onOpenLiveBox?: () => void;
}

export const DiffTab: React.FC<DiffTabProps> = ({ displayData, onOpenLiveBox }) => {
  if (!displayData) {
    return (
      <div className="flex-1 bg-[#111827] border border-gray-800 rounded-xl p-8 flex flex-col items-center justify-center text-center gap-4">
        <div className="h-16 w-16 rounded-2xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400">
          <FileCode className="h-8 w-8" />
        </div>
        <div>
          <h3 className="text-sm font-bold text-white mb-1">No Verified Patch Selected</h3>
          <p className="text-xs text-gray-400 max-w-md">
            When an autonomous run executes, Loom&apos;s Patcher agent synthesizes a surgical code diff, verifies it in an isolated sandbox, and renders it here with syntax-highlighted additions and removals.
          </p>
        </div>
        <button
          onClick={onOpenLiveBox}
          className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-xs font-semibold transition flex items-center gap-2"
        >
          <span>Launch Run to Generate Patch</span>
        </button>
      </div>
    );
  }

  const diffLines = displayData.patchDiff.split('\n');

  return (
    <div className="flex-1 bg-[#111827] border border-gray-800 rounded-xl p-6 flex flex-col gap-4" id="tabpanel-diff" role="tabpanel" aria-labelledby="tab-diff">
      <div className="flex items-center justify-between border-b border-gray-800 pb-4">
        <div>
          <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1">Verified Unified Patch Diff</h3>
          <p className="text-xs text-gray-400">Generated patch validated by test harness execution</p>
        </div>
        <span className="text-xs bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 px-2.5 py-1 rounded-md font-mono flex items-center gap-1.5">
          <FileCode className="h-3.5 w-3.5" aria-hidden="true" /> Unified Diff Format
        </span>
      </div>

      <div className="bg-gray-950 border border-gray-800 rounded-xl p-4 font-mono text-xs overflow-x-auto flex-1 text-gray-300 space-y-1">
        {diffLines.map((line: string, i: number) => {
          let colorClass = 'text-gray-300';
          if (line.startsWith('+') && !line.startsWith('+++')) colorClass = 'text-emerald-400 bg-emerald-950/30 px-1 rounded';
          else if (line.startsWith('-') && !line.startsWith('---')) colorClass = 'text-red-400 bg-red-950/30 px-1 rounded';
          else if (line.startsWith('@@')) colorClass = 'text-indigo-400 font-semibold';
          else if (line.startsWith('---') || line.startsWith('+++')) colorClass = 'text-gray-500 font-semibold';

          return (
            <div key={i} className={`flex items-start gap-4 ${colorClass}`}>
              <span className="text-gray-600 select-none w-8 text-right font-mono text-[11px]">{i + 1}</span>
              <pre className="font-mono whitespace-pre-wrap">{line}</pre>
            </div>
          );
        })}
      </div>
    </div>
  );
};
