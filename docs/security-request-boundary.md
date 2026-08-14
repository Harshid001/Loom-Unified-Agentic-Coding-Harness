# Security Request Pipeline Boundary Architecture

This document defines the canonical 8-stage security request pipeline for all HTTP API requests in Loom.

## Pipeline Architecture

```text
Request
  ↓
1. Authentication (verify_api_key / auth tokens / SCIM tokens)
  ↓
2. Identity Binding (AuthenticatedPrincipal context resolution)
  ↓
3. Tenant / Resource Lookup (authoritative record store lookup)
  ↓
4. Resource Authorization (require_run_access & AuthorizationContext validation)
  ↓
5. RBAC Enforcement (RBACEnforcer role evaluation: VIEW_RUN, ROLLBACK_RUN, REPORT_CI)
  ↓
6. Business Operation (Endpoint execution / DAG task state update)
  ↓
7. Security Audit Logging (AuditAction recording: RUN_AUTHORIZATION_DENIED, etc.)
  ↓
Response / Stream Output
```

## Security Invariants

### 1. Fail-Closed Tenant Boundaries
- Any attempt to access a run belonging to a different organization or a non-existent run ID **MUST** return `404 Not Found`.
- Returning `403 Forbidden` for a cross-tenant resource is explicitly forbidden because it leaks resource existence to potential attackers attempting run ID enumeration.

### 2. Route Dependency Authorization Injection
- Authorization dependencies are attached directly to registered FastAPI `APIRoute.dependencies` via `install_run_authorization()`.
- Endpoint callables, parameter signatures, and response model definitions remain untouched, preserving async execution, Pydantic model validation, and SSE `StreamingResponse` generators.
- Installation is strictly **idempotent** using route markers (`_loom_run_authorized`).

### 3. Identity & Role Matrix Enforcement

| Role | `VIEW_RUN` | `ROLLBACK_RUN` | `REPORT_CI` | `MODIFY_ENTITLEMENTS` |
| :--- | :---: | :---: | :---: | :---: |
| **OWNER** | Allowed | Allowed | Allowed | Allowed |
| **ADMIN** | Allowed | Allowed | Allowed | Allowed |
| **DEVELOPER** | Allowed | Denied (403) | Denied (403) | Denied (403) |
| **REVIEWER** | Allowed | Denied (403) | Denied (403) | Denied (403) |
| **AUDITOR** | Allowed | Denied (403) | Denied (403) | Denied (403) |
| **BILLING_ADMIN** | Denied (403) | Denied (403) | Denied (403) | Denied (403) |

### 4. Audit Trail
- Security violations (cross-tenant access or RBAC role failures) emit internal audit events (`AuditAction.RUN_AUTHORIZATION_DENIED`) via `get_audit_logger()`.
- Audit logs contain `org_id`, `actor_id`, and `action` details internally while maintaining uninformative `404` or `403` client responses.
