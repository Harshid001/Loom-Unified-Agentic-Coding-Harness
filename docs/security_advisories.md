# Loom Security Advisories & Dependency Risk Acceptance Matrix

## Overview
This document tracks known security advisories, remediation actions, and risk acceptance policies for production dependencies across the Loom agentic coding harness backend and web dashboard frontend.

## Dependency Security Audits

### Python Backend Dependencies (PRD-001)
- **Status**: Remediated. Minimum secure dependency versions enforced in `pyproject.toml`.
- **Target Threshold**: Zero critical or high vulnerabilities in production environments (`pip-audit`).
- **Enforced Minimum Package Versions**:
  - `cryptography>=42.0.0`
  - `pillow>=10.3.0`
  - `starlette>=0.36.3`
  - `pyjwt>=2.8.0`
  - `urllib3>=2.2.2`
  - `werkzeug>=3.0.3`
  - `fastapi>=0.110.0`
  - `uvicorn[standard]>=0.28.0`

### Next.js Frontend Advisory Matrix (PRD-002)
- **Framework**: Next.js 14.2.x / 15.x patch stream
- **Risk Assessment**:
  - **GHSA-ffhc-5mcf-pf4q (XSS)**: Mitigation active via Content-Security-Policy headers and standard React auto-escaping.
  - **GHSA-c4j6-fc7j-m34r (SSRF)**: Mitigation active via restricted BFF proxy routes with hardcoded target backend URLs.
  - **GHSA-vfv6-92ff-j949 (Cache Poisoning)**: Mitigation active via `cache: 'no-store'` directive on server-side proxy fetches.
  - **GHSA-9g9p-9gw9-jx7f (DoS)**: Mitigation active via backend request size limits and edge rate limiting.

## Security Governance
- Dependencies are audited on every release build.
- Dependabot / Renovate automated dependency updates are enforced via GitHub Actions workflows.
