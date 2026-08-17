# Loom Production Readiness Implementation Plan

This plan maps the 2026-08-15 production-readiness findings to implementation phases and verification gates. The current remote `main` branch should be treated as the source of truth; findings from a local audit must be re-verified against remote before release.

## Phase 1 — 13 production blockers

PRD-001/008: wire request principal lifecycle and runtime guards; enforce tenant scope at the data-access boundary and add cross-org integration tests.

PRD-002: only allow authentication bypass when `LOOM_ENV=development` and `DEV_MODE=true`; fail closed otherwise when `API_KEY` is absent.

PRD-003: authorize rollback before any rollback work, validate identifiers, and constrain checkpoint paths to the checkpoint directory.

PRD-004: preserve `SECURITY_HOLD` during terminal status derivation and keep the regression test green.

PRD-005: keep exactly one PostgreSQL migration authority, with advisory locking/checksums and real schema-version reads.

PRD-006: add a heartbeat-renewed execution lease or equivalent reclaim protocol so an active long-running job cannot be claimed by a second worker.

PRD-007: make restore drills target a disposable/non-production database explicitly; fix the shell drill's module drift.

PRD-009: connect the dashboard to the actual backend/proxy routes and remove silent fake execution in production.

PRD-010: make CI gates truthful and green: ruff, mypy, pytest, and scanner-presence checks must fail closed.

PRD-011: reconcile any dirty index/snapshot branches against the current remote branch before release.

PRD-012: use trusted-proxy-aware, credential-aware rate limiting and protect dashboard login against brute force.

PRD-013: perform SSRF validation inside the Slack/webhook handlers themselves.

PRD-024: enforce patch approval execution gate — halt at `PENDING_APPROVAL` after patcher on high-risk patches or org policy, preventing sandbox/verification invocation until `approve_patch` is triggered.

PRD-025: real remote repository write path — authenticated branch creation, commit/push, and GitHub PR creation via `GitHubAPIClient` and `create-pr` endpoint.

## Phase 2 — High-priority hardening

PRD-014 target-org authorization; PRD-015 fail-fast record persistence and atomic checkpoints; PRD-016 sandbox egress/symlink/TLS controls; PRD-017 dashboard headers/CSRF/session hardening; PRD-019 webhook secret encryption/event filters/SCIM hardening; PRD-020 database foreign keys/pagination/pool health; PRD-022 backup alerting/checkpoint coverage/retry DLQ/webhook auth.

## Phase 3 — Scale and assurance

PRD-021 frontend route/E2E coverage and backend coverage ≥80%; PRD-023 Postgres-backed run listing and caching; durable worker lease/run-state framework; IaC; SLO alerting; canary/blue-green rollback; evidence-driven release gates.

## Production approval gate

Approval requires green backend lint/typecheck/tests, tenant-isolation regression tests, frontend lint/typecheck/tests/build, migration validation, disposable restore-drill validation, clean git state, and successful Docker/Firecracker/live E2E verification.
