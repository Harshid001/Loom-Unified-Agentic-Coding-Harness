# Loom v2.0 Spec — Gap Analysis vs. Current Codebase (status: post-fourth-pass)

> Generated 2026-08-12 against spec v2.0 sections 1–9. Updated after Phase 0 completion
> (Entitlement enforcement, Usage Ledger wiring, RBAC in API, rollup job, audit log, planner node,
> confidence-scored verification), the second pass (repo model / lifecycle webhooks / SECURITY_HOLD /
> evidence export), the third pass (actor attribution, CONFLICT_RESOLUTION, post-merge
> auto-rollback, memory tenant scoping), and the fourth pass (§2 relational run records,
> §3.3 append-only tiers).

## Summary

All **Critical** gap items from the original analysis are closed. All **High** items are closed.
Second pass closed the remaining implementable Medium/domain gaps: `RepoConnection` model, run-lifecycle
webhook dispatch, `SECURITY_HOLD` state wiring, and evidence-bundle export at run completion.
Third pass closed the last logic-only gaps: §3.7 actor attribution, §3.5 `CONFLICT_RESOLUTION`
routing, §3.6 post-merge auto-rollback (rule + monitor + API), and §2 memory tenant scoping.
Fourth pass added the §2 relational records layer (Run/AgentStep/Patch/VerificationResult rows)
and §3.3 append-only enforcement for memory tiers 3/5.
Remaining work is Phase 2+ roadmap material (postgres/Qdrant vector sync + team conflict
resolution, Docker/Firecracker enclaves, SSO/SCIM, CI bot, billing cutover).

---

## Closed Items (original gap list)

### Critical

| # | Item | Status | Where |
|---|---|---|---|
| 1 | Wire `UsageEvent` emission into `TaskGraph._execute_node_with_retry()` | ✅ | `task_graph.py` — emits success + failure events per attempt; dedup key `run_id|step_id|attempt_number|input_context_hash` |
| 2 | Wire RBAC into API | ✅ | `server.py` — `require_run_permission` on run creation, `require_admin_permission` on entitlements/check, `require_auditor_permission` on org usage; 403 on denial |
| 3 | Entitlement enforcement at run creation | ✅ | `server.py create_run` — `sandbox_tier` in `RunRequest`; requested B/C on a non-entitled org → 403 with reason; invalid tier → 400 |
| 4 | Sandbox-ms dimension in `evaluate_quota()` | ✅ | `entitlements.py` — `quota_usage_percent()` + messages report runs/tokens/sandbox |

### High

| # | Item | Status | Where |
|---|---|---|---|
| 5 | PLANNING node in TaskGraph | ✅ | `PlannerAgent` added; `NODE_SEQUENCE` = onboarding → reproduction → planner → patcher → verifier → reviewer; `STATUS_NODE_MAP` maps planner → `PLANNING`; patcher prompt consumes the plan |
| 6 | Egress violation → AuditLogEntry | ✅ | `AuditLogger` (`business/audit_log.py`, append-only JSONL, reloads on init); `EgressEnforcer(audit_logger=...)` records `sandbox.egress_blocked` |
| 7 | Hourly rollup job skeleton | ✅ | `business/rollup.py` `UsageRollupJob` — aggregates ledger → snapshot per org, evaluates quota, emits `usage.quota_warning` / `usage.quota_exceeded` webhooks + audit entries; threshold-crossing state machine → idempotent on replay |
| 8 | Confidence score (§3.6) | ✅ | `VerifierAgent` delegates to `VerificationRunner.full_verification_pipeline()` (weights match spec exactly); `confidence_score` / `verification_decision` / `sast_findings` stored in shared_data; `TaskGraph` computes `merge_decision` vs `auto_merge_threshold` |
| — | `auto_merge_threshold` floor (0.85) | ✅ | `Organization.auto_merge_threshold` `Field(ge=0.85, le=1.0)` in `models.py` |
| — | Webhook event names per spec §5 | ✅ | `run.queued`, `run.security_hold`, `usage.quota_warning`, `usage.quota_exceeded`, `evidence.exported` added to `WebhookEventType` (legacy names kept for compat) |

### Medium

| # | Item | Status | Where |
|---|---|---|---|
| 9 | EvidenceBundle model + hash chaining | ✅ (pre-existing) | `verification/bundle.py` — hash-chained, HMAC-signable, tamper verify |
| 12 | `auto_merge_threshold` floor | ✅ | covered above |

---

## Remaining Gaps (by spec section)

| Spec Item | Status | Notes |
|---|---|---|
| §2 `MemoryNode` entity fields (org_id, ttl_expires_at, invalidated_by_file) | ✅ | `MemoryItem.org_id` tenant column (sqlite migration v3 + postgres), `ttl_expires_at` property from TTL invalidation rule; store/retriever org-scoped filters |
| §2 `Run`/`AgentStep`/`Patch`/`VerificationResult` records | ✅ | `RunRecordStore` (`loom/db/records_store.py`) — relational rows (SQLite + Postgres via `DATABASE_URL`); `TaskGraph` writes one `AgentStep` row per DAG node (upserted across retries), `Patch` row + 5 `VerificationResult` stage rows (build/test/repro/sast/lint); `GET /runs/{id}/records` returns run + nested rows |
| §1.3 Stripe metered billing sync | ✅ | `StripeBillingAdapter` (`loom/business/billing_provider.py`), HMAC signature verification (`verify_stripe_signature`), `POST /api/v1/billing/stripe/webhook`, metered usage reporting, `UsageRollupJob` integration (`tests/test_billing_stripe.py`) |
| §1.3 Proration / plan changes / payment grace | ✅ | `prorated_credit_for_plan_change`, `tier_after_payment_grace`, `settle_pending_plan_change`, `build_invoice` itemization, checkout/portal sessions (`/api/v1/billing/checkout-session`, `/api/v1/billing/portal-session`) |
| §3.3 Postgres/Qdrant vector store + Tier 3/5 append-only | ⚠️ Partial | Append-only invariant enforced for EPISODIC (3) + VERIFIED_EVIDENCE (5) — same-id writes get a fresh id instead of overwriting; postgres/SQLite backends exist; vector indexing + team-sync conflict resolution remain (Phase 2) |
| §3.4 Docker/Firecracker enclaves, egress deny in real isolation | ⚠️ Partial | Decision tree + egress allowlist implemented; actual containers/VMs not provisioned (Phase 3) |
| §3.5 CONFLICT_RESOLUTION transition | ✅ | Patcher records `apply_status`/`conflict_detected` (git apply → patch fallback); conflict → `run_status = CONFLICT_RESOLUTION`, merge decision forced to human review; resolution loop via `TaskGraph.run(resume_from="patcher")` |
| §3.6 Post-merge auto-rollback rule | ✅ | `post_merge.py` — single pure rule `auto_rollback_triggered()` (runner delegates), `generate_revert_patch()` (reverses unified diffs), `PostMergeMonitor` (audit entry + revert log + `run.rolled_back` webhook); `POST /api/v1/runs/{id}/ci-report` wires it end-to-end (checkpoint status → `rolled_back`) |
| §3.7 Evidence bundle actor attribution (human vs agent) | ✅ | `compute_merge_decision()` returns `actor` (`agent`/`human`/`none`); `EvidenceBundle.merge_decision` included in the tamper-evident payload hash and exported at run completion |
| §4.2 SSO/SCIM + 5-min deprovisioning SLA | ✅ | `loom/scim/provisioning.py` SCIM 2.0 provisioning / deprovisioning with token revocation within 5-min SLA (`tests/test_scim_provisioning.py`) |
| §6 SLA monitoring / status page | ✅ | `SystemStatusMonitor` (`loom/telemetry/status.py`) with component probes & 30-day uptime/latency SLA metric computation; `GET /api/v1/system/status` and `GET /status` endpoints (`tests/test_system_status.py`) |

---

## Closed in Second Pass (2026-08-12)

| Item | Status | Where |
|---|---|---|
| §2 `RepoConnection` (provider, install_token_ref) | ✅ | `models.py` — `RepoProvider` enum + `RepoConnection.create()` enforcing `vault:`-prefixed token refs only (raw tokens rejected); `tests/test_domain_models.py` |
| §5 Run-lifecycle webhooks from orchestrator | ✅ | `TaskGraph` dispatches `run.queued`, `run.completed`, `run.failed`, `run.rolled_back`, `run.security_hold`, `evidence.ready` (fire-and-forget, gathered before `run()` returns); `WebhookEngine` singleton `get_webhook_engine()`/`reset_webhook_engine()`; server wires engine into every run |
| §3.5 `SECURITY_HOLD` transition | ✅ | `compute_merge_decision()` — SAST `security_hold` decision → `auto_merge=False` always + `run_status = SECURITY_HOLD`; verified via verifier monkeypatch integration test |
| §3.7 Evidence export at run completion | ✅ | `TaskGraph._export_evidence_bundle()` assembles patch/verification/cost/traces/snapshot/merge-decision and exports via `EvidenceBundler`; `evidence_ready` webhook fired; `GET /runs/{id}/evidence` now returns the real hash-chained bundle with `chain_integrity` verification; response includes `evidence.{exported,chain_hash}`; `LOOM_EVIDENCE_DIR` env override for isolated output |

---

## Closed in Third Pass (2026-08-12)

| Item | Status | Where |
|---|---|---|
| §3.7 Merge-decision actor attribution | ✅ | `compute_merge_decision()` returns `actor` — `"agent"` (auto-merge), `"human"` (review required, incl. security holds and conflicts), `"none"` (blocked/failed); `EvidenceBundle.merge_decision` added and included in `_payload_hash` so attribution is tamper-evident; verified by bundle-content and decision-unit tests |
| §3.5 CONFLICT_RESOLUTION routing | ✅ | `PatcherAgent` now distinguishes `applied` / `applied_via_fallback` / `conflict` / `error` via exit codes of `git apply` then `patch -p1`; conflict → `run_status = CONFLICT_RESOLUTION` and `compute_merge_decision(conflict_detected=True)` forces `auto_merge=False`, `needs_human_review=True`; webhook `run.failed` payload carries `reason: merge_conflict`; humans resolve by re-running `TaskGraph.run(resume_from="patcher")` |
| §3.6 Post-merge auto-rollback | ✅ | `loom/business/post_merge.py` — `auto_rollback_triggered()` (single source of truth; `VerificationRunner.should_auto_rollback` now delegates), `generate_revert_patch()` (swaps file headers, inverts hunk ranges/markers; double-revert is identity; new-file additions revert to deletions), `PostMergeMonitor.evaluate()` + `record_rollback()` (audit `run.rolled_back`, revert record JSONL, `run.rolled_back` webhook); `POST /api/v1/runs/{run_id}/ci-report` (and `/api/runs/...`) applies it to persisted checkpoints — sets `run_status=rolled_back`, marks `merge_decision.auto_rolled_back`, fires webhook, returns revert patch |
| §2 Memory tenant scoping | ✅ | `MemoryItem.org_id` (default `"default"`) + `ttl_expires_at` property; sqlite `_migration_v3` adds `org_id` column + index (postgres schema updated, schema version 3); `add` persists org_id; `search`/`get_by_tier`/`clear_tier` accept optional `org_id` filter (explicit column lists keep row layout consistent across dialects); `MemoryRetriever.retrieve(org_id=...)` passthrough |

---

## Closed in Fourth Pass (2026-08-12)

| Item | Status | Where |
|---|---|---|
| §2 Relational run records | ✅ | `loom/business/models.py` — `RunRecord`, `AgentStepRecord`, `PatchRecord`, `VerificationResultRecord` (spec field lists); `loom/db/records_store.py` — `RunRecordStore` (SQLite + Postgres via `DATABASE_URL`, schema migration v1, `get_run_record_store()`/`reset_run_record_store()` singletons, `verification_stage_records()` mapping); `TaskGraph` takes `records_store` — upserts one `AgentStep` row per DAG node across retry attempts, records `Patch` row (diff hash, files touched, `high_risk` flag via `classify_patch_risk`) after patcher, 5 verification stage rows after verifier, and final `Run` row (status, confidence, merge decision, cost); `server.create_run` seeds the `queued` run row; `GET /api/v1/runs/{run_id}/records` returns run + nested steps/patches/verifications (§7 `GET /runs/{id}` summary shape) |
| §3.3 Append-only tiers (3 + 5) | ✅ | `TieredMemoryStore._is_append_only_tier()` — `EPISODIC` and `VERIFIED_EVIDENCE` same-id writes are preserved: duplicate id gets a fresh id (both rows persist, never overwritten); mutable tiers keep replace-on-same-id semantics |

---

## Phase 0 Acceptance Criteria — Verification

| Epic | Acceptance Criterion | Status |
|---|---|---|
| Entitlement Service | Free-tier org calling gated endpoint returns 403 with reason | ✅ `test_create_run_tier_b_denied_on_solo_org`, `test_create_run_tier_c_denied_on_solo_org`, `test_create_run_rbac_blocks_developer_from_admin_action` |
| Usage Ledger + Metering | Every AgentStep → exactly one ledger row; rollup idempotent on replay | ✅ `test_ledger_*` (dedup), `test_rollup_replay_is_idempotent` |
| RBAC scaffolding | Admin-only action as Developer → 403 in integration suite | ✅ `test_create_run_rbac_blocks_developer_from_admin_action`, `test_developer_authorize_raises_permission_error` |

New test coverage added in this pass: `tests/test_audit_log.py`, `tests/test_rollup.py`,
`tests/test_sandbox_tiers.py::test_blocked_egress_writes_audit_entry`, API tier-gating tests,
orchestrator planner/merge-decision tests, `tests/test_domain_models.py` (RepoConnection),
orchestrator lifecycle-webhook + SECURITY_HOLD integration tests, API evidence-export test,
`tests/test_post_merge.py` (rollback rule, revert-patch reversal, monitor record/audit/webhook,
runner delegation), orchestrator CONFLICT_RESOLUTION + actor + bundle-content tests,
memory tenant isolation/default-org/TTL tests, API ci-report rollback tests,
`tests/test_records_store.py` (run upsert, one-step-row-per-node, patch/verification rows,
stage mapping, orchestrator records integration), API records endpoint tests,
memory append-only tier tests.
Full suite: 287 passing.