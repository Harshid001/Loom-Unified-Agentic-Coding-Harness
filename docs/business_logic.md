# Loom — Production Business Logic & Roadmap Specification v2.0

> **Companion to the v1.0.0 Architecture Blueprint**
> This document specifies the concrete decision rules, state machines, data contracts, pricing/entitlement logic, and governance model required to operate Loom as a commercial, enterprise-grade product — not just a technical system. Every subsystem below is written so an engineer can implement it without further interpretation, and so a business/product owner can price, gate, and support it.

---

## 0. How This Document Is Organized

| Section | Answers |
|---|---|
| 1. Business Model | Who pays, for what unit, at what price, gated how |
| 2. Core Domain Model | What data exists, who owns it, how it relates |
| 3. Subsystem Business Logic | The actual algorithms/thresholds/state machines behind each engine |
| 4. Enterprise Governance | RBAC, SSO, compliance mapping |
| 5. API & Webhook Contracts | The integration surface |
| 6. SLAs & Reliability Targets | What we promise, by tier |
| 7. Phased Roadmap | Epics, acceptance criteria, effort, dependencies, risk |
| 8. Risk Register | What could break the plan and the mitigation |
| 9. KPIs | How we know v1.0.0 succeeded |

---

## 1. Business Model & Monetization

### 1.1 Positioning

Loom does not compete on model intelligence — every competitor has access to the same frontier models. Loom competes on **empirically verified correctness**: no patch ships without a reproduction test flipping FAIL→PASS, a clean build, and a passing SAST scan. The commercial thesis is that **teams will pay for a harness that reduces false-positive PRs to near-zero**, not for another chat-based coding assistant.

Positioning axis vs. category (Devin-style autonomous agents, Copilot Workspace, Cursor/Windsurf, SWE-agent-style OSS runners):

| Axis | Loom's claim |
|---|---|
| Trust | Every merge is backed by an evidence bundle (build log, test diff, SAST result, cost trace) — auditable, not self-reported |
| Portability | Model-independent; no lock-in to a single frontier provider; runs self-hosted or cloud |
| Isolation | Only harness in category offering worktree → container → microVM tiered isolation matched to risk, not a single sandbox posture for every job |
| Enterprise readiness | SOC2-track audit logging and SSO are first-class from v1.0.0, not bolted on later |

### 1.2 Packaging & Pricing Tiers

Unit of value = a **Run** (one full DAG execution: Onboarding → Reproduction → Patch → Verify → Evidence). Pricing is run-based with seat and governance add-ons, not pure per-seat SaaS, because cost is driven by compute + model tokens, not headcount.

| Tier | Target Customer | Included | Hard Limits | Price Model |
|---|---|---|---|---|
| **Solo** | Individual developer, OSS maintainer | CLI + TUI, Tier A sandbox only, local SQLite memory, 1 model provider (BYO API key) | 50 runs/mo, 1 repo connected, no team sync | Free |
| **Team** | Startup / small eng org | + Web dashboard, Tier A+B sandbox, Postgres/Qdrant shared memory, multi-model router, GitHub/GitLab bot, Slack notifications | 500 runs/mo pooled, up to 15 seats, 20 repos | $49/seat/mo + $0.80/run over included quota |
| **Enterprise** | Regulated / large eng org | + Tier C (Firecracker) sandbox, SSO/SCIM, SOC2 audit export, dedicated VPC/self-host option, consensus verification, priority SLA | Custom (contracted run pool) | Annual contract, usage-based overage, minimum commit |
| **Self-Hosted (Air-Gapped)** | Enterprise with data-residency constraints | Full stack deployed in customer VPC, no telemetry egress by default | Custom | License fee + support contract |

### 1.3 Usage Metering & Billing Logic

**Unit of sale: Run Credit.** One Run Credit = one DAG execution up to:
- 8 agent-steps (Onboarding → Evidence Review, with up to 2 self-healing retries per step before it counts as a second consumed credit)
- 400K total tokens across all model calls in the run
- 45 minutes of sandbox wall-clock time

**Overage rules:**
- Token overage within a run: billed at provider-passthrough cost + 15% margin, itemized per run in the evidence bundle.
- Run-count overage (Team tier): metered hourly, invoiced monthly, capped by an org-configurable hard stop (default: 2x included quota) to prevent runaway spend from a misconfigured CI trigger.
- Sandbox time overage: Tier B/C minutes billed separately from Tier A, since container/VM cold-start and compute cost materially more.

**Metering pipeline (implementation contract):**
```
AgentStep completion → emit UsageEvent{run_id, org_id, tokens_in, tokens_out,
    model_id, sandbox_tier, wall_clock_ms} to append-only UsageLedger
  → hourly rollup job aggregates UsageLedger → OrgUsageSnapshot
  → OrgUsageSnapshot compared against Entitlement.quota
      → at 80% of quota: soft-warn webhook + dashboard banner
      → at 100% of quota: enforce org.hard_stop_policy
          (block | allow_with_overage_billing | require_admin_approval)
  → billing engine (Stripe metered billing) synced nightly from UsageLedger
```

**Proration & plan changes:** upgrades apply immediately with prorated credit for unused days on the prior plan; downgrades apply at the next billing cycle boundary (no mid-cycle downgrade, to avoid quota-gaming). Failed payment → 7-day grace period at current tier → auto-downgrade to Solo (not full account lock) to avoid data loss and support tickets.

### 1.4 Feature Gating (Entitlement Service)

Every tier-gated capability is enforced by a single `EntitlementService.check(org_id, feature_key)` call at the point of use — never by hiding UI alone. This prevents the common SaaS bug class of "free tier can still hit the paid API directly."

| Feature Key | Solo | Team | Enterprise |
|---|:---:|:---:|:---:|
| `sandbox.tier_b_container` | ✗ | ✓ | ✓ |
| `sandbox.tier_c_microvm` | ✗ | ✗ | ✓ |
| `memory.team_sync` | ✗ | ✓ | ✓ |
| `router.consensus_verification` | ✗ | ✗ | ✓ |
| `governance.sso_scim` | ✗ | ✗ | ✓ |
| `governance.soc2_audit_export` | ✗ | ✗ | ✓ |
| `integrations.ci_bot` | ✗ | ✓ | ✓ |
| `integrations.ide_plugins` | ✓ | ✓ | ✓ |

---

## 2. Core Domain Model

Primary entities and their ownership boundary (single-tenant fields never cross `org_id`):

| Entity | Key Fields | Notes |
|---|---|---|
| `Organization` | id, name, tier, hard_stop_policy, data_residency_region | Root tenant boundary |
| `Membership` | user_id, org_id, role | Drives RBAC (§4.1) |
| `RepoConnection` | id, org_id, provider (github/gitlab/local), install_token_ref | Token stored in secrets vault, never in DB |
| `Run` | id, org_id, repo_id, issue_text, status, sandbox_tier, started_at, cost_usd, confidence_score | Central execution record; status is the DAG state machine (§3.5) |
| `AgentStep` | id, run_id, agent_name, input_context_ref, output_ref, tokens_in/out, model_id, duration_ms, retry_count | One row per DAG node execution |
| `Patch` | id, run_id, diff_ref, files_touched, risk_flags[] | risk_flags drive consensus requirement (§3.1) |
| `VerificationResult` | id, run_id, stage (build/test/repro/lint/sast), status, evidence_ref | One row per verification stage (§3.6) |
| `MemoryNode` | id, org_id, tier (1–7), content_ref, ttl_expires_at, invalidated_by_file | See §3.3 |
| `EvidenceBundle` | id, run_id, hash_chain_prev, hash_self, immutable_url | Tamper-evident audit artifact (§3.7) |
| `UsageLedgerEntry` | id, org_id, run_id, tokens, sandbox_ms, cost_usd, billed_flag | Feeds billing (§1.3) |
| `AuditLogEntry` | id, org_id, actor_id, action, target, ip, timestamp | SOC2-scoped, append-only |

---

## 3. Subsystem Business Logic

### 3.1 Model Router & Consensus Engine

**Routing score.** For each eligible model `m` and task `t`, the router computes:

```
Score(m, t) = w1 * (1 / normalized_cost(m))
            + w2 * (1 / normalized_p95_latency(m))
            + w3 * historical_success_rate(m, task_type(t))   // rolling 30-day window
            + w4 * capability_match(m, t)                     // context window fit, language support
```
Default weights `w = [0.25, 0.15, 0.35, 0.25]`, tunable per org (e.g., a latency-sensitive CI customer raises `w2`). The router selects the highest-scoring model that has remaining quota headroom for the org.

**Fallback cascade.** Triggered when any of: request timeout > 90s, provider error rate > 10% in a trailing 5-minute window, or context overflow. Cascade order is primary → secondary (next-highest score) → tertiary (cheapest capable model, "degrade gracefully" mode) → hard fail with human escalation after 3 cascade exhaustions.

**Consensus verification (Enterprise).** A patch is flagged `high_risk` — and therefore requires 2-of-3 independent model agreement on patch *intent* (not byte-identical diffs) before the Patcher Agent applies it — when **any** of:
- touched files match a configurable sensitive-path glob (default: `**/auth/**`, `**/billing/**`, `**/migrations/**`)
- diff size > 150 changed lines
- the Verifier's confidence score (§3.6) on a prior attempt was < 0.6
- the org has `router.consensus_verification` entitlement enabled and set to "always-on"

### 3.2 Polyglot Repository Intelligence — Context Budget Algorithm

Relevance score per AST symbol:
```
Relevance(s) = a1 * TF_IDF(s.text, issue_text)
             + a2 * graph_proximity(s, touched_files)   // inverse BFS depth in call/def graph
             + a3 * recency_weight(s.last_modified)
             + a4 * historical_bug_density(s.file)       // from Tier 3 memory
```
Context budget split per run (relative to the target model's context window `C`): 15% system/instructions, 55% ranked symbols (greedy-fill by `Relevance(s)` descending until budget exhausted), 20% memory tiers 2–3 (conventions + issue history), 10% headroom reserved for model output. Symbols are truncated at signature+docstring level before full-body inclusion when budget is tight — never silently dropped without a `context_truncated` flag on the `AgentStep` record, since silent truncation is the leading cause of hallucinated fixes.

### 3.3 7-Tier Memory — Retention & Invalidation

| Tier | TTL | Invalidation Trigger | Backend | Tenant Isolation |
|---|---|---|---|---|
| 1. Workspace/Repo metadata | 24h | repo push webhook | Postgres | row-level `org_id` |
| 2. Conventions | 7d | lint config or `.editorconfig` change | Postgres | row-level `org_id` |
| 3. Issue/bug history | indefinite | manual purge only | Postgres + pgvector | row-level `org_id` |
| 4. AST/symbol cache | invalidated on file diff, else 12h | file content hash mismatch | Redis + Postgres | row-level `org_id` |
| 5. Execution traces | 90d | none (rolls off) | Postgres (partitioned by month) | row-level `org_id` |
| 6. Invalidation engine itself | n/a — this *is* the invalidation logic | file-change webhook fan-out | event bus | n/a |
| 7. Cloud/team sync | n/a | conflict resolution below | Postgres primary, Redis cache | row-level `org_id`, plus per-repo ACL within org |

**Team-sync conflict resolution:** last-write-wins at the field level, **except** Tier 3 (issue history) and Tier 5 (execution traces), which are append-only and never overwritten — two developers' learnings both persist rather than one clobbering the other.

### 3.4 Sandbox Tier Selection — Decision Tree

```
IF repo.has_untrusted_native_deps == false AND run.classification == "quick_fix":
    → Tier A (Git Worktree)
ELSE IF org.tier IN {Team, Enterprise} AND run requires dependency install/build:
    → Tier B (Docker/Podman), network egress = deny-all except configured package registries
ELSE IF org.tier == Enterprise AND (repo.sensitivity_flag == true OR patch.risk_flags contains "high_risk"):
    → Tier C (Firecracker microVM), network egress = deny-all, no external network unless explicitly allowlisted per-run
ELSE:
    → default to Tier B if available in org entitlement, else Tier A with a dashboard warning
```
**Resource quotas:** Tier B containers capped at 2 vCPU / 4GB RAM / 45 min per run by default (Enterprise-configurable). **Auto-scale trigger:** sandbox pool scales when queue wait time p95 > 20s over a 2-minute window. **Egress policy:** default-deny with an explicit allowlist per org (package registries, the repo's own git remote); any egress attempt outside the allowlist is logged as a `AuditLogEntry` and the run is failed, not silently permitted.

### 3.5 Dynamic DAG Orchestration — State Machine

States: `QUEUED → ONBOARDING → REPRODUCING → PLANNING → PATCHING → VERIFYING → EVIDENCE_REVIEW → {MERGED | FAILED | ROLLED_BACK}`, with side-states `CONFLICT_RESOLUTION` and `SECURITY_HOLD` reachable from `PATCHING`/`VERIFYING`.

| Transition | Guard Condition |
|---|---|
| `ONBOARDING → REPRODUCING` | AST map built AND reproduction test synthesized |
| `REPRODUCING → PLANNING` | Reproduction test confirmed to FAIL on unpatched base |
| `PATCHING → CONFLICT_RESOLUTION` | Multi-file patch produces a merge conflict against latest base |
| `PATCHING → SECURITY_HOLD` | SAST pre-check on the diff (fast pass) finds a Critical finding |
| `VERIFYING → EVIDENCE_REVIEW` | All verification stages (§3.6) return non-blocking status |
| `EVIDENCE_REVIEW → MERGED` | confidence_score ≥ org.auto_merge_threshold AND no open Reviewer hold |
| `* → ROLLED_BACK` | Manual trigger, or auto-rollback rule (§3.6) fires post-merge |

**Retry/backoff policy:** each step retries up to 2 times with exponential backoff + jitter (base 5s, factor 2, max 60s) before escalating the run to `FAILED` with a human-review flag. A step that fails identically twice (hash of error signature matches) escalates immediately on the second failure rather than burning the third retry — repeat-identical-failure is a strong signal that retrying won't help.

### 3.6 Verification-First Engine — Decision Matrix

| Build | Tests | Repro flips F→P | SAST | Action |
|---|---|---|---|---|
| ✓ | ✓ | ✓ | clean | Auto-merge if `confidence_score ≥ threshold`, else route to human review |
| ✓ | ✓ | ✗ | clean | Reject — fix didn't address root cause even though nothing broke; back to Planning |
| ✓ | ✗ (regression) | — | — | Reject, auto-rollback patch, escalate to Patcher with regression context |
| ✗ | — | — | — | Reject, no evidence bundle merge candidate; escalate to Planning with build log |
| ✓ | ✓ | ✓ | High/Critical finding | Hard block regardless of confidence — routes to `SECURITY_HOLD`, never auto-merges |

**Confidence score:** `0.4 * repro_test_strength + 0.3 * diff_minimality + 0.2 * historical_pattern_match + 0.1 * model_self_reported_certainty` (self-reported certainty is intentionally weighted lowest — it is the least reliable signal per the "no self-reporting" design principle). Default `auto_merge_threshold = 0.95`, org-configurable down to 0.85 minimum (cannot be disabled entirely — this is a product guardrail, not just a default).

**Post-merge auto-rollback rule:** if a newly merged patch's monitored CI pipeline (when connected via the GitHub/GitLab bot) fails within 1 hour of merge, Loom automatically opens a revert PR and notifies the Reviewer role — it does not force-push a revert without a PR, to preserve human review of the rollback itself.

### 3.7 Evidence Bundling & Audit Trail

Every `EvidenceBundle` is hash-chained (`hash_self = SHA256(hash_prev + bundle_content)`) so tampering with historical evidence is detectable. Required contents for SOC2-track readiness: build log, full diff, every `VerificationResult`, model+version used per step, token/cost breakdown, and the actor (agent or human) responsible for the final merge decision. Evidence bundles are retained for the org's configured audit window (default 1 year, Enterprise-configurable up to 7 years) and are exportable but never mutable in place.

### 3.8 Telemetry & Quota Enforcement

Cost accumulates in real time against the `Run.cost_usd` field as each `AgentStep` completes. Enforcement mirrors §1.3: soft-warn at 80% of org quota (webhook + dashboard), hard-stop at 100% unless `hard_stop_policy = allow_with_overage_billing`. Enterprise orgs may configure a **burst grace**: up to 20% over quota permitted for a maximum of 48 hours before hard enforcement, to avoid interrupting an in-flight incident-response run.

---

## 4. Enterprise Governance

### 4.1 RBAC Matrix

| Action | Owner | Admin | Developer | Reviewer | Billing Admin | Auditor (read-only) |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| Trigger a run | ✓ | ✓ | ✓ | ✗ | ✗ | ✗ |
| Approve auto-merge override | ✓ | ✓ | ✗ | ✓ | ✗ | ✗ |
| Modify entitlements/quota policy | ✓ | ✓ | ✗ | ✗ | ✓ (billing fields only) | ✗ |
| Configure sandbox tier defaults | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ |
| Export evidence bundles / audit log | ✓ | ✓ | ✗ | ✗ | ✗ | ✓ |
| Manage SSO/SCIM config | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ |
| Invite/remove members | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ |

### 4.2 SSO / SCIM Requirements

SAML 2.0 and OIDC supported at Enterprise tier; SCIM 2.0 for automated provisioning/deprovisioning (deprovisioning must revoke all active `Run` triggers and API tokens for that user within 5 minutes — this is a hard SLA, not best-effort, since delayed offboarding is a common audit finding).

### 4.3 Compliance Control Mapping (illustrative, SOC2 Trust Services Criteria)

| Trust Criterion | Loom Control |
|---|---|
| Security — Access Control (CC6.1) | RBAC matrix (§4.1) + SSO/SCIM (§4.2) |
| Security — Change Management (CC8.1) | Every patch is an `EvidenceBundle`-backed, hash-chained record (§3.7) |
| Availability (A1.2) | SLA targets (§6) + auto-scale triggers (§3.4) |
| Confidentiality (C1.1) | Per-org row-level isolation (§3.3) + Tier C air-gapped sandbox option |
| Processing Integrity (PI1.1) | Verification-first decision matrix (§3.6) — no unverified merge path exists |

---

## 5. API & Webhook Contract Highlights

Representative REST/gRPC surface (full OpenAPI spec to be generated from the same source of truth as the domain model in §2, not maintained by hand):

```
POST   /v1/runs                     { repo_id, issue_text, sandbox_tier?, priority? } → Run
GET    /v1/runs/{id}                → Run (with nested AgentStep summary)
GET    /v1/runs/{id}/evidence       → EvidenceBundle
POST   /v1/runs/{id}/rollback       → triggers ROLLED_BACK transition
GET    /v1/orgs/{id}/usage          → OrgUsageSnapshot
POST   /v1/entitlements/check       { org_id, feature_key } → { allowed: bool, reason? }
```

Webhook events (for the CI bot / Slack integration): `run.queued`, `run.completed`, `run.failed`, `run.security_hold`, `usage.quota_warning`, `usage.quota_exceeded`, `evidence.exported`.

---

## 6. SLA & Reliability Targets

| Tier | Uptime | Run p50 latency | Run p95 latency | Support MTTR (Sev1) |
|---|---|---|---|---|
| Solo | Best-effort | — | — | Community |
| Team | 99.5% | ≤ 4 min | ≤ 12 min | Next business day |
| Enterprise | 99.9% (99.95% for self-hosted control plane) | ≤ 3 min | ≤ 8 min | 1 hour |

---

## 7. Phased Roadmap (Expanded, Execution-Ready)

### Phase 0 — Business-Logic Foundation *(new — precedes Phase 1, ~2 weeks, blocks monetization)*
| Epic | Deliverable | Acceptance Criteria | Effort | Risk |
|---|---|---|---|---|
| Entitlement Service | `EntitlementService.check()` live, backed by §1.4 table | Free-tier org calling a gated endpoint returns `403` with reason, not silent success | 1 eng-wk | Low |
| Usage Ledger + Metering | Append-only `UsageLedgerEntry` pipeline | Every `AgentStep` produces exactly one ledger row; hourly rollup job idempotent on replay | 1.5 eng-wk | Medium (idempotency bugs are the classic failure mode) |
| RBAC scaffolding | Role table + middleware enforcing §4.1 | Attempting an Admin-only action as Developer returns `403` in integration test suite | 1 eng-wk | Low |

### Phase 1 — Engine Hardening (2026-08-12, 24d)
| Epic | Deliverable | Acceptance Criteria | Effort | Dependencies | Risk |
|---|---|---|---|---|---|
| Polyglot Tree-Sitter Integration | Parsers for TS/JS, Py, Go, Rust, Java, C++ | Symbol extraction accuracy ≥ 95% against a 200-repo golden test set per language | 3 eng-wk | none | Medium (grammar edge cases per language) |
| Advanced AST Context Budgeter | §3.2 algorithm implemented with `context_truncated` flagging | Zero silent truncations across regression suite; budget overflow always flagged on `AgentStep` | 2 eng-wk | Tree-sitter integration | Low |

### Phase 2 — Memory & Cloud (2026-09-01, 24d)
| Epic | Deliverable | Acceptance Criteria | Effort | Dependencies | Risk |
|---|---|---|---|---|---|
| Postgres/Qdrant Vector Sync | Tier 3–7 migrated off local SQLite for Team+ orgs | Zero data loss on migration (verified via row-count + checksum parity); Solo tier unaffected | 3 eng-wk | Phase 0 (org isolation model) | Medium |
| Team Shared Memory Hub | Conflict resolution per §3.3 | Two concurrent writers to the same Tier 4 node never silently overwrite Tier 3/5 append-only data in chaos test | 2 eng-wk | Vector sync | Medium |

### Phase 3 — Sandboxing & IDE (2026-09-20, 28d)
| Epic | Deliverable | Acceptance Criteria | Effort | Dependencies | Risk |
|---|---|---|---|---|---|
| Docker/Firecracker Enclaves | §3.4 decision tree + resource quotas + egress allowlist | Egress attempt outside allowlist is blocked and logged in 100% of red-team test attempts | 3 eng-wk | Phase 0 (entitlement gating of Tier C) | High (isolation bugs are security-critical) |
| VS Code & JetBrains Extensions | Inline run trigger + live diff preview | Extension can trigger a run and render `EvidenceBundle` summary without leaving the IDE | 3 eng-wk | API contracts (§5) stable | Medium |

### Phase 4 — Enterprise & CI/CD (2026-10-15, 28d)
| Epic | Deliverable | Acceptance Criteria | Effort | Dependencies | Risk |
|---|---|---|---|---|---|
| GitHub/GitLab Bot + Slack | Auto-triage, verification branch, evidence-backed PR | Bot-created PR includes full evidence bundle link; false-trigger rate < 1% over pilot period | 2.5 eng-wk | Verification engine (§3.6) stable | Medium |
| Enterprise SSO & SOC2 | SAML/OIDC/SCIM + audit export (§4.2–4.3) | Deprovisioned SCIM user loses all active tokens within 5-minute SLA in test harness | 3.5 eng-wk | RBAC scaffolding (Phase 0) | High (compliance-gating for enterprise deals) |

### Phase 5 — General Availability *(new, 2 weeks post-Phase 4)*
| Epic | Deliverable | Acceptance Criteria |
|---|---|---|
| Billing cutover | Stripe metered billing live against real `UsageLedger` | First month's invoice reconciles to ledger within 0.5% variance |
| SLA monitoring | Public status page + internal alerting on §6 targets | Alert fires before any SLA breach crosses the promised threshold, not after |

---

## 8. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Model provider rate limits throttle router under load | Medium | High | Fallback cascade (§3.1) + per-org token budget smoothing |
| Firecracker isolation bug allows sandbox escape | Low | Critical | Red-team egress testing gate (Phase 3 acceptance criteria), deny-all default |
| Usage ledger double-counts on retry, over-billing customers | Medium | High | Idempotency key = `(run_id, step_id, attempt_number)` on every ledger write |
| Auto-merge threshold too aggressive, ships a bad patch | Medium | High | Guardrail floor of 0.85 confidence, non-disableable; post-merge auto-rollback (§3.6) |
| SOC2 audit gap blocks a signed enterprise deal | Medium | High | Compliance control mapping (§4.3) tracked against Phase 4 acceptance criteria explicitly, not left implicit |
| Team memory sync conflicts cause silent data loss | Low | High | Append-only policy for Tier 3/5 (§3.3), chaos-tested before Phase 2 exit |

---

## 9. Success Metrics (v1.0.0 Launch)

**Product:** reproduction-test flip rate ≥ 90% of attempted runs; auto-merge false-positive rate (merged patch later reverted) < 2%; median time-to-verified-PR ≤ 10 minutes.

**Business:** Team-tier logo count vs. pilot target; Enterprise pipeline conversion rate on SOC2/SSO-gated deals; run-credit gross margin ≥ 70% after model-cost passthrough; quota-driven upgrade rate (Solo→Team) as a leading indicator of packaging fit.

---

## Appendix: Glossary

- **Run** — one full DAG execution against a single issue on a single repo.
- **Evidence Bundle** — the immutable, hash-chained record proving a patch was verified, not asserted.
- **Consensus Verification** — 2-of-3 model agreement requirement for high-risk patches (Enterprise).
- **Entitlement** — a tier-gated feature flag enforced server-side at point of use, never UI-only.
- **Hard Stop** — the enforced action when an org exceeds its usage quota, configurable per org.