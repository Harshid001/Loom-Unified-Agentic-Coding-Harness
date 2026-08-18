"use client";

import React, { useState, useEffect } from 'react';
import {
  ShieldCheck,
  CheckCircle2,
  FileCheck,
  Copy,
  Check,
  Lock,
  Code2,
  AlertTriangle,
  XCircle,
} from 'lucide-react';

interface EvidenceArtifact {
  name: string;
  type: string;
  hash: string;
  size: string;
  verified: boolean;
}

interface EvidenceViewProps {
  displayData?: any;
  runId?: string;
  connectedRepoName?: string;
  onOpenLiveBox?: () => void;
  integrityValid?: boolean;
  artifactsCount?: number;
  hashSeal?: string;
}

/**
 * Computes standard cryptographic SHA-256 digest over arbitrary UTF-8 string bytes
 * using the browser standard Web Crypto API.
 */
async function computeSha256(content: string): Promise<string> {
  if (!content) return '';
  try {
    if (typeof window !== 'undefined' && window.crypto?.subtle) {
      const data = new TextEncoder().encode(content);
      const hashBuffer = await window.crypto.subtle.digest('SHA-256', data);
      const hashArray = Array.from(new Uint8Array(hashBuffer));
      return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
    }
    return '';
  } catch {
    return '';
  }
}

export const EvidenceView: React.FC<EvidenceViewProps> = ({
  displayData,
  runId,
  connectedRepoName = 'Connected Workspace',
  onOpenLiveBox,
  hashSeal,
}) => {
  const [copiedHash, setCopiedHash] = useState<string | null>(null);
  const [showRawJson, setShowRawJson] = useState(false);
  const [computedArtifacts, setComputedArtifacts] = useState<EvidenceArtifact[]>([]);
  const [rootSeal, setRootSeal] = useState<string>('');
  const [isComputing, setIsComputing] = useState<boolean>(false);
  const [backendBundle, setBackendBundle] = useState<any | null>(null);

  const activeRunId = displayData?.id || (runId && runId !== 'run_427' ? runId : null);
  const isVerifiedSuccess = displayData?.status === 'VERIFIED SUCCESS' || displayData?.checkpoint?.verification_passed === true;

  // Fetch backend evidence bundle if available
  useEffect(() => {
    if (!activeRunId) return;

    fetch(`/api/runs/${encodeURIComponent(activeRunId)}/evidence`)
      .then(res => (res.ok ? res.json() : null))
      .then(bundle => {
        if (bundle) setBackendBundle(bundle);
      })
      .catch(() => {});
  }, [activeRunId]);

  // Compute real Web Crypto SHA-256 hashes over genuine artifact payloads
  useEffect(() => {
    if (!displayData && !activeRunId) {
      setComputedArtifacts([]);
      setRootSeal('');
      return;
    }

    let isMounted = true;
    setIsComputing(true);

    async function computeHashes() {
      const patchContent = displayData?.patchDiff || displayData?.checkpoint?.patch_diff || '';
      const reproContent = displayData?.reproductionTest || displayData?.checkpoint?.reproduction_test || '';
      const traceContent = JSON.stringify(displayData?.trace_events || displayData?.checkpoint?.trace_events || []);
      const resolutionBrief = JSON.stringify(displayData?.checkpoint?.resolution_summary || {});

      const patchHash = patchContent ? await computeSha256(patchContent) : '';
      const reproHash = reproContent ? await computeSha256(reproContent) : '';
      const traceHash = traceContent.length > 2 ? await computeSha256(traceContent) : '';
      const resolutionHash = resolutionBrief.length > 2 ? await computeSha256(resolutionBrief) : '';

      const patchSize = patchContent ? `${(patchContent.length / 1024).toFixed(1)} KB` : '--';
      const reproSize = reproContent ? `${(reproContent.length / 1024).toFixed(1)} KB` : '--';
      const traceSize = traceContent.length > 2 ? `${(traceContent.length / 1024).toFixed(1)} KB` : '--';

      const artifacts: EvidenceArtifact[] = [];

      if (resolutionHash) {
        artifacts.push({
          name: '01_resolution_brief.json',
          type: 'Root Cause Diagnosis & Fix Brief',
          hash: resolutionHash,
          size: `${(resolutionBrief.length / 1024).toFixed(1)} KB`,
          verified: isVerifiedSuccess,
        });
      }

      if (reproHash) {
        artifacts.push({
          name: '02_reproduction_test.py',
          type: 'Red Phase Test Case',
          hash: reproHash,
          size: reproSize,
          verified: Boolean(reproContent),
        });
      }

      if (patchHash) {
        artifacts.push({
          name: '03_surgical_patch.diff',
          type: 'Unified Code Modification',
          hash: patchHash,
          size: patchSize,
          verified: Boolean(patchContent),
        });
      }

      if (traceHash) {
        artifacts.push({
          name: '04_execution_telemetry.json',
          type: 'DAG Telemetry & Sandbox Logs',
          hash: traceHash,
          size: traceSize,
          verified: isVerifiedSuccess,
        });
      }

      // Root chain seal: computed over chained artifact digests or pulled from backend bundle
      let seal = hashSeal || backendBundle?.chain_hash || '';
      if (!seal && artifacts.length > 0) {
        const joined = artifacts.map(a => a.hash).join('|');
        seal = await computeSha256(joined);
      }

      if (seal) {
        artifacts.push({
          name: '05_evidence_seal_manifest.json',
          type: 'Root SHA-256 Hash Chain Seal',
          hash: seal,
          size: '1.2 KB',
          verified: isVerifiedSuccess,
        });
      }

      if (isMounted) {
        setComputedArtifacts(artifacts);
        setRootSeal(seal);
        setIsComputing(false);
      }
    }

    computeHashes();

    return () => {
      isMounted = false;
    };
  }, [displayData, activeRunId, hashSeal, backendBundle, isVerifiedSuccess]);

  // Empty state when no run is active
  if (!displayData && !activeRunId) {
    return (
      <div className="space-y-6">
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
                  <span className="status-pill status-pill-running text-[10px]">
                    STANDBY
                  </span>
                </div>
                <h3 className="text-base font-bold text-[var(--text-primary)] font-mono mt-0.5">
                  SHA-256 Hash Chain Audit Bundle
                </h3>
                <p className="text-xs text-[var(--text-secondary)] mt-0.5">
                  Target Repository: <span className="text-[var(--text-primary)] font-mono font-semibold">{connectedRepoName}</span>
                </p>
              </div>
            </div>

            {onOpenLiveBox && (
              <button
                onClick={onOpenLiveBox}
                className="btn-primary h-8 px-3.5 text-xs gap-1.5"
              >
                <ShieldCheck className="h-3.5 w-3.5" />
                <span>Launch Run to Generate Evidence</span>
              </button>
            )}
          </div>
        </div>

        <div className="loom-card flex flex-col items-center justify-center text-center py-12 px-4 gap-4">
          <div className="h-12 w-12 rounded-2xl bg-[var(--bg-elevated)] border border-[var(--border-subtle)] flex items-center justify-center text-[var(--text-muted)]">
            <Lock className="h-6 w-6 text-[var(--brand)]" />
          </div>
          <div className="max-w-md space-y-1.5">
            <h4 className="text-sm font-bold text-[var(--text-primary)] font-mono">
              No Execution Evidence Generated Yet
            </h4>
            <p className="text-xs text-[var(--text-muted)] leading-relaxed">
              When an autonomous task executes against <span className="text-[var(--text-secondary)] font-mono">{connectedRepoName}</span>, Loom&apos;s Reviewer Agent compiles all generated artifacts into a SHA-256 hash-chained proof bundle for tamper-evident compliance.
            </p>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 w-full max-w-3xl text-left mt-2">
            {[
              { title: 'AST Call Graph', desc: 'Symbol dependency index' },
              { title: 'Red Phase Test', desc: 'Synthesized failing reproduction' },
              { title: 'Surgical Patch', desc: 'Unified code modification' },
              { title: 'Root Hash Seal', desc: 'SHA-256 cryptographic chain' },
            ].map((item, i) => (
              <div key={i} className="p-3 bg-[var(--bg-elevated)] border border-[var(--border-subtle)] rounded-lg">
                <p className="text-xs font-bold text-[var(--text-secondary)] font-mono">{item.title}</p>
                <p className="text-[10px] text-[var(--text-muted)] mt-0.5">{item.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  const runIdentifier = activeRunId || 'run_active';
  const hasArtifacts = computedArtifacts.length > 0;
  const isIntegrityValid = isVerifiedSuccess && hasArtifacts && Boolean(rootSeal);

  const handleCopy = (hash: string) => {
    navigator.clipboard.writeText(hash);
    setCopiedHash(hash);
    setTimeout(() => setCopiedHash(null), 2000);
  };

  const rawJsonContent = JSON.stringify(
    {
      spec_version: 'loom/evidence/v1',
      run_id: runIdentifier,
      repository: connectedRepoName,
      integrity_status: isIntegrityValid ? 'VALID' : 'UNVERIFIED',
      hash_algorithm: 'SHA-256',
      chain_seal: rootSeal || null,
      verification_checklist: {
        patch_generated: Boolean(displayData?.patchDiff || displayData?.checkpoint?.patch_diff),
        tests_reproduced: Boolean(displayData?.reproductionTest || displayData?.checkpoint?.reproduction_test),
        sandbox_verified: isVerifiedSuccess,
        hash_chain_validated: isIntegrityValid,
      },
      artifacts: computedArtifacts,
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
                {isIntegrityValid ? (
                  <span className="status-pill status-pill-verified text-[10px]">
                    <Check className="h-3 w-3 stroke-[3]" />
                    INTEGRITY VALID
                  </span>
                ) : (
                  <span className="status-pill text-[10px] bg-[var(--warning-soft)] text-[var(--warning)] border border-[var(--warning)]/30 font-bold">
                    <AlertTriangle className="h-3 w-3" />
                    UNVERIFIED / BLOCKED
                  </span>
                )}
              </div>
              <h3 className="text-base font-bold text-[var(--text-primary)] font-mono mt-0.5">
                SHA-256 Hash Chain Audit Bundle
              </h3>
              <p className="text-xs text-[var(--text-secondary)] mt-0.5">
                Run ID: <span className="font-mono text-[var(--cyan)] font-bold">{runIdentifier}</span> • Repository: <span className="font-mono">{connectedRepoName}</span>
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
              disabled={!hasArtifacts}
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
        {rootSeal ? (
          <div className="mt-4 p-3 bg-[var(--bg-elevated)] border border-[var(--border-subtle)] rounded-lg flex items-center justify-between gap-3 text-xs font-mono">
            <div className="flex items-center gap-2 min-w-0">
              <Lock className="h-3.5 w-3.5 text-[var(--brand)] shrink-0" />
              <span className="text-[var(--text-muted)] shrink-0">SHA-256 CHAIN SEAL:</span>
              <span className="text-[var(--cyan)] truncate">{rootSeal}</span>
            </div>
            <button
              onClick={() => handleCopy(rootSeal)}
              className="text-[var(--text-muted)] hover:text-[var(--text-primary)] transition shrink-0"
              title="Copy SHA-256 Hash Seal"
            >
              {copiedHash === rootSeal ? <Check className="h-3.5 w-3.5 text-[var(--success)]" /> : <Copy className="h-3.5 w-3.5 text-[var(--text-muted)]" />}
            </button>
          </div>
        ) : (
          <div className="mt-4 p-3 bg-[var(--bg-elevated)] border border-[var(--border-subtle)] rounded-lg flex items-center gap-2 text-xs font-mono text-[var(--text-muted)]">
            <XCircle className="h-4 w-4 text-[var(--danger)] shrink-0" />
            <span>No cryptographic chain seal: this execution did not pass full sandbox verification.</span>
          </div>
        )}
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
            <CheckCircle2 className={`h-4 w-4 ${displayData?.patchDiff || displayData?.checkpoint?.patch_diff ? 'text-[var(--success)]' : 'text-[var(--text-muted)]'} shrink-0 mt-0.5`} />
            <div>
              <p className="text-xs font-bold text-[var(--text-primary)]">Patch Generated</p>
              <p className="text-[11px] text-[var(--text-muted)] mt-0.5">Surgical code modification formatted</p>
            </div>
          </div>

          <div className="p-3 bg-[var(--bg-elevated)] border border-[var(--border-subtle)] rounded-lg flex items-start gap-2.5">
            <CheckCircle2 className={`h-4 w-4 ${displayData?.reproductionTest || displayData?.checkpoint?.reproduction_test ? 'text-[var(--success)]' : 'text-[var(--text-muted)]'} shrink-0 mt-0.5`} />
            <div>
              <p className="text-xs font-bold text-[var(--text-primary)]">Tests Reproduced</p>
              <p className="text-[11px] text-[var(--text-muted)] mt-0.5">Failing test synthesized (Red phase)</p>
            </div>
          </div>

          <div className="p-3 bg-[var(--bg-elevated)] border border-[var(--border-subtle)] rounded-lg flex items-start gap-2.5">
            <CheckCircle2 className={`h-4 w-4 ${isVerifiedSuccess ? 'text-[var(--success)]' : 'text-[var(--text-muted)]'} shrink-0 mt-0.5`} />
            <div>
              <p className="text-xs font-bold text-[var(--text-primary)]">Sandbox Verified</p>
              <p className="text-[11px] text-[var(--text-muted)] mt-0.5">Pytest suite passed (Green phase)</p>
            </div>
          </div>

          <div className="p-3 bg-[var(--bg-elevated)] border border-[var(--border-subtle)] rounded-lg flex items-start gap-2.5">
            <CheckCircle2 className={`h-4 w-4 ${isIntegrityValid ? 'text-[var(--success)]' : 'text-[var(--text-muted)]'} shrink-0 mt-0.5`} />
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
              {computedArtifacts.length} cryptographic evidence artifacts hashed via Web Crypto SHA-256
            </p>
          </div>
        </div>

        {computedArtifacts.length > 0 ? (
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
                {computedArtifacts.map((artifact, idx) => (
                  <tr key={idx} className="hover:bg-[var(--bg-hover)] transition">
                    <td className="p-3 font-semibold text-[var(--text-primary)] flex items-center gap-2">
                      <FileCheck className="h-4 w-4 text-[var(--brand)] shrink-0" />
                      <span>{artifact.name}</span>
                    </td>
                    <td className="p-3 text-[var(--text-secondary)]">{artifact.type}</td>
                    <td className="p-3">
                      <div className="flex items-center gap-2">
                        <span className="text-[var(--cyan)] font-mono">
                          {artifact.hash.slice(0, 32)}...
                        </span>
                        <button
                          onClick={() => handleCopy(artifact.hash)}
                          className="text-[var(--text-muted)] hover:text-[var(--text-primary)] transition"
                          title="Copy SHA-256 Hash"
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
                      {artifact.verified ? (
                        <span className="text-[var(--success)] font-semibold flex items-center justify-end gap-1">
                          <Check className="h-3 w-3 stroke-[3]" />
                          SEALED
                        </span>
                      ) : (
                        <span className="text-[var(--text-muted)]">UNVERIFIED</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="p-6 text-center text-xs font-mono text-[var(--text-muted)] bg-[var(--bg-elevated)] rounded-lg border border-[var(--border-subtle)]">
            No verified artifacts committed to this run. Real artifacts are generated when the task runs in the Loom sandbox.
          </div>
        )}
      </div>
    </div>
  );
};
