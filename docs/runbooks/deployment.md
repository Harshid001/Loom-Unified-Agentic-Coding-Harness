# Loom Operational Runbook — Production Deployment

## Target Architecture

Loom runs as a stateless API service behind a load balancer, backed by:
- PostgreSQL (relational state store)
- Redis (distributed run store + pub/sub event bus)
- Firecracker microVM worker nodes (Tier C execution isolation)

---

## Pre-Deployment Verification Gate

Before promoting any build to production:

```bash
# 1. Run the baseline capture & production release gate
python scripts/production/capture_baseline.py
python scripts/production/final_release_gate.py

# 2. Verify all 15 production gates pass
# Expected output: "FINAL RELEASE GATE VERDICT: PASSED (15/15 GATES)"
```

---

## Zero-Downtime Deployment Sequence

1. **Database Migration:**
   ```bash
   python -m loom.db.migration_runner --url $POSTGRES_URL --up
   ```

2. **Rolling Worker Update:**
   Deploy the new code to the worker one host at a time. Active runs finish on legacy nodes.

3. **API Fleet Update:**
   Deploy the API code and restart `loom-api`. Healthcheck endpoint `/api/v1/health/readiness` must return 200 OK before traffic is routed.

---

## Post-Deployment Validation

```bash
curl -f -H "X-API-Key: $API_KEY" https://loom-api.internal/api/v1/health/readiness
```
