# Loom API Reference Manual

**API Version:** `v1`  
**Base URL:** `https://api.loom.dev` (Production) / `http://localhost:8000` (Local)  
**OpenAPI Specification:** Available at `/openapi.json` (Authenticated in Production)

---

## 1. Authentication & Security

Loom enforces multi-tenant, role-based access control (RBAC) across all state-changing endpoints. Requests must authenticate using one of the supported methods:

### Authentication Headers

1. **API Key Authentication (Recommended for CI/CD & Automated Workers)**
   ```http
   X-API-Key: loom_live_sec_0192837465abcdef...
   ```
2. **Bearer Token Authentication (Dashboard & SCIM)**
   ```http
   Authorization: Bearer <jwt_or_session_token>
   ```

### Tenant Identification
Multi-tenant requests are automatically scoped to the organization bound to the API key. In multi-tenant environments with administrative tokens, pass:
```http
X-Org-ID: org_enterprise_corp
```

---

## 2. Health, Status & Observability

### 2.1 Liveness Probe
- **`GET /api/v1/health/liveness`** (Aliases: `/healthz`, `/livez`)
- **Auth:** None
- **Response (200 OK):**
  ```json
  {
    "status": "alive",
    "service": "Loom API"
  }
  ```

### 2.2 Readiness Probe
- **`GET /api/v1/health/readiness`** (Aliases: `/readyz`)
- **Auth:** None
- **Response (200 OK):**
  ```json
  {
    "status": "ready",
    "service": "Loom API",
    "components": {
      "database": "ok",
      "storage": "ok"
    }
  }
  ```
- **Response (503 Service Unavailable):**
  ```json
  {
    "status": "not_ready",
    "components": {
      "database": "failed",
      "storage": "ok"
    }
  }
  ```

### 2.3 Prometheus Metrics
- **`GET /metrics`**
- **Auth:** Token Admin (Production) / Public (Local Dev)
- **Response (200 OK):**
  Prometheus text exposition format containing `loom_requests_total`, `loom_request_duration_seconds`, `loom_active_runs`, `loom_backup_last_status`.

### 2.4 System Status & SLA Metrics
- **`GET /api/v1/system/status`**
- **Auth:** Required (`viewer`+)
- **Response (200 OK):**
  ```json
  {
    "status": "healthy",
    "uptime_seconds": 348210,
    "sla": {
      "target_availability": 0.999,
      "current_availability": 0.9998,
      "p95_latency_ms": 142
    },
    "version": "1.0.0",
    "environment": "production"
  }
  ```

---

## 3. Run Execution & Orchestration Graph

### 3.1 Trigger Execution Run
- **`POST /api/v1/run`**
- **Auth:** Required (`operator`+)
- **Request Body:**
  ```json
  {
    "issue": "Fix authentication bug in login router when token expires",
    "repo_path": "/workspace/my-app",
    "model": "claude-3-7-sonnet-20250219",
    "mock": false,
    "context_budget_tokens": 32000,
    "sandbox_tier": "tier_b",
    "tags": ["bugfix", "security"]
  }
  ```
- **Response (200 OK / 202 Accepted):**
  ```json
  {
    "run_id": "run_01j9a8b7c6d5e4f3",
    "status": "queued",
    "issue": "Fix authentication bug in login router when token expires",
    "created_at": "2026-08-18T12:00:00Z",
    "stream_url": "/api/v1/runs/run_01j9a8b7c6d5e4f3/stream"
  }
  ```

### 3.2 List Execution Runs
- **`GET /api/v1/runs`**
- **Query Parameters:**
  - `offset` (int, default: 0): Pagination offset
  - `limit` (int, default: 50, max: 100): Maximum runs to return
  - `status` (string, optional): Filter by `queued`, `running`, `completed`, `failed`
- **Response (200 OK):**
  ```json
  [
    {
      "id": "run_01j9a8b7c6d5e4f3",
      "issue": "Fix authentication bug in login router when token expires",
      "status": "VERIFIED SUCCESS",
      "repo_path": "/workspace/my-app",
      "created_at": "2026-08-18T12:00:00Z",
      "cost": 0.0412
    }
  ]
  ```

### 3.3 Get Run Details
- **`GET /api/v1/runs/{run_id}`**
- **Auth:** Required (`viewer`+)
- **Response (200 OK):**
  ```json
  {
    "run_id": "run_01j9a8b7c6d5e4f3",
    "status": "completed",
    "verification_passed": true,
    "issue_description": "Fix authentication bug in login router when token expires",
    "patch_diff": "diff --git a/auth/router.py...",
    "snapshot_id": "snap_1723982400000000000_patch_pre",
    "created_at": "2026-08-18T12:00:00Z",
    "shared_data": {
      "cost_report": {
        "total_cost_usd": 0.0412,
        "input_tokens": 12450,
        "output_tokens": 1820
      }
    }
  }
  ```

### 3.4 Real-time SSE Execution Stream
- **`GET /api/v1/runs/{run_id}/stream`**
- **Headers:** `Accept: text/event-stream`
- **Auth:** Required
- **SSE Events Emitted:**
  - `step_start`: Agent stage started (`onboarding`, `reproduction`, `planner`, `patcher`, `verifier`)
  - `agent_thought`: Model planning and decision step
  - `tool_execution`: Sandboxed command or patch application
  - `verification_result`: Test execution output and assertion pass/fail
  - `complete`: Final run status and evidence hash

### 3.5 Cancel Active Run
- **`POST /api/v1/runs/{run_id}/cancel`**
- **Auth:** Required (`operator`+)
- **Response (200 OK):**
  ```json
  {
    "run_id": "run_01j9a8b7c6d5e4f3",
    "status": "cancelled",
    "message": "Run execution cancelled successfully"
  }
  ```

---

## 4. Snapshots, Rollback & State Restoration

### 4.1 Rollback Codebase
- **`POST /api/v1/rollback/{run_id}`**
- **Auth:** Required (`operator`+)
- **Response (200 OK):**
  ```json
  {
    "run_id": "run_01j9a8b7c6d5e4f3",
    "status": "rolled_back",
    "snapshot_id": "snap_1723982400000000000_patch_pre",
    "message": "Codebase restored to verified pre-patch state"
  }
  ```

### 4.2 List Snapshots
- **`GET /api/v1/snapshots`**
- **Auth:** Required (`viewer`+)
- **Response (200 OK):**
  ```json
  [
    {
      "snapshot_id": "snap_1723982400000000000_patch_pre",
      "created_at": 1723982400.0,
      "path": "/workspace/my-app/.loom_snapshots/snap_1723982400000000000_patch_pre"
    }
  ]
  ```

---

## 5. Verification & Evidence Bundles

### 5.1 Retrieve Tamper-Evident Evidence Bundle
- **`GET /api/v1/runs/{run_id}/evidence`**
- **Auth:** Required (`viewer`+)
- **Response (200 OK):**
  ```json
  {
    "bundle_id": "ev_01j9a8b7c6d5e4f3",
    "run_id": "run_01j9a8b7c6d5e4f3",
    "sha256_chain": "8f3b2e1a9c4d5e6f708192a3b4c5d6e7f8091a2b3c4d5e6f7a8b9c0d1e2f3a4b",
    "verification_passed": true,
    "tests_executed": [
      {
        "name": "test_auth_token_expiry",
        "passed": true,
        "duration_ms": 45
      }
    ],
    "patch_sha256": "3a4b5c6d7e8f9012a3b4c5d6e7f8091a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e",
    "immutable": true
  }
  ```

---

## 6. Authentication & API Key Management

### 6.1 Issue API Token
- **`POST /api/v1/auth/tokens`**
- **Auth:** Required (`admin` role)
- **Request Body:**
  ```json
  {
    "user_id": "usr_dev_01",
    "label": "github-actions-ci",
    "org_id": "org_enterprise_corp"
  }
  ```
- **Response (200 OK):**
  ```json
  {
    "token": "loom_live_sec_99a8b7c6d5...",
    "token_id": "tok_01j9a8b7c6d5e4f3",
    "user_id": "usr_dev_01",
    "org_id": "org_enterprise_corp",
    "label": "github-actions-ci",
    "prefix": "loom_live_sec_99",
    "created_at": "2026-08-18T12:00:00Z"
  }
  ```

### 6.2 Revoke API Token
- **`DELETE /api/v1/auth/tokens/{token_id}`**
- **Auth:** Required (`admin` role)
- **Response (200 OK):**
  ```json
  {
    "revoked": true,
    "token_id": "tok_01j9a8b7c6d5e4f3"
  }
  ```

---

## 7. Audit Logging & Compliance

### 7.1 Query Audit Trail
- **`GET /api/v1/audit/logs`**
- **Auth:** Required (`admin` or `compliance` role)
- **Query Parameters:** `limit=50`, `offset=0`, `event_type=run_completed`
- **Response (200 OK):**
  ```json
  [
    {
      "event_id": "aud_01j9a8b7c6d5e4f3",
      "timestamp": "2026-08-18T12:00:00Z",
      "org_id": "org_enterprise_corp",
      "actor_user_id": "usr_dev_01",
      "action": "run.trigger",
      "resource": "run_01j9a8b7c6d5e4f3",
      "ip_address": "192.0.2.1",
      "status": "success"
    }
  ]
  ```

---

## 8. Webhook Ingestion

### 8.1 GitHub Webhook Handler
- **`POST /api/v1/webhooks/github`**
- **Headers:** `X-Hub-Signature-256: sha256=...`, `X-GitHub-Event: issues`
- **Auth:** HMAC Signature Verification via configured webhook secret
- **Response (200 OK):**
  ```json
  {
    "status": "received",
    "event": "issues",
    "action": "opened",
    "run_triggered": true,
    "run_id": "run_01j9a8b7c6d5e4f3"
  }
  ```

### 8.2 GitLab Webhook Handler
- **`POST /api/v1/webhooks/gitlab`**
- **Headers:** `X-Gitlab-Token: <webhook_secret>`
- **Response (200 OK):**
  ```json
  {
    "status": "received",
    "event": "Issue Hook"
  }
  ```

---

## 9. SCIM 2.0 User Provisioning (Enterprise)

- **`GET /scim/v2/Users`** — Filter & paginate enterprise identity users.
- **`POST /scim/v2/Users`** — Provision new enterprise member.
- **`GET /scim/v2/Users/{id}`** — Retrieve SCIM identity resource.
- **`PUT /scim/v2/Users/{id}`** — Full attribute replacement.
- **`PATCH /scim/v2/Users/{id}`** — Partial user update (e.g. `active: false` deprovisioning).
- **`DELETE /scim/v2/Users/{id}`** — Deprovision and delete user.

---

## 10. Error Response Codes & Format

All error responses adhere to standard RFC 7807 problem details:

```json
{
  "detail": "Invalid snapshot label or unauthenticated request",
  "status_code": 400,
  "error_code": "INVALID_PARAM"
}
```

| HTTP Status | Reason |
|---|---|
| **400 Bad Request** | Malformed parameters, invalid label, or payload schema violation |
| **401 Unauthorized** | Missing or invalid `X-API-Key` or `Bearer` token |
| **403 Forbidden** | RBAC permission denied or cross-tenant access violation |
| **404 Not Found** | Run ID, snapshot, or resource does not exist |
| **429 Too Many Requests** | Rate limit exceeded. Check `Retry-After` header |
| **500 Internal Error** | Server-side execution or model failure |
| **503 Unavailable** | Database or storage readiness probe unhealthy |
