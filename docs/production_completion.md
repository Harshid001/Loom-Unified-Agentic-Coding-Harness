# Production Completion Checklist

## Repository-side controls

- Fail-closed production authentication and explicit development bypass
- Tenant-bound identity and org-scoped run/evidence access
- Production Redis rate limiting
- Request-size and webhook-signature protections
- Hardened Docker sandbox with no implicit host fallback
- Tier C Firecracker provider boundary that fails closed when unavailable
- Privileged token control-plane boundary
- Billing lifecycle state and provider-neutral event handling
- Tenant-safe memory synchronization primitives
- Durable run-state transition and worker-heartbeat primitives
- Backup integrity, encryption, and restore tooling
- SCIM provisioning/deprovisioning primitives
- CI lint, typecheck, dependency audit, tests, frontend verification, and container checks

## Deployment gates

A production release is approved only after the target environment has verified the external dependencies that cannot be proven by repository inspection alone:

1. PostgreSQL and Redis are reachable and healthy.
2. The production sandbox worker is isolated from the API host.
3. Tier C has a deployed Firecracker worker and passes an end-to-end execution test.
4. Backup scheduling and off-site retention are active.
5. A restore drill records measured RPO/RTO.
6. Any billing provider adapter is configured and webhook signatures are verified.
7. A staging deployment passes the complete release suite and smoke tests.
8. The exact release commit has a green GitHub Actions run.
9. Load and failure-recovery tests pass on the deployment topology.
