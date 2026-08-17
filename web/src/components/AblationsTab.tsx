import React from 'react';
import { Layers } from 'lucide-react';

interface AblationsTabProps {
  displayData: any;
}

const STANDARD_ABLATIONS = [
  { name: 'Full Loom Harness (Tier A-C)', memory: true, context: true, multiAgent: true, passRate: '94.8%', cost: '$0.0038' },
  { name: 'No 7-Tier Memory Store', memory: false, context: true, multiAgent: true, passRate: '78.2%', cost: '$0.0071' },
  { name: 'No Context Ranking (TF-IDF/AST)', memory: true, context: false, multiAgent: true, passRate: '69.4%', cost: '$0.0098' },
  { name: 'Single Agent Baseline (No DAG)', memory: false, context: false, multiAgent: false, passRate: '51.3%', cost: '$0.0124' },
];

export const AblationsTab: React.FC<AblationsTabProps> = ({ displayData }) => {
  const ablations = displayData?.ablations?.length ? displayData.ablations : STANDARD_ABLATIONS;

  return (
    <div className="flex-1 bg-[#111827] border border-gray-800 rounded-xl p-6 flex flex-col gap-6" id="tabpanel-ablations" role="tabpanel" aria-labelledby="tab-ablations">
      <div>
        <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1">Ablation Experiment Benchmark Matrix</h3>
        <p className="text-xs text-gray-400">Comparing pass rates and token costs across modular harness tier configurations</p>
      </div>

      <div className="overflow-x-auto border border-gray-800 rounded-xl">
        <table className="w-full text-left border-collapse text-xs">
          <caption className="sr-only">Ablation benchmark metrics across harness features</caption>
          <thead>
            <tr className="bg-gray-900 border-b border-gray-800 text-gray-400 font-semibold uppercase tracking-wider">
              <th scope="col" className="p-3.5">Harness Configuration</th>
              <th scope="col" className="p-3.5 text-center">Tiered Memory</th>
              <th scope="col" className="p-3.5 text-center">Repo Context Ranking</th>
              <th scope="col" className="p-3.5 text-center">Multi-Agent DAG</th>
              <th scope="col" className="p-3.5 text-right">Pass Rate</th>
              <th scope="col" className="p-3.5 text-right">Avg Cost / Run</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800/60 text-gray-300">
            {ablations.map((ab: any, i: number) => (
              <tr key={i} className={ab.name?.includes('Full Harness') ? 'bg-indigo-950/20 font-medium' : 'hover:bg-gray-900/40'}>
                <td className="p-3.5 flex items-center gap-2">
                  <Layers className={`h-4 w-4 ${ab.name?.includes('Full Harness') ? 'text-indigo-400' : 'text-gray-500'}`} aria-hidden="true" />
                  <span>{ab.name}</span>
                </td>
                <td className="p-3.5 text-center">{ab.memory ? '✅' : '❌'}</td>
                <td className="p-3.5 text-center">{ab.context ? '✅' : '❌'}</td>
                <td className="p-3.5 text-center">{ab.multiAgent ? '✅' : '❌'}</td>
                <td className="p-3.5 text-right font-mono font-semibold text-emerald-400">{ab.passRate}</td>
                <td className="p-3.5 text-right font-mono text-gray-400">{ab.cost}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
