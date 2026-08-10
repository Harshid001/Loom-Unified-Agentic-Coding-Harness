# Loom API Reference

## Authentication

All state-changing endpoints (`/api/v1/run`, `/api/v1/rollback`) require mandatory API key authentication.
Pass your API key in the request header:
```http
X-API-Key: your-secret-api-key
```

## Endpoints

### 1. Health Checks
- **`GET /api/v1/health/liveness`**
  Returns liveness status `{"status": "alive", "service": "Loom API"}`.
- **`GET /api/v1/health/readiness`**
  Returns database and storage component status.

### 2. Metrics & Observability
- **`GET /metrics`**
  Exposes Prometheus metrics format (`loom_requests_total`, `loom_request_duration_seconds`).

### 3. Execution & Runs
- **`GET /api/v1/runs?limit=50&offset=0`**
  Retrieves paginated execution run histories.
- **`GET /api/v1/runs/{run_id}`**
  Retrieves execution details, checkpoints, and trace logs for a specific run ID.
- **`POST /api/v1/run`**
  Triggers a new agentic execution graph.
  **Body**:
  ```json
  {
    "issue": "Fix authentication bug in login router",
    "repo_path": ".",
    "mock": false,
    "model": "claude-3-5-sonnet-20241022"
  }
  ```

### 4. Rollback & State Restoration
- **`POST /api/v1/rollback/{run_id}`**
  Restores codebase to snapshot pre-patch state.
