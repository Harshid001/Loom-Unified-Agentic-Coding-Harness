# Loom Agentic Harness — Production Deployment Guide

Production execution must fail closed when a required security boundary is unavailable.

## 1. Native deployment — systemd + Postgres + Redis + Nginx

Loom runs natively on a Debian/Ubuntu host under systemd. No container runtime is required.

Services:
- `loom-api` — FastAPI server (`loom.runtime.entrypoint`) on `127.0.0.1:8000`
- `loom-worker` — durable Redis-backed run worker
- `loom-backup` — scheduled encrypted backups
- `loom-dashboard` — Next.js standalone dashboard on `127.0.0.1:3000`
- `nginx` — TLS reverse proxy (see `infra/systemd/nginx.conf`)
- `postgresql` / `redis-server` — distro packages

Deploy on a Debian/Ubuntu host as root:

```bash
sudo bash infra/systemd/install.sh /opt/loom
```

The installer creates the `loom` user, installs packages, builds the dashboard (standalone output), applies PostgreSQL migrations, installs unit files from `infra/systemd/`, and enables all services. Then:

```bash
# Fill in real secrets (API_KEY, DASHBOARD_AUTH_TOKEN, DATABASE_URL, provider keys)
sudo nano /etc/loom/loom.env
sudo nano /etc/loom/dashboard.env
sudo systemctl restart loom-api loom-dashboard
```

Post-deployment:

```bash
curl -f http://127.0.0.1:8000/api/v1/health/readiness
systemctl status loom-api loom-worker loom-dashboard
journalctl -u loom-api -f
```

Notes:
- Swap the generated self-signed TLS certs (`/etc/nginx/certs/`) for a real domain certificate before exposing publicly.
- Tier B/C (Firecracker microVM) requires a KVM host plus the worker unit at `infra/firecracker/loom-firecracker-worker.service`. Tier A (git worktree) runs on any host.
- Backups: `loom-backup` runs continuously; interval is `LOOM_BACKUP_INTERVAL_SECONDS`.

Validate configuration before startup:

```bash
python scripts/production_preflight.py
python scripts/postgres_migrate.py --database-url "$DATABASE_URL"
```

## 2. Firecracker worker

The repository pins the certified Firecracker baseline in `infra/firecracker/VERSION`. Before enabling production:
```bash
sudo bash scripts/validate_firecracker_host.sh
```

Populate `infra/firecracker/SHA256SUM` with the SHA-256 of the exact deployed Firecracker binary. The worker refuses to start its healthy execution path when the approved hash is missing or mismatched.

Then run the worker E2E validation from a Linux/KVM host:

```bash
LOOM_FIRECRACKER_WORKER_URL=http://127.0.0.1:8101 \
LOOM_FIRECRACKER_WORKER_TOKEN="$LOOM_FIRECRACKER_WORKER_TOKEN" \
bash scripts/e2e_firecracker_validation.sh
```

## 3. Required production environment

At minimum:

```env
LOOM_ENV=production
API_KEY=...
DASHBOARD_AUTH_TOKEN=...
ALLOWED_REPO_ROOTS=/var/repos
DATABASE_URL=postgresql://...
REDIS_URL=redis://...
LOOM_FIRECRACKER_WORKER_URL=http://firecracker-worker:8101
LOOM_FIRECRACKER_WORKER_TOKEN=...
LOOM_BACKUP_ENCRYPTION_KEY=...
LOOM_TOKEN_ADMIN_ENABLED=false
RATE_LIMIT_ALLOW_LOCAL_FALLBACK=false
```

Store production secrets in a dedicated secrets manager. Never commit real credentials.

## 3. PostgreSQL migrations

Production schema changes are versioned under `migrations/postgres/` and applied with an advisory lock:

```bash
python scripts/postgres_migrate.py --database-url "$DATABASE_URL"
```

Each applied migration records its filename and SHA-256 checksum in `schema_migrations`. A checksum mismatch blocks startup/deployment rather than silently accepting drift.

## 4. Backup and disaster recovery

Create an encrypted, checksummed backup:

```bash
python scripts/backup_restore.py create --dir ./backups
```

Run a measured restore drill:

```bash
python scripts/restore_drill.py \
  --backup-dir ./drill-backups \
  --restore-home ./drill-restore \
  --report ./restore-drill-report.json
```

The report records backup duration, restore duration, measured RPO and RTO. Production still requires off-site retention, scheduled execution, alerting on failures, and periodic successful drills.

## 5. Health and monitoring

- `GET /healthz` — liveness
- `GET /api/v1/health/readiness` — database/Redis readiness
- `GET /metrics` — Prometheus metrics
- OpenTelemetry exporters can be configured through `OTEL_EXPORTER_OTLP_ENDPOINT`

## 6. Load and failure testing

The load test can be run against the real staging/production topology:

```bash
python scripts/load_test.py \
  --base-url "$BASE_URL" \
  --api-key "$API_KEY" \
  --repo-path /var/repos/example \
  --concurrency 20 \
  --requests 100
```

Release approval should record measured p95/p99 latency, throughput, success rate, Redis behavior, worker capacity, and database saturation. Do not substitute arbitrary benchmark numbers for measured deployment evidence.

## 7. Release gates

The repository includes a manual workflow named `Production Release Gates`. It accepts a staging/production URL and runs the strict production preflight, API liveness/readiness, load test, Firecracker E2E validation, and restore drill using GitHub Environment secrets.

A release is approved only when:

1. source CI is green on the exact release commit;
2. staging passes the release suite and smoke tests;
3. PostgreSQL/Redis are healthy;
4. Firecracker hardware and E2E validation pass;
5. backup/restore drills pass with measured RPO/RTO;
6. load/concurrency tests pass on the real topology;
7. canary and rollback procedures are successfully exercised.

A green unit-test/build pipeline by itself is not production approval.
