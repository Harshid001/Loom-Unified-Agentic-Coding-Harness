import React from 'react';
import { Layers, Cpu } from 'lucide-react';

interface HeaderProps {
  modelName?: string;
  onOpenModal: () => void;
}

export const Header: React.FC<HeaderProps> = ({ modelName = 'claude-3-5-sonnet-20241022', onOpenModal }) => {
  return (
    <header className="border-b border-gray-800 bg-[#111827] px-6 py-4 flex items-center justify-between" role="banner">
      <div className="flex items-center space-x-3">
        <div 
          className="h-9 w-9 rounded-lg bg-indigo-600 flex items-center justify-center font-bold text-white shadow-lg shadow-indigo-500/30"
          aria-hidden="true"
        >
          <Layers className="h-5 w-5" />
        </div>
        <div>
          <h1 className="text-xl font-bold tracking-tight text-white flex items-center gap-2">
            Loom <span className="text-xs bg-indigo-500/20 text-indigo-400 px-2 py-0.5 rounded-full border border-indigo-500/30 font-medium">Harness Core</span>
          </h1>
          <p className="text-xs text-gray-400">Unified Agentic Coding Harness & Evidence Trace Viewer</p>
        </div>
      </div>

      <div className="flex items-center space-x-4">
        <span 
          className="text-xs text-gray-400 flex items-center gap-1.5 bg-gray-900 border border-gray-800 px-3 py-1.5 rounded-md"
          aria-label={`Current LLM Model: ${modelName}`}
        >
          <Cpu className="h-3.5 w-3.5 text-indigo-400" aria-hidden="true" /> Model: {modelName}
        </span>
        <button 
          onClick={onOpenModal}
          aria-label="Start new execution run"
          className="flex items-center gap-1.5 text-xs bg-indigo-600 hover:bg-indigo-500 text-white px-3.5 py-1.5 rounded-md font-medium transition shadow-md shadow-indigo-600/20 focus:ring-2 focus:ring-indigo-400 focus:outline-none"
        >
          + Start New Run
        </button>
      </div>
    </header>
  );
};
