# Loom Agentic Harness — Production Deployment Guide

This document describes the supported production controls. Production execution must fail closed when a required security boundary is unavailable.

---

## 1. Containerized Deployment

Production deployments should use the Docker image and PostgreSQL-backed records store. The Docker sandbox must be available for Tier B/C runs; the application never silently falls back to host execution in production.

```bash
docker compose up -d --build
docker compose logs -f api
```

**Important:** The current Docker sandbox implementation still uses the Docker daemon from the execution host. A separate sandbox-worker control plane is the next isolation milestone; until then, keep the Docker host dedicated to Loom workloads and do not expose the daemon remotely.

---

## 2. Native Deployment

Native PM2 execution is intended for development and local testing only.

```bash
pm2 start ecosystem.config.js
pm2 status
```

---

## 3. Required Production Environment

| Variable | Production requirement | Purpose |
| :--- | :--- | :--- |
| `LOOM_ENV` | `production` | Enables fail-closed security behavior |
| `API_KEY` | Required | Backend API authentication |
| `DASHBOARD_AUTH_TOKEN` | Required | Web dashboard authentication |
| `ALLOWED_REPO_ROOTS` | Required | Restricts target repository paths |
| `DATABASE_URL` | Strongly recommended | PostgreSQL durable records store |
| `ALLOWED_ORIGINS` | Explicit allowlist | CORS policy |
| `LOOM_BACKUP_ENCRYPTION_KEY` | Required for encrypted backups | Fernet key for backup encryption |
| `LOOM_TOKEN_ADMIN_ENABLED` | `false` by default | Enables token-management API only after a privileged control-plane is configured |

Generate a Fernet key once and store it in a secrets manager:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

---

## 4. Backup & Disaster Recovery

` scripts/backup_restore.py ` creates integrity-checked backups. In production, `LOOM_BACKUP_ENCRYPTION_KEY` is mandatory and backups are encrypted before storage.

```bash
python scripts/backup_restore.py create --dir ./backups
python scripts/backup_restore.py restore ./backups/loom_backup_YYYYMMDD_HHMMSS.tar.gz.enc
```

The restore path rejects unsafe archive members, verifies SHA-256 checksums, decrypts encrypted archives, and can restore PostgreSQL custom-format dumps when `pg_dump`/`pg_restore` and `DATABASE_URL` are available.

Backups still require an external scheduler, off-host retention policy, and periodic restore drills before they can be considered a complete disaster-recovery program.

---

## 5. Health & Monitoring

- `GET /healthz` — liveness
- `GET /api/v1/health/readiness` — storage/database readiness
- `GET /metrics` — Prometheus metrics
- OpenTelemetry exporters can be configured through `OTEL_EXPORTER_OTLP_ENDPOINT`

---

## 6. Release Verification

Every production release must pass the GitHub Actions workflow:

```text
Backend: install → dependency audit → ruff → mypy → pytest
Frontend: npm ci → npm audit → lint → typecheck → Vitest → production build
Container: docker build --pull
Native: loom version + loom init
```

A green source diff without a green CI run is not a production approval.
