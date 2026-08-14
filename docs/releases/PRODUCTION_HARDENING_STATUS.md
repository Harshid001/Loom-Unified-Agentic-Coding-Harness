# Production Hardening Status

This branch contains the current production-readiness hardening pass.

## Evidence policy

A control is not considered production-approved merely because its code exists. Release approval requires successful automated checks plus production-like runtime evidence for deployment, Firecracker, restore, and end-to-end execution.

## Current hardening areas

- Request-scoped authentication and tenant/resource guards
- Explicit fail-closed authentication posture
- Rollback authorization and safe run identifiers
- Security-hold preservation
- Single authoritative PostgreSQL migration source
- Renewable Redis execution leases and worker dead-letter handling
- Explicit disposable restore targets and checkpoint backup coverage
- Dashboard real execution path and explicit production mock rejection
- Credential-aware rate limiting
- Direct SSRF validation
- Sanitized production exception boundary
- Atomic checkpoint persistence
- PostgreSQL pool health and fail-fast persistence
- Sandbox egress hostname validation
- Symlink-safe snapshot restore
- HTTPS enforcement for production Firecracker workers
- Correct webhook event filtering
- SCIM constant-time token enforcement at the request boundary
- Evidence-based release gate behavior

## Verification boundary

The repository connector cannot execute the project's Windows/Linux runtime stack locally in this session. The hardening branch therefore remains subject to GitHub CI plus production-like infrastructure validation before a production release is approved.
