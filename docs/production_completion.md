# Production Completion Checklist

## Repository-side controls

- [x] Fail-closed production authentication and explicit development bypass
- [x] Tenant-bound identity and org-scoped run/evidence access
- [x] Production Redis rate limiting
- [x] Request-size and webhook-signature protections
- [x] Tier B/C Firecracker boundary with fail-closed worker selection
- [x] Firecracker host validation and deployment E2E tooling
- [x] Privileged token control-plane boundary
- [x] Billing lifecycle state and provider-neutral event handling
- [x] Tenant-safe memory synchronization primitives
- [x] Durable run-state transition and worker-heartbeat primitives
- [x] Backup integrity, encryption, checksums, and restore tooling
- [x] Versioned PostgreSQL migration runner with advisory locking/checksums
- [x] CI lint, typecheck, dependency audit, tests, frontend verification, and container checks
- [x] Manual production release-gates workflow for deployment evidence
- [x] Measured backup/restore drill tooling with RPO/RTO output

## Deployment gates — must be proven in the target environment

Repository code can prepare these gates, but cannot honestly mark them passed without target-environment evidence:

1. PostgreSQL and Redis are reachable, healthy, and sized for the deployment.
2. `python scripts/postgres_migrate.py --database-url "$DATABASE_URL"` applies cleanly and reports the expected schema version.
3. The production sandbox worker is isolated from the API host.
4. Tier C has a deployed Firecracker worker and `scripts/e2e_firecracker_validation.sh` passes on Linux/KVM.
5. The exact Firecracker binary SHA-256 is populated in `infra/firecracker/SHA256SUM` and matches the deployed binary.
6. Backup scheduling and off-site encrypted retention are active.
7. `python scripts/restore_drill.py` passes and produces measured RPO/RTO evidence.
8. A staging deployment passes API liveness/readiness, browser smoke tests, and the complete release suite.
9. The exact release commit has a green GitHub Actions run.
10. Load/concurrency tests pass on the real deployment topology with measured SLO thresholds.
11. Failure-recovery tests pass for Redis outage, worker crash, API restart, and database connectivity loss.
12. Canary/rollback procedures are exercised successfully.

## Approval rule

Production deployment is **Not Approved** while any required deployment gate above is unverified or failing. A green source-level CI run is necessary but not sufficient for production approval.
