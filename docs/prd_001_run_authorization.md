# PRD-001 Run Authorization

This change centralizes run-level authorization at the API boundary.

Every run-scoped read or mutation resolves the authoritative `RunRecord` and binds it to the authenticated principal's organization before applying RBAC.

Cross-tenant access intentionally returns `404 Not Found` to avoid leaking run existence across organizations.

## Protected routes

- `GET /runs/{run_id}`
- `GET /runs/{run_id}/evidence`
- `GET /runs/{run_id}/records`
- `POST /rollback/{run_id}` and `/runs/{run_id}/rollback`
- `POST /runs/{run_id}/ci-report`
- `GET /stream/{run_id}`

## Regression contract

- Own-tenant run: allowed when role has `view_run`.
- Cross-tenant run/evidence/records/rollback/CI/stream: `404`.
- Missing authentication: `401`.
- Authenticated principal with insufficient role: `403`.
