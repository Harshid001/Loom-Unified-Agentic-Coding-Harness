# Loom Operational Runbook — Emergency Rollback

## Emergency Rollback Trigger Conditions

Trigger a rollback immediately if:
- Error rate exceeds SLO threshold (>0.5% over 5 minutes)
- `/api/v1/health/readiness` fails across >25% of API replicas
- Security hold cascade detected in audit logs

---

## Procedure

1. **Traffic Reversion:**
   Switch Load Balancer target group back to previous known-good deployment SHA.

2. **Database Schema Compatibility:**
   Loom migrations are backward-compatible by policy. If a rollback migration is explicitly required:
   ```bash
   python -m loom.db.migration_runner --url $POSTGRES_URL --down
   ```

3. **Verify Health:**
   ```bash
   curl -f -H "X-API-Key: $API_KEY" https://loom-api.internal/api/v1/health/readiness
   ```
