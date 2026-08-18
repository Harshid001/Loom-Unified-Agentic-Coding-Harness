# Production Hardening Roadmap

This document tracks production controls implemented on the canonical `main` branch.

## Implemented and Verified on `main`

### 1. Hardware-Isolated Sandbox (Tier C Firecracker MicroVM)
- **Firecracker MicroVM Backend:** Real hardware virtualization powered by Firecracker (`loom.sandbox.firecracker_vm.FirecrackerVM`), utilizing `/dev/kvm` and virtio-vsock (`guest.vsock`) for hypervisor-isolated execution.
- **Vsock Guest Agent:** Dedicated guest daemon (`loom.sandbox.firecracker_guest_agent.FirecrackerGuestAgent`) running inside the guest rootfs communicating via AF_VSOCK RPC for command dispatch, signal propagation, and git worktree operations.
- **Authenticated Worker Daemon:** Standalone HTTPS worker service (`loom.sandbox.firecracker_worker.FirecrackerWorker`) running under non-privileged system user, requiring `LOOM_FIRECRACKER_WORKER_TOKEN` Bearer authentication.
- **Fail-Closed Policy:** In production (`LOOM_ENV=production`), `sandbox_for_state()` strictly enforces Tier B/C Firecracker worker configuration and fails closed with `RuntimeError` rather than allowing host or unconfined execution.
- **Docker Socket Elimination:** Docker daemon socket mounting is entirely eliminated from API and worker containers.

### 2. Distributed Runtime & Shared Rate Limiting
- **Cross-Replica Run State:** `ACTIVE_RUNS` in `loom.api.server` and `loom.runtime.distributed_runtime` is coordinated across horizontal API replicas using `RedisCoordinator` and `RedisRunStore`.
- **Distributed SSE Event Streaming:** Event streams (`/api/v1/stream/{run_id}`) use Redis Pub/Sub channels (`loom:run:{run_id}:events`) and durable event lists with automatic keepalive pings.
- **Shared Sliding-Window Rate Limiting:** `RedisRateLimiter` provides atomic sliding-window rate limiting across all API instances with tenant and IP partitioning, with graceful local fallback for standalone CLI/dev modes.
- **Cross-Instance Control Plane:** Control actions (`pause`, `resume`, `step`, `cancel`, `model_switch`, `rollback`, `approve_patch`) are dispatched across replicas via Redis control queues.

### 3. Disaster Recovery & Backup Operations
- **Automated Restore Drills:** Scheduled CI workflow (`.github/workflows/restore-drill.yml`) and automated drill script (`scripts/restore_drill.py`) measuring RTO (<15 min) and RPO (<1 hr).
- **Cryptographic Verification:** Backups use atomic SQLite snapshots, Fernet envelope encryption, and SHA-256 tamper-evident checksums with safe directory traversal prevention.
- **Documented Runbooks:** Detailed DR operations runbook at `docs/runbooks/disaster_recovery.md` with measured drill metrics.

### 4. Security & Compliance Hardening
- **RBAC & Tenant Isolation:** Strict organization boundaries enforced at database and API layers with deterministic route-action mapping (`loom.auth.rbac`).
- **Security Headers & Surface Policy:** CSP, HSTS, X-Frame-Options, and nosniff headers enforced globally; Swagger docs, ReDoc, and metrics endpoints restricted to authenticated credentials in production.
- **Privileged Control Plane:** Token administration endpoints in public API fail closed in production (`403 Forbidden`) to protect credentials.
- **SSRF & Payload Guards:** Inbound webhooks and outbound requests validate target IP ranges (blocking RFC1918/loopback/link-local addresses).

### 5. Automated CI/CD Gates
- **Comprehensive Quality Gates:** CI enforces ruff linting, strict mypy typechecking across all 125+ modules, pytest suite (690+ tests, 0 failures), dependency vulnerability scanning (`pip-audit`, `npm audit`), and Gitleaks secret scans.
- **Frontend Verification:** Vitest suite with automated accessibility (a11y) tests, TypeScript compilation, and production Next.js build validation on every pull request.
