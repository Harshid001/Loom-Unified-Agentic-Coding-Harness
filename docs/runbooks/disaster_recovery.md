# Disaster Recovery & Backup Operations Runbook

## 1. Overview & Objectives

This runbook defines the disaster recovery (DR), backup scheduling, automated restore validation, and business continuity procedures for the **Loom Unified Agentic Coding Harness**.

### Service Level Objectives (SLOs)

| Metric | Target SLA | Description |
|---|---|---|
| **RPO (Recovery Point Objective)** | **< 1 Hour** | Maximum permissible data loss interval in the event of catastrophic storage failure. Achieved via hourly automated snapshot backups and WAL-level replication. |
| **RTO (Recovery Time Objective)** | **< 15 Minutes** | Maximum allowable downtime to restore full API, orchestrator, and database service from cold backups. |
| **Integrity Assurance** | **100% SHA256 Verified** | All backup archives are encrypted with AES-256-GCM and verified with SHA-256 checksums prior to extraction. |

---

## 2. Backup Architecture & Data Sources

Loom stores persistent state across two key tiers:
1. **Relational Database (PostgreSQL / SQLite fallback)**:
   - Contains organizations, users, API tokens, RBAC roles, audit logs, billing usage ledger, and execution metadata.
2. **Loom Runtime Home (`~/.loom` or `LOOM_HOME`)**:
   - Contains task graphs, checkpoints, evidence bundles, verification artifacts, and vector memory embeddings.

---

## 3. Automated Backup Creation & Scheduling

### Automated Scheduler

Backups are managed continuously by the backup scheduler worker or cron daemon:

```bash
# Run backup scheduler with 1-hour interval and 7-day retention
python scripts/backup_scheduler.py --interval-seconds 3600 --retention-days 7 --backup-dir /var/backups/loom
```

### Manual Backup Creation

To generate an immediate, encrypted, timestamped backup archive:

```bash
python scripts/backup_restore.py create --backup-dir /var/backups/loom
```

Archive output format:
`loom-backup-<YYYYMMDD-HHMMSS>-<SHA256_PREFIX>.tar.gz`

---

## 4. Disaster Recovery & Automated Restore Drills

Production gate validation requires routine, automated restore drills against isolated, disposable targets before and after major deployments.

### Running a Restore Drill

```bash
python scripts/restore_drill.py \
  --backup-dir ./drill-backups \
  --restore-home ./drill-restore \
  --database-url "postgresql://drill_user:drill_pass@localhost:5432/loom_drill" \
  --confirm-disposable \
  --report ./restore-drill-report.json
```

### Drill Verification Metrics

The automated drill report output from live execution:
```json
{
  "timestamp": "2026-08-18T07:40:00Z",
  "status": "passed",
  "backup": "loom_backup_20260818_130848.tar.gz",
  "backup_sha256": "103eb66853bd449cd5514c96126817b088a8410e412ea5945c74a65d2ed31477",
  "backup_size_bytes": 776,
  "backup_duration_seconds": 0.03,
  "restore_duration_seconds": 0.014,
  "rto_seconds": 0.044,
  "rpo_seconds": 0.021,
  "rto_sla_met": true,
  "rpo_sla_met": true,
  "records_verified": true,
  "evidence_verified": true
}
```

### Automated CI Workflow
Automated disaster recovery drills are executed weekly via GitHub Actions at [`.github/workflows/restore-drill.yml`](file:///d:/NewVolumeE/Unified%20agentic%20coding%20harness/.github/workflows/restore-drill.yml) (cron `0 2 * * 0`) and on-demand via `workflow_dispatch`. Drill reports are uploaded as build artifacts with a 30-day retention policy.

---

## 5. Cold Restore Procedure (Disaster Recovery Incident)

In the event of primary host loss or database corruption:

1. **Provision New Target Infrastructure**:
   - Deploy new Postgres 16 instance and Loom API host.
   - Configure environment variables (`DATABASE_URL`, `LOOM_ENCRYPTION_KEY`, `REDIS_URL`).

2. **Retrieve Latest Verified Backup from Offsite Storage**:
   ```bash
   aws s3 cp s3://loom-encrypted-backups/latest-verified.tar.gz /var/backups/loom/
   ```

3. **Verify Integrity & Decrypt**:
   ```bash
   python scripts/backup_restore.py verify /var/backups/loom/latest-verified.tar.gz
   ```

4. **Restore Database & Runtime State**:
   ```bash
   python scripts/backup_restore.py restore \
     --archive /var/backups/loom/latest-verified.tar.gz \
     --target-loom-home /home/loom/.loom \
     --target-database-url "$DATABASE_URL"
   ```

5. **Execute Health Checks & Validation**:
   ```bash
   curl -f http://localhost:8000/api/v1/health/readiness
   curl -f http://localhost:8000/api/v1/system/status
   ```
