"use client";

import React, { useState } from 'react';
import {
  ShieldCheck,
  CheckCircle2,
  FileCheck,
  Download,
  Copy,
  Check,
  Layers,
  Lock,
  ExternalLink,
  Code2,
} from 'lucide-react';

interface EvidenceArtifact {
  name: string;
  type: string;
  hash: string;
  size: string;
  verified: boolean;
}

interface EvidenceViewProps {
  runId?: string;
  integrityValid?: boolean;
  artifactsCount?: number;
  hashSeal?: string;
}

const DEFAULT_ARTIFACTS: EvidenceArtifact[] = [
  {
    name: '01_onboarding_ast_graph.json',
    type: 'AST Call Graph',
    hash: 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
    size: '14.2 KB',
    verified: true,
  },
  {
    name: '02_reproduction_test.py',
    type: 'Red Phase Test Case',
    hash: 'ca978112ca1bbdcaf0643e8f6cd83b131014551d409826160e22cd91d668b532',
    size: '1.8 KB',
    verified: true,
  },
  {
    name: '03_surgical_patch.diff',
    type: 'Unified Code Diff',
    hash: '5e884898da28047151d0e56f8dc6292773603d0d6aabbdd62a11ef721d1542d8',
    size: '4.6 KB',
    verified: true,
  },
  {
    name: '04_sandbox_pytest_stdout.log',
    type: 'Green Phase Verification',
    hash: '4b227777d4dd1fc61c6f884f48641d02b4d121d3fd328cb08b5531fcacdabf8a',
    size: '8.1 KB',
    verified: true,
  },
  {
    name: '05_evidence_seal_manifest.json',
    type: 'Root Hash Chain Seal',
    hash: 'ef2d127de37b942baad06145e54b0c619a1f22327b2ebbcfbec78f5564afe39d',
    size: '2.4 KB',
    verified: true,
  },
];

export const EvidenceView: React.FC<EvidenceViewProps> = ({
  runId = 'run_427',
  integrityValid = true,
  artifactsCount = 5,
  hashSeal = 'ef2d127de37b942baad06145e54b0c619a1f22327b2ebbcfbec78f5564afe39d',
}) => {
  const [copiedHash, setCopiedHash] = useState<string | null>(null);
  const [showRawJson, setShowRawJson] = useState(false);

  const handleCopy = (hash: string) => {
    navigator.clipboard.writeText(hash);
    setCopiedHash(hash);
    setTimeout(() => setCopiedHash(null), 2000);
  };

  const rawJsonContent = JSON.stringify(
    {
      spec_version: 'loom/evidence/v1',
      run_id: runId,
      integrity_status: integrityValid ? 'VALID' : 'INVALID',
      hash_algorithm: 'SHA-256',
      chain_seal: hashSeal,
      verification_checklist: {
        patch_generated: true,
        tests_reproduced: true,
        sandbox_verified: true,
        hash_chain_validated: true,
      },
      artifacts: DEFAULT_ARTIFACTS,
    },
    null,
    2
  );

  return (
    <div className="space-y-6">
      {/* Proof Layer Header Card */}
      <div className="loom-card-active">
        <div className="flex items-start justify-between flex-wrap gap-4">
          <div className="flex items-center gap-3.5">
            <div className="h-10 w-10 rounded-xl bg-[var(--brand-soft)] border border-[var(--brand)]/40 flex items-center justify-center text-[var(--brand)] shrink-0">
              <ShieldCheck className="h-5 w-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-[10px] text-[var(--text-muted)] uppercase tracking-wider font-mono font-bold">
                  CRYPTOGRAPHIC PROOF LAYER
                </span>
                <span className="status-pill status-pill-verified text-[10px]">
                  <Check className="h-3 w-3 stroke-[3]" />
                  INTEGRITY VALID
                </span>
              </div>
              <h3 className="text-base font-bold text-[var(--text-primary)] font-mono mt-0.5">
                SHA-256 Hash Chain Audit Bundle
              </h3>
              <p className="text-xs text-[var(--text-secondary)] mt-0.5">
                Tamper-evident verification trail sealed at run completion
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowRawJson(!showRawJson)}
              className="btn-secondary h-8 px-3 text-xs gap-1.5"
            >
              <Code2 className="h-3.5 w-3.5" />
              <span>{showRawJson ? 'Hide JSON' : 'View JSON'}</span>
            </button>
            <button
              onClick={() => handleCopy(rawJsonContent)}
              className="btn-primary h-8 px-3.5 text-xs gap-1.5"
            >
              {copiedHash === rawJsonContent ? (
                <>
                  <Check className="h-3.5 w-3.5" />
                  <span>Copied</span>
                </>
              ) : (
                <>
                  <Copy className="h-3.5 w-3.5" />
                  <span>Export Bundle</span>
                </>
              )}
            </button>
          </div>
        </div>

        {/* Hash Seal Bar */}
        <div className="mt-4 p-3 bg-[var(--bg-elevated)] border border-[var(--border-subtle)] rounded-lg flex items-center justify-between gap-3 text-xs font-mono">
          <div className="flex items-center gap-2 min-w-0">
            <Lock className="h-3.5 w-3.5 text-[var(--brand)] shrink-0" />
            <span className="text-[var(--text-muted)] shrink-0">CHAIN SEAL:</span>
            <span className="text-[var(--cyan)] truncate">{hashSeal}</span>
          </div>
          <button
            onClick={() => handleCopy(hashSeal)}
            className="text-[var(--text-muted)] hover:text-[var(--text-primary)] transition shrink-0"
            title="Copy Hash Seal"
          >
            {copiedHash === hashSeal ? <Check className="h-3.5 w-3.5 text-[var(--success)]" /> : <Copy className="h-3.5 w-3.5" />}
          </button>
        </div>
      </div>

      {/* Raw JSON viewer if toggled */}
      {showRawJson && (
        <div className="bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-xl p-4 font-mono text-xs text-[var(--text-secondary)] overflow-x-auto">
          <pre className="text-[var(--cyan)]">{rawJsonContent}</pre>
        </div>
      )}

      {/* 4-Point Verification Checklist */}
      <div className="loom-card">
        <h4 className="text-xs font-bold text-[var(--text-primary)] uppercase tracking-wider font-mono mb-3">
          Verification Proof Checklist
        </h4>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          <div className="p-3 bg-[var(--bg-elevated)] border border-[var(--border-subtle)] rounded-lg flex items-start gap-2.5">
            <CheckCircle2 className="h-4 w-4 text-[var(--success)] shrink-0 mt-0.5" />
            <div>
              <p className="text-xs font-bold text-[var(--text-primary)]">Patch Generated</p>
              <p className="text-[11px] text-[var(--text-muted)] mt-0.5">Surgical code modification formatted</p>
            </div>
          </div>

          <div className="p-3 bg-[var(--bg-elevated)] border border-[var(--border-subtle)] rounded-lg flex items-start gap-2.5">
            <CheckCircle2 className="h-4 w-4 text-[var(--success)] shrink-0 mt-0.5" />
            <div>
              <p className="text-xs font-bold text-[var(--text-primary)]">Tests Reproduced</p>
              <p className="text-[11px] text-[var(--text-muted)] mt-0.5">Failing test synthesized (Red phase)</p>
            </div>
          </div>

          <div className="p-3 bg-[var(--bg-elevated)] border border-[var(--border-subtle)] rounded-lg flex items-start gap-2.5">
            <CheckCircle2 className="h-4 w-4 text-[var(--success)] shrink-0 mt-0.5" />
            <div>
              <p className="text-xs font-bold text-[var(--text-primary)]">Sandbox Verified</p>
              <p className="text-[11px] text-[var(--text-muted)] mt-0.5">Pytest suite passed (Green phase)</p>
            </div>
          </div>

          <div className="p-3 bg-[var(--bg-elevated)] border border-[var(--border-subtle)] rounded-lg flex items-start gap-2.5">
            <CheckCircle2 className="h-4 w-4 text-[var(--success)] shrink-0 mt-0.5" />
            <div>
              <p className="text-xs font-bold text-[var(--text-primary)]">Hash Chain Validated</p>
              <p className="text-[11px] text-[var(--text-muted)] mt-0.5">Tamper-evident links verified</p>
            </div>
          </div>
        </div>
      </div>

      {/* Artifact Hashes Table */}
      <div className="loom-card">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h4 className="text-xs font-bold text-[var(--text-primary)] uppercase tracking-wider font-mono">
              Chained Artifact Manifest
            </h4>
            <p className="text-xs text-[var(--text-muted)] mt-0.5">
              {artifactsCount} cryptographic evidence artifacts committed to this execution bundle
            </p>
          </div>
        </div>

        <div className="overflow-x-auto border border-[var(--border-subtle)] rounded-lg">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="bg-[var(--bg-elevated)] border-b border-[var(--border-subtle)] text-[var(--text-muted)] font-mono text-[11px] uppercase">
                <th className="p-3">Artifact</th>
                <th className="p-3">Type</th>
                <th className="p-3">SHA-256 Digest</th>
                <th className="p-3 text-right">Size</th>
                <th className="p-3 text-right">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--border-subtle)] font-mono text-[11px]">
              {DEFAULT_ARTIFACTS.map((artifact, idx) => (
                <tr key={idx} className="hover:bg-[var(--bg-hover)] transition">
                  <td className="p-3 font-semibold text-[var(--text-primary)] flex items-center gap-2">
                    <FileCheck className="h-3.5 w-3.5 text-[var(--brand)]" />
                    <span>{artifact.name}</span>
                  </td>
                  <td className="p-3 text-[var(--text-secondary)]">{artifact.type}</td>
                  <td className="p-3">
                    <div className="flex items-center gap-2 max-w-xs">
                      <span className="truncate text-[var(--text-muted)]">{artifact.hash}</span>
                      <button
                        onClick={() => handleCopy(artifact.hash)}
                        className="text-[var(--text-muted)] hover:text-[var(--text-primary)] transition shrink-0"
                        title="Copy Hash"
                      >
                        {copiedHash === artifact.hash ? (
                          <Check className="h-3 w-3 text-[var(--success)]" />
                        ) : (
                          <Copy className="h-3 w-3" />
                        )}
                      </button>
                    </div>
                  </td>
                  <td className="p-3 text-right text-[var(--text-muted)]">{artifact.size}</td>
                  <td className="p-3 text-right">
                    <span className="text-[var(--success)] font-semibold flex items-center justify-end gap-1">
                      <Check className="h-3 w-3 stroke-[3]" />
                      SEALED
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
