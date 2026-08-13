# Loom Agentic Harness — Production Deployment Guide

This document outlines deployment configurations, containerization, environment variables, security policies, and monitoring setups for Loom.

---

## 1. Containerized Docker / Docker-Compose Deployment (Recommended)

Production environments should deploy Loom using isolated containers to enforce sandbox boundaries and fail-closed security posture.

```bash
# Build and launch complete production stack (PostgreSQL + Loom API + Isolated Sandboxes)
docker-compose up -d --build

# Inspect logs
docker-compose logs -f api
```

---

## 2. Native Deployment with PM2 Process Manager

Loom can also run natively on Python 3.10+ and Node 20+ for development and local testing.

### Startup via PM2 Ecosystem
```bash
# Launch all Loom services (FastAPI Backend + Next.js Web UI)
pm2 start ecosystem.config.js

# Monitor running processes
pm2 status
```

Services exposed:
- **Backend API**: `http://localhost:8000`
- **OpenAPI / Swagger UI**: `http://localhost:8000/docs`
- **Web Dashboard**: `http://localhost:3000`

---

## 3. Environment Variable & Fail-Closed Security Configuration

Create a `.env` file in the root directory (refer to [.env.example](file:///d:/NewVolumeE/Unified%20agentic%20coding%20harness/.env.example)):

| Variable Name | Default | Description |
| :--- | :--- | :--- |
| `LOOM_ENV` | `development` | Environment status (`production` enforces fail-closed auth & strict path policy) |
| `API_KEY` | *(Required in Prod)* | Secret key for securing API endpoints via `X-API-Key` header |
| `DASHBOARD_AUTH_TOKEN` | *(Required in Prod)* | Token for securing Next.js Web BFF endpoints (fails closed if missing) |
| `ALLOWED_REPO_ROOTS` | *(Mandatory in Prod)*| Comma-separated list of allowed root directories for `repo_path` execution |
| `DATABASE_URL` | *(SQLite default)* | PostgreSQL connection string (`postgresql://user:pass@host:5432/db`) |
| `ALLOWED_ORIGINS` | `http://localhost:3000` | Comma-separated CORS allowed origin origins |
| `RATE_LIMIT_PER_MINUTE` | `60` | Max API requests per minute per IP address |

---

## 4. Disaster Recovery & Backup / Restore

Automated backup and restore utilities are provided under `scripts/backup_restore.py`:

```bash
# Create an encrypted, compressed TAR.GZ backup archive with SHA-256 checksum
python scripts/backup_restore.py create --dir ./backups

# Restore from a backup archive with checksum validation
python scripts/backup_restore.py restore ./backups/loom_backup_YYYYMMDD_HHMMSS.tar.gz
```

---

## 5. Health & Monitoring Probes

Loom provides Kubernetes-style liveness and readiness endpoints under `/api/v1/health/`:

- **Liveness Probe**: `GET /api/v1/health/liveness`
  - Returns `200 OK` with `{"status": "alive"}`
- **Readiness Probe**: `GET /api/v1/health/readiness`
  - Validates SQLite/Postgres database connectivity and evidence filesystem access.
- **Prometheus Metrics**: `GET /metrics`

