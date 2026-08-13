# Production Gate Runbook

This runbook turns Loom's production-readiness controls into a repeatable release process. A green repository CI run is necessary but does not prove that the deployed topology is safe to release.

## 1. Before the first staging gate

Configure a protected GitHub `staging` environment with the same secret names consumed by `.github/workflows/production-gates.yml`:

- `LOOM_PROD_API_KEY`
- `LOOM_PROD_DASHBOARD_AUTH_TOKEN`
- `LOOM_PROD_ALLOWED_REPO_ROOTS`
- `LOOM_PROD_DATABASE_URL`
- `LOOM_PROD_REDIS_URL`
- `LOOM_PROD_FIRECRACKER_WORKER_URL`
- `LOOM_PROD_FIRECRACKER_WORKER_TOKEN`
- `LOOM_PROD_BACKUP_ENCRYPTION_KEY`

The values must point to the staging topology. Keep the secret names stable so the workflow cannot accidentally mix staging credentials with production credentials.

Configure an equivalent protected `production` environment with production values and approval rules.

## 2. Run the exact release candidate

Start **Production Release Gates** manually from the release branch or commit and supply:

- `target_environment=staging` for the first validation pass
- `release_ref=<exact commit SHA or release tag>`
- `base_url=<staging API base URL>`
- `repo_path=<path covered by ALLOWED_REPO_ROOTS>`
- leave load, restore and Firecracker gates enabled

The workflow records the resolved commit SHA in `release-metadata.json`, runs configuration preflight, verifies PostgreSQL migrations, probes API readiness, executes the SLO test, validates the Firecracker worker and performs a restore drill.

## 3. Evidence review

A successful staging run should retain:

- `release-metadata.json`
- `release-health-evidence.json`
- `load-slo-evidence.json`
- `restore-drill-report.json`

Review the resolved release SHA, API health, error rate, p95/p99 latency, throughput and restore results before approving production.

## 4. Production promotion

Run the same workflow with:

- `target_environment=production`
- the same exact `release_ref` that passed staging
- the production API URL and production-approved repository path

Do not promote a different commit between staging and production validation.

## 5. Failure handling

Any failed gate keeps deployment approval blocked. Investigate the failure and rerun the exact release candidate after remediation. Do not convert a failed deployment gate into a warning by disabling the corresponding workflow input for production.

## 6. What this workflow does not prove

The repository cannot prove target-environment facts by itself. Production approval still requires an actual Linux/KVM Firecracker host, operational off-site backup scheduling, controlled failure injection, canary/rollback testing and browser-level verification against the deployed dashboard.
