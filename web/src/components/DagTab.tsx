import React, { useState } from 'react';
import { ArrowRight, ArrowDown, CheckCircle2, Loader2, XCircle, Info, GitBranch } from 'lucide-react';

interface DagTabProps {
  displayData: any;
  onOpenLiveBox?: () => void;
}

interface DAGNode {
  id: string;
  label: string;
  detail: string;
  status: string;
  duration?: string;
  cost?: string;
  model?: string;
  logs?: string[];
}

export const DagTab: React.FC<DagTabProps> = ({ displayData, onOpenLiveBox }) => {
  const [expandedNode, setExpandedNode] = useState<string | null>(null);

  const isDemo = !displayData;
  const nodes: DAGNode[] = [
    {
      id: 'onboarding',
      label: '1. Repo Mapper',
      detail: 'AST Index & Call Graph',
      status: displayData?.nodes?.[0]?.status || 'completed',
      duration: displayData?.nodes?.[0]?.duration || '0.8s',
      cost: displayData?.nodes?.[0]?.cost || '$0.0003',
      model: 'AST Parser',
    },
    {
      id: 'reproduction',
      label: '2. Reproduction Agent',
      detail: 'Synthesize Failing Test',
      status: displayData?.nodes?.[1]?.status || 'completed',
      duration: displayData?.nodes?.[1]?.duration || '1.1s',
      cost: displayData?.nodes?.[1]?.cost || '$0.0005',
      model: 'Frontier LLM',
    },
    {
      id: 'patcher',
      label: '3. Patcher Agent',
      detail: 'Surgical Code Diff',
      status: displayData?.nodes?.[2]?.status || 'completed',
      duration: displayData?.nodes?.[2]?.duration || '1.4s',
      cost: displayData?.nodes?.[2]?.cost || '$0.0025',
      model: displayData?.model || 'gemini-1.5-pro',
    },
    {
      id: 'verifier',
      label: '4. Verification Runner',
      detail: 'Sandbox Pytest Suite',
      status: displayData?.nodes?.[3]?.status || 'completed',
      duration: displayData?.nodes?.[3]?.duration || '0.9s',
      cost: displayData?.nodes?.[3]?.cost || '$0.0002',
    },
    {
      id: 'reviewer',
      label: '5. Evidence Reviewer',
      detail: 'SHA-256 Hash Chaining',
      status: displayData?.nodes?.[4]?.status || 'completed',
      duration: displayData?.nodes?.[4]?.duration || '0.6s',
      cost: displayData?.nodes?.[4]?.cost || '$0.0003',
      model: 'Auditor',
    },
  ];

  const completedCount = nodes.filter(n => n.status === 'completed').length;
  const progressPercent = (completedCount / nodes.length) * 100;

  const statusIcon = (status: string) => {
    if (status === 'running') return <Loader2 className="h-4 w-4 text-amber-400 animate-spin" />;
    if (status === 'completed') return <CheckCircle2 className="h-4 w-4 text-emerald-400" />;
    if (status === 'failed') return <XCircle className="h-4 w-4 text-red-400" />;
    return <div className="h-4 w-4 rounded-full border-2 border-gray-600" />;
  };

  return (
    <div className="flex-1 bg-[#111827] border border-gray-800 rounded-xl p-6 flex flex-col gap-5" id="tabpanel-dag" role="tabpanel" aria-labelledby="tab-dag">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1">DAG Task Graph Topology</h3>
          <p className="text-xs text-gray-500">Sequential multi-agent execution pipeline with feedback loops</p>
        </div>
        <div className="flex items-center gap-3">
          <div className="w-24 h-1.5 bg-gray-800 rounded-full overflow-hidden">
            <div className="h-full bg-indigo-500 rounded-full transition-all duration-700" style={{ width: `${progressPercent}%` }} />
          </div>
          <span className="text-[10px] text-gray-500 font-mono">{completedCount}/{nodes.length}</span>
        </div>
      </div>

      <div className="flex-1 flex flex-col justify-center gap-4 p-6 bg-gray-950/40 rounded-xl border border-gray-800/80">
        <div className="flex flex-col lg:flex-row items-center justify-center gap-3 max-w-5xl mx-auto w-full">
          {nodes.map((node, i) => {
            const isExpanded = expandedNode === node.id;
            const nodeStatus = node.status;

            return (
              <React.Fragment key={node.id}>
                <div className="flex flex-col items-center w-full lg:w-44">
                  <button
                    onClick={() => setExpandedNode(isExpanded ? null : node.id)}
                    className={`w-full flex flex-col items-center bg-gray-900 border px-3 py-3 rounded-xl shadow-lg text-center transition hover:border-gray-600 ${
                      nodeStatus === 'completed' ? 'border-emerald-500/30 shadow-emerald-950/20' :
                      nodeStatus === 'running' ? 'border-amber-500/30 shadow-amber-950/20 animate-pulse' :
                      nodeStatus === 'failed' ? 'border-red-500/30 shadow-red-950/20' :
                      'border-gray-700/50'
                    }`}
                  >
                    <div className="mb-2">{statusIcon(nodeStatus)}</div>
                    <span className="text-[11px] font-bold text-white mb-0.5">{node.label}</span>
                    <span className="text-[10px] text-gray-400">{node.detail}</span>
                    {(node.duration && node.duration !== '--') && (
                      <div className="flex items-center gap-2 mt-2 text-[9px] font-mono text-gray-500">
                        <span>{node.duration}</span>
                        {node.cost && node.cost !== '--' && <span>{node.cost}</span>}
                      </div>
                    )}
                  </button>

                  {isExpanded && (
                    <div className="w-full mt-1 p-2.5 bg-gray-950 rounded-lg border border-gray-800 text-[10px] space-y-1.5">
                      <div className="flex items-center justify-between">
                        <span className="text-gray-400">Agent: <span className="text-indigo-400 font-mono">{node.id}</span></span>
                        <span className={`font-semibold uppercase ${nodeStatus === 'completed' ? 'text-emerald-400' : nodeStatus === 'running' ? 'text-amber-400' : nodeStatus === 'failed' ? 'text-red-400' : 'text-gray-500'}`}>{nodeStatus}</span>
                      </div>
                      {node.model && <div className="text-gray-500">Model: {node.model}</div>}
                      {node.duration && <div className="text-gray-500">Duration: {node.duration}</div>}
                      {node.cost && <div className="text-gray-500">Cost: {node.cost}</div>}
                    </div>
                  )}
                </div>

                {i < nodes.length - 1 && (
                  <div className="flex flex-col items-center text-gray-600 shrink-0">
                    <ArrowRight className="h-4 w-4 hidden lg:block" aria-hidden="true" />
                    <ArrowDown className="h-4 w-4 lg:hidden" aria-hidden="true" />
                  </div>
                )}
              </React.Fragment>
            );
          })}
        </div>
      </div>
    </div>
  );
};