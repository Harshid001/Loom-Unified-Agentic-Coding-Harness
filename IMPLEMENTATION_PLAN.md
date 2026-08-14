# Loom Production Readiness Implementation Plan

Source: Production Readiness Audit dated 2026-08-15.

## Phase 1 — Production blockers

1. Activate request-scoped principal and runtime guard middleware; add end-to-end tenant-isolation regression tests.
2. Make authentication fail closed unless development is explicitly enabled (`LOOM_ENV=development` and `DEV_MODE=true`); validate auth configuration during app construction.
3. Authorize rollback before action; validate `run_id` as a safe identifier and enforce checkpoint path containment.
4. Preserve `SECURITY_HOLD` during terminal status derivation and add regression coverage.
5. Select one PostgreSQL migration system, make it authoritative, and read the actual applied schema version instead of a hardcoded value.
6. Eliminate worker duplicate execution by introducing a heartbeat-renewed job lease or heartbeat-aware reclaim protocol; test jobs beyond the visibility timeout.
7. Make restore drills target-only and non-production by construction; fix the shell drill's stale import.
8. Enforce org scoping in run listing independently of middleware so tenant filtering cannot disappear silently.
9. Connect the dashboard execution flow to the real API routes/SSE proxy; remove or explicitly gate mock execution.
10. Make CI/release gates truthful: fix lint/type errors and the failing security-hold test, and fail gates when required scanners are missing.
11. Resolve/stage the current merge-conflict files and remove obsolete snapshot branches from the development workflow.
12. Replace spoofable per-IP rate limiting with trusted-proxy-aware and credential-aware limiting; protect dashboard login.
13. Enforce SSRF URL validation directly in Slack/webhook handlers, not only via optional middleware.

## Phase 2 — High-priority hardening

- Enforce target-org authorization on admin/usage endpoints.
- Make record-store failures fatal in production and use atomic checkpoint writes.
- Harden sandbox egress matching, symlink-safe restore, and worker TLS.
- Add dashboard security headers, CSRF/Origin checks, and server-side session identifiers.
- Encrypt webhook secrets at rest and fix webhook event filtering/SCIM token comparison.
- Add database foreign keys, bounded/paginated reads, pool health settings, and remove fabricated AST responses.
- Add backup-failure alerting, checkpoint backup coverage, bounded retries/DLQ, and correct inbound CI webhook authentication.

## Phase 3 — Quality, scale, and operability

- Add frontend route/LiveBox/AuthGate tests and backend tests for Firecracker, worker, browser, and distributed paths.
- Move run listing to Postgres with validated pagination and caching.
- Activate a durable run-state store/job-lease framework.
- Add IaC, SLO alerting, canary/blue-green deployment, and automated rollback.
- Raise backend coverage to at least 80% and require production-gate evidence to be generated from actual command results.

## Verification gate

Production approval requires green `ruff`, `mypy`, full `pytest`, tenant-isolation regression tests, frontend lint/typecheck/tests/build, database migration validation, disposable-database restore drill, clean git index, and verified Docker/Firecracker/live-E2E checks.
