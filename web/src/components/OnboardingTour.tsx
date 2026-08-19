"use client";

import React, { useState, useEffect } from 'react';
import {
  Layers,
  GitBranch,
  ShieldCheck,
  Play,
  ArrowRight,
  CheckCircle2,
  Lock,
  TestTube2,
  FileCode,
  X,
} from 'lucide-react';

const STORAGE_KEY = 'loom_onboarding_complete';

interface OnboardingTourProps {
  onComplete?: () => void;
}

interface Step {
  title: string;
  description: string;
  icon: React.ElementType;
  color: string;
  detail?: React.ReactNode;
}

const STEPS: Step[] = [
  {
    title: 'Welcome to Loom',
    description: 'Loom is a verification-first autonomous coding engine. It diagnoses bugs, synthesizes patches, and proves correctness — all with cryptographic evidence.',
    icon: Layers,
    color: 'var(--brand)',
    detail: (
      <div className="flex items-center justify-center gap-1 mt-4">
        {['#7C5CFF', '#35D5FF', '#35D399', '#F5B83D', '#FF5F6D'].map((c, i) => (
          <div key={i} className="h-2 w-8 rounded-full" style={{ backgroundColor: c, opacity: 0.7 }} />
        ))}
      </div>
    ),
  },
  {
    title: 'The 5-Stage Pipeline',
    description: 'Every execution runs through 5 sequential agents: Mapper (AST indexing), Reproducer (failing test synthesis), Patcher (surgical code modification), Verifier (sandbox testing), and Reviewer (proof construction).',
    icon: GitBranch,
    color: 'var(--cyan)',
    detail: (
      <div className="flex items-center justify-center gap-2 mt-4 font-mono text-[10px]">
        {[
          { label: 'MAP', color: '#7C5CFF' },
          { label: 'REPRO', color: '#35D5FF' },
          { label: 'PATCH', color: '#9175FF' },
          { label: 'VERIFY', color: '#35D399' },
          { label: 'REVIEW', color: '#F5B83D' },
        ].map((s, i, arr) => (
          <React.Fragment key={s.label}>
            <span className="px-2 py-1 rounded border border-[var(--border-subtle)] font-bold" style={{ color: s.color, borderColor: `${s.color}40` }}>
              {s.label}
            </span>
            {i < arr.length - 1 && <ArrowRight className="h-3 w-3 text-[var(--border-default)]" />}
          </React.Fragment>
        ))}
      </div>
    ),
  },
  {
    title: 'Evidence & Proof Bundles',
    description: 'Every completed run produces a SHA-256 hash-chained evidence bundle. Each artifact (patch, test, telemetry) is hashed and linked into a tamper-evident chain — verified directly in your browser via Web Crypto API.',
    icon: ShieldCheck,
    color: 'var(--success)',
    detail: (
      <div className="flex items-center justify-center gap-3 mt-4">
        {['Resolution Brief', 'Reproduction Test', 'Surgical Patch', 'Root Seal'].map((name, i) => (
          <div key={i} className="flex items-center gap-1.5 text-[10px] font-mono text-[var(--text-muted)]">
            <Lock className="h-3 w-3 text-[var(--success)]" />
            <span>{name}</span>
          </div>
        ))}
      </div>
    ),
  },
  {
    title: 'Launch Your First Run',
    description: 'Click "Launch Run" to start the pipeline. Paste a bug description or select a GitHub issue, and Loom will autonomously reproduce, patch, verify, and prove the fix. You can watch the execution in real-time via the Live Box.',
    icon: Play,
    color: 'var(--brand)',
    detail: (
      <div className="flex items-center justify-center gap-4 mt-4 text-[10px] font-mono text-[var(--text-muted)]">
        <div className="flex items-center gap-1.5">
          <TestTube2 className="h-3 w-3 text-[var(--cyan)]" />
          <span>Red → Green testing</span>
        </div>
        <div className="flex items-center gap-1.5">
          <FileCode className="h-3 w-3 text-[var(--brand)]" />
          <span>Surgical patches</span>
        </div>
        <div className="flex items-center gap-1.5">
          <ShieldCheck className="h-3 w-3 text-[var(--success)]" />
          <span>SHA-256 proof</span>
        </div>
      </div>
    ),
  },
  {
    title: "You're All Set",
    description: "You now understand the core of Loom's verification-first architecture. Explore the dashboard tabs — Overview, DAG, Evidence, Analytics — and launch your first autonomous pipeline run.",
    icon: CheckCircle2,
    color: 'var(--success)',
  },
];

export const OnboardingTour: React.FC<OnboardingTourProps> = ({ onComplete }) => {
  const [currentStep, setCurrentStep] = useState(0);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (typeof window !== 'undefined') {
      const completed = localStorage.getItem(STORAGE_KEY);
      if (!completed) {
        setVisible(true);
      }
    }
  }, []);

  const handleNext = () => {
    if (currentStep < STEPS.length - 1) {
      setCurrentStep(prev => prev + 1);
    } else {
      handleComplete();
    }
  };

  const handleComplete = () => {
    if (typeof window !== 'undefined') {
      localStorage.setItem(STORAGE_KEY, 'true');
    }
    setVisible(false);
    onComplete?.();
  };

  if (!visible) return null;

  const step = STEPS[currentStep];
  const Icon = step.icon;
  const isLast = currentStep === STEPS.length - 1;

  return (
    <>
      <div className="onboarding-overlay" onClick={handleComplete} />
      <div className="onboarding-card" onClick={e => e.stopPropagation()}>
        {/* Close button */}
        <button
          onClick={handleComplete}
          className="absolute top-4 right-4 text-[var(--text-muted)] hover:text-[var(--text-primary)] transition"
          aria-label="Skip onboarding tour"
        >
          <X className="h-4 w-4" />
        </button>

        {/* Icon */}
        <div className="flex justify-center mb-5">
          <div
            className="h-14 w-14 rounded-2xl flex items-center justify-center shadow-lg"
            style={{
              backgroundColor: `${step.color}15`,
              color: step.color,
              boxShadow: `0 0 24px ${step.color}25`,
            }}
          >
            <Icon className="h-7 w-7" />
          </div>
        </div>

        {/* Content */}
        <div className="text-center space-y-2">
          <h3 className="text-lg font-bold text-[var(--text-primary)] font-mono">
            {step.title}
          </h3>
          <p className="text-sm text-[var(--text-secondary)] leading-relaxed max-w-md mx-auto">
            {step.description}
          </p>
          {step.detail}
        </div>

        {/* Progress & Navigation */}
        <div className="mt-8 flex items-center justify-between">
          <div className="flex items-center gap-2">
            {STEPS.map((_, i) => (
              <div
                key={i}
                className={`onboarding-progress-dot ${i === currentStep ? 'active' : ''} ${i < currentStep ? '!bg-[var(--success)]' : ''}`}
              />
            ))}
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={handleComplete}
              className="text-xs font-mono text-[var(--text-muted)] hover:text-[var(--text-primary)] transition px-3 py-1.5"
            >
              Skip Tour
            </button>
            <button
              onClick={handleNext}
              className="btn-primary h-9 px-5 text-xs gap-1.5"
            >
              {isLast ? (
                <>
                  <CheckCircle2 className="h-3.5 w-3.5 relative z-10" />
                  <span className="relative z-10">Get Started</span>
                </>
              ) : (
                <>
                  <span className="relative z-10">Next</span>
                  <ArrowRight className="h-3.5 w-3.5 relative z-10" />
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </>
  );
};
