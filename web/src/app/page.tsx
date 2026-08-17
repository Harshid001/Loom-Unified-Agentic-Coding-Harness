                  <p className="text-xs text-[var(--text-muted)] mt-0.5">
                    Red-phase synthesis and green-phase verification test traces
                  </p>
                </div>
                {displayData && (
                  <span className={`status-pill ${displayData.status === 'VERIFIED SUCCESS' ? 'status-pill-verified' : 'status-pill-running'} text-[10px]`}>
                    {displayData.status === 'VERIFIED SUCCESS' ? 'VERIFIED PASSED' : 'EXECUTING'}
                  </span>
                )}
              </div>

              {displayData?.reproductionTest ? (
                <div className="bg-[var(--bg-root)] border border-[var(--border-subtle)] rounded-xl p-4 font-mono text-xs text-[var(--text-secondary)] overflow-x-auto space-y-2">
                  <p className="text-[var(--brand)] font-bold">{"// Synthesized Reproduction Test for Run "}{displayData.id}:</p>
                  <pre className="whitespace-pre-wrap text-[var(--text-primary)]">{displayData.reproductionTest}</pre>
                </div>
              ) : (
                <div className="py-12 text-center text-xs text-[var(--text-muted)] flex flex-col items-center gap-3">
                  <p>No test suite execution recorded yet for {connectedRepo?.fullName || 'this repository'}.</p>
                  <button
                    onClick={() => setIsNewRunModalOpen(true)}
                    className="btn-primary h-8 px-3 text-xs gap-1.5"
                  >
                    <Play className="h-3 w-3 fill-current" />
                    <span>Launch Run to Synthesize Tests</span>
                  </button>