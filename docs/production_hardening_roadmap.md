# Production Hardening Roadmap

This document tracks production controls implemented on the canonical `main` branch.

## Implemented in this hardening branch

- Production Docker sandbox fails closed when Docker is unavailable.
- Patch and verification agents honor the selected sandbox tier.
- Production Tier B/C execution can be delegated to an authenticated sandbox worker.
- API container no longer mounts the Docker daemon socket.
- Sandbox worker is the only service that mounts the Docker socket.
- Sandbox worker runs non-root and uses the host Docker group via `DOCKER_GID`.
- Production startup validates security-critical environment variables.
- Dashboard token comparison uses constant-time comparison.
- API token administration is disabled by default in production until a privileged control-plane path is enabled.
- Backups use consistent SQLite copies, optional Fernet encryption, SHA-256 checksums, and safe archive extraction.
- Frontend typecheck and tests are enforced in CI.
- Backend dependency audit, lint, typecheck, and tests are enforced in CI.
- Production container builds are enforced in CI.

## Remaining production work

### Distributed runtime

`ACTIVE_RUNS` and the current IP rate limiter are still process-local in `loom/api/server.py`. Production horizontal scaling requires a shared rate limiter (for example Redis) and durable run-control state with worker coordination.

### Tier C isolation

Tier C is currently backed by the hardened Docker worker as a compatibility implementation. A real Firecracker microVM backend is still required before claiming VM-level isolation.

### Disaster recovery operations

The backup utility is implemented, but production still needs an external scheduler, off-host encrypted retention, retention policy, restore drills, and measured RPO/RTO.

### Release verification

Production approval requires a green CI run on the final release commit plus a staging deployment verification. Source inspection alone is not sufficient.

### Token administration

The token-management routes remain intentionally disabled in production by default. A real privileged control-plane authorization path should be wired before enabling them.
