# Loom Production Incident Runbook

## Incident Scenarios & Response Procedures

### 1. HTTP 401 Unauthorized Errors
- **Symptom**: Clients or web dashboard receiving 401 Unauthorized on `/api/v1/run`.
- **Cause**: Missing or invalid `X-API-Key` header.
- **Resolution**: Verify `API_KEY` environment variable on API server match header passed by client.

### 2. HTTP 429 Rate Limit Exceeded
- **Symptom**: API returns 429 Too Many Requests.
- **Cause**: IP host exceeded `RATE_LIMIT_PER_MINUTE` limit.
- **Resolution**: Increase `RATE_LIMIT_PER_MINUTE` setting in server environment or tune rate limit window.

### 3. LLM Provider Connection Failures
- **Symptom**: Runs fail with exception in production mode (`mock=False`).
- **Cause**: LiteLLM upstream completion failure (network timeout, rate limit, invalid key).
- **Resolution**: Verify provider API keys (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`) and inspect `/metrics` endpoint.

### 4. Database Storage Issues
- **Symptom**: Health readiness check returns 503 Database unready.
- **Cause**: Database file locked or PostgreSQL connection lost.
- **Resolution**: Check `LOOM_DB_PATH` or `DATABASE_URL` connectivity and connection pool status.
