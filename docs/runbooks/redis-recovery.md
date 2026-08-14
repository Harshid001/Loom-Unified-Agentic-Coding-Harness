# Loom Operational Runbook — Redis Recovery

## Symptom
API returns 503 on rate-limited endpoints or active runs state is unresponsive due to Redis cluster failure.

## Recovery Procedure

1. **Verify Connectivity:**
   ```bash
   redis-cli -u $REDIS_URL PING
   ```

2. **Failover to Sentinel / Replica:**
   If primary Redis node is unresponsive, trigger Sentinel failover:
   ```bash
   redis-cli -h $SENTINEL_HOST -p 26379 SENTINEL failover master-loom
   ```

3. **Fallback Mode:**
   If Redis cannot be recovered immediately, Loom API automatically falls back to `LocalRunStore` for single-node deployments.
