# Loom — Unified Agentic Coding Harness

> **Verification-first autonomous software engineering infrastructure.**

Loom takes a repository and an engineering task through a structured coding workflow: repository onboarding, reproduction, planning, patching, verification, evidence collection, review, and rollback.

The core design principle is simple:

> **An agent should not declare a fix successful without evidence.**

---

## Why Loom exists

Traditional coding agents often optimize for generating a plausible patch. Loom is designed around the harder problem: producing a patch that can be **reproduced, verified, reviewed, explained, and safely rolled back**.

```text
Issue / Task
     │
     ▼
Repository Intelligence
     │
     ▼
Reproduction
     │
     ▼
Planning
     │
     ▼
Patching
     │
     ▼
Verification
     │
     ▼
Evidence + Risk Decision
     │
     ├── Human review
     ├── Auto-merge when policy allows
     └── Rollback when required
```

---

## Core architecture

```text
                         ┌─────────────────────────┐
                         │      User / Developer   │
                         │       CLI / Dashboard   │
                         └────────────┬────────────┘
                                      │
                                      ▼
                         ┌─────────────────────────┐
                         │       FastAPI API       │
                         │  Auth / RBAC / Policies │
                         └────────────┬────────────┘
                                      │
                                      ▼
                         ┌─────────────────────────┐
                         │     Agent Orchestrator  │
                         │        TaskGraph        │
                         └────────────┬────────────┘
                                      │
             ┌────────────────────────┼────────────────────────┐
             ▼                        ▼                        ▼
      Repository Intel            Model Router             Memory
             │                        │                        │
             └────────────────────────┼────────────────────────┘
                                      ▼
                         ┌─────────────────────────┐
                         │     Specialist Agents   │
                         │                         │
                         │ Onboarding              │
                         │ Reproduction            │
                         │ Planning                │
                         │ Patching                │
                         │ Verification            │
                         │ Review                  │
                         └────────────┬────────────┘
                                      │
                                      ▼
                         ┌─────────────────────────┐
                         │ Sandbox / Git Worktree  │
                         │ Snapshot + Rollback     │
                         └────────────┬────────────┘
                                      │
                                      ▼
                         ┌─────────────────────────┐
                         │ Evidence / Telemetry    │
                         │ Tests / Builds / SAST   │
                         └─────────────────────────┘
```

### Execution stages

| Stage | Purpose |
|---|---|
| **Onboarding** | Map the repository, relevant symbols, conventions, and project context. |
| **Reproduction** | Establish a reproducible failure or concrete acceptance condition. |
| **Planning** | Produce an implementation strategy based on repository evidence. |
| **Patching** | Generate, validate, policy-check, and apply a patch. |
| **Verification** | Run build/test/lint/security/reproduction checks. |
| **Review** | Calculate confidence and determine merge, review, hold, or rollback. |

---

# Key capabilities

## Verification-first execution

Loom records evidence instead of trusting an LLM's claim that a fix worked.

Verification can include:

- build checks
- unit/integration tests
- reproduction testing
- linting
- type checking
- security-pattern analysis
- confidence scoring
- merge-decision policies
- evidence bundles
- rollback support

## Model-independent architecture

The agent layer is separated from individual model providers. Providers can be routed through the adapter layer without rewriting the orchestration engine.

Model selection can consider:

- task type
- model capability
- cost
- latency
- provider health
- context requirements
- quota headroom

## Repository intelligence

Loom includes repository-analysis components for:

- AST and symbol extraction
- repository mapping
- call-graph information
- dependency relationships
- git history analysis
- relevance scoring
- context budgeting
- repository-intelligence caching

This allows agents to retrieve targeted context instead of blindly consuming an entire repository.

## Context and prompt safety

The context layer provides:

- token-budget management
- relevance ranking
- truncation under budget pressure
- prompt-injection sanitization
- context summarization

Repository content is treated as **untrusted input**.

## Memory and provenance

Loom provides persistent memory infrastructure for repository/project context and execution information, with tenant-aware storage and provenance-oriented records.

## Security and policy controls

The platform contains controls for:

- API authentication
- RBAC
- organization memberships
- entitlements and feature gates
- quota evaluation
- usage accounting
- audit records
- path policy for sensitive patches
- evidence integrity
- rollback

## Observability

The project includes:

- Prometheus metrics
- OpenTelemetry-oriented tracing
- token and cost tracking
- execution telemetry
- benchmark/ablation tooling
- structured execution records

---

# Sandbox model

Loom separates coding operations from the user's main workspace using sandbox/worktree abstractions.

| Capability | Purpose |
|---|---|
| Local process sandbox | Fast local development/testing |
| Docker sandbox | Isolated container execution |
| Remote sandbox | Separate execution service for stronger deployment isolation |
| Worktree snapshots | Safe patch application and rollback |
| Resource limits | CPU/memory/timeout controls |
| Egress policy | Restrict outbound domains where enforced |

### Important production rule

Production deployments should **fail closed** when the required isolation layer is unavailable. A security boundary should never silently degrade into unrestricted host execution.

The repository also contains production-hardening work for a worker-separated container architecture. Real microVM/Firecracker isolation remains a separate deployment milestone and should not be claimed as implemented until the required infrastructure exists.

---

# Quick start

## Requirements

- Python **3.10+**
- Node.js **20+** for the web dashboard
- Git
- An LLM provider/API for live execution

Docker, PostgreSQL, and Redis are used by the distributed production architecture and are not required for the simplest local CLI workflow.

## Install from source

```bash
git clone https://github.com/Harshid001/Loom-Unified-Agentic-Coding-Harness.git
cd Loom-Unified-Agentic-Coding-Harness
pip install -e .
```

## Environment configuration

```bash
cp .env.example .env
```

Set the provider credentials and local configuration required by your selected model/provider.

**Never commit real credentials to the repository.**

---

# Run Loom against a project

## Option A — one-command workflow

```bash
cd /path/to/target-project
loom fix "Fix the total_price calculation error"
```

Run with a real provider:

```bash
loom fix "Fix the total_price calculation error" --no-mock --model <model-name>
```

## Option B — explicit workflow

```bash
loom init --path /path/to/target-project
loom issue "Add validation for duplicate email addresses"
loom run --mock
```

Inspect the result:

```bash
loom trace <run_id>
```

Rollback a run when required:

```bash
loom rollback <run_id>
```

## Option C — web dashboard

Backend:

```bash
loom server --port 8000
```

Frontend:

```bash
cd web
npm install
npm run dev
```

Then open:

```text
http://localhost:3000
```

---

# CLI reference

| Command | Purpose |
|---|---|
| `loom version` | Display the Loom CLI version. |
| `loom init` | Initialize a repository and build repository context. |
| `loom issue` | Set the active engineering task. |
| `loom run` | Execute the agent TaskGraph. |
| `loom fix` | Initialize, set the issue, and execute in one command. |
| `loom trace <run_id>` | Inspect execution events, stages, and costs. |
| `loom rollback <run_id>` | Restore the pre-patch snapshot. |
| `loom bench` | Run controlled benchmark/ablation workflows. |
| `loom server` | Start the FastAPI backend. |

---

# Web dashboard

The dashboard provides a visual view of the agent execution lifecycle and run state.

Typical flow:

```text
Create run
   ↓
Monitor TaskGraph
   ↓
Inspect agent output
   ↓
Review verification evidence
   ↓
Inspect merge decision
   ↓
Approve / reject / rollback
```

---

# Production architecture

The repository contains a production-hardening path built around shared infrastructure and isolated workers.

```text
Client
  │
  ▼
FastAPI
  │
  ▼
Redis coordination
  │
  ├── rate limiting
  ├── queue/control state
  ├── run events
  └── worker heartbeats
  │
  ▼
Run Worker(s)
  │
  ▼
TaskGraph
  │
  ▼
Sandbox Worker
  │
  ├── PostgreSQL / records
  ├── evidence storage
  └── telemetry
```

The production-hardening work includes durable worker execution, checkpoint/resume infrastructure, retry classification, run budgets, worker health reporting, fail-closed production configuration, sandbox-worker separation, and backup/recovery tooling.

Treat this section as the target/implemented hardening architecture rather than a claim that every deployment concern is solved by the repository alone.

---

# Production configuration

Production deployments should explicitly configure security-sensitive settings such as:

```env
API_KEY=...
DASHBOARD_AUTH_TOKEN=...
ALLOWED_REPO_ROOTS=/var/repos
REDIS_URL=redis://...
LOOM_SANDBOX_WORKER_URL=http://sandbox-worker:8100
SANDBOX_WORKER_TOKEN=...
LOOM_BACKUP_ENCRYPTION_KEY=...
LOOM_BACKUP_S3_BUCKET=...
LOOM_MAX_RUN_COST_USD=...
LOOM_MAX_RUN_DURATION_SECONDS=...
LOOM_MAX_RUN_TOKENS=...
```

Production startup is intended to fail when required security configuration is missing.

Do not enable privileged token-administration functionality in production without the corresponding control-plane security model.

---

# Testing and quality gates

## Backend

```bash
pytest --timeout=60 --timeout_method=thread
mypy loom/ --ignore-missing-imports
ruff check loom/
pip-audit --skip-editable
```

## Frontend

From `web/`:

```bash
npm ci --legacy-peer-deps
npm audit --audit-level=high
npm run lint
npx tsc --noEmit
npm test
npm run build
```

## Container and Compose validation

```bash
docker build --pull -t loom-ci .
docker compose config --quiet
```

The repository's CI also includes secret scanning and a native CLI smoke test.

### Current test expectation

The test suite is substantial and covers business logic, orchestration, verification, memory, routing, sandbox policy, integrations, telemetry, SCIM, webhooks, and runtime hardening.

Coverage should be interpreted by **risk area**, not only by the global percentage. Production-critical worker, sandbox, distributed-runtime, backup, and API paths should receive the highest coverage priority.

---

# Backup and recovery

The repository includes operational backup/restore tooling supporting:

- SQLite backup handling
- PostgreSQL dump/restore paths
- encrypted archives
- SHA-256 integrity verification
- safe archive extraction
- evidence backup

Example:

```bash
python scripts/backup_restore.py create --dir ./backups
```

Restore:

```bash
python scripts/backup_restore.py restore ./backups/<backup>.enc --loom-home ./restored-loom
```

For real production use, pair this with off-host storage, retention policies, encryption-key management, scheduled backups, and tested restore procedures.

---

# Security model

Loom treats the repository and model-generated code as potentially untrusted.

Security mechanisms include:

- prompt-injection sanitization
- API authentication
- RBAC and entitlement enforcement
- production repository path restrictions
- request-size and rate-limit controls
- sensitive-path patch policies
- secret scanning in CI
- sandbox/resource controls
- evidence integrity verification
- rollback support
- encrypted/checksummed backup handling

Security features do **not** by themselves constitute SOC 2, GDPR, HIPAA, PCI DSS, or other compliance certification.

---

# Current limitations

Loom is an active engineering project. The following items still require deployment-level work or additional verification before making a blanket enterprise-production claim:

- real Firecracker/microVM Tier C execution
- full load/concurrency testing under realistic infrastructure
- complete managed Redis/PostgreSQL integration testing
- scheduled off-site backup and restore drills
- production deployment/canary/rollback drills
- deeper coverage for lower-level workers, browser verification, TUI, and some persistence paths

These limitations are documented intentionally so the README does not overstate the system's maturity.

---

# Project structure

```text
loom/
├── adapters/           # Model/provider adapters and routing
├── api/                # FastAPI API and webhooks
├── auth/               # Authentication and API tokens
├── business/           # RBAC, entitlements, usage, policy
├── cli/                # CLI, recovery, streaming, TUI
├── context/            # Context budgeting and sanitization
├── db/                 # Run and step persistence
├── infra/              # Distributed infrastructure helpers
├── integrations/       # GitHub/Slack/CI integrations
├── memory/             # Persistent memory and retrieval
├── orchestrator/       # Agents, TaskGraph, execution state
├── repo_intel/         # Repository mapping and analysis
├── runtime/            # Queues, workers, budgets, health, recovery
├── sandbox/            # Local/Docker/remote sandbox layers
├── scim/               # SCIM provisioning
├── telemetry/          # Cost and execution telemetry
└── verification/       # Build/test/security/evidence verification

web/                     # Next.js dashboard
tests/                   # Automated test suite
scripts/                 # Operational tooling
docs/                    # Architecture, deployment, runbooks, security
```

---

# Design principles

1. **Evidence over assertions** — successful model output is not proof.
2. **Fail closed around security boundaries** — dangerous fallbacks are rejected.
3. **Provider-independent orchestration** — models remain replaceable adapters.
4. **Recoverable execution** — checkpoints, retries, heartbeats, and rollback matter.
5. **Explicit policy** — sandbox tiers, quotas, budgets, merge rules, and risk controls are visible.
6. **Backward-compatible evolution** — infrastructure improvements should preserve the core TaskGraph and agent interfaces.

---

# Contributing

1. Create a feature branch.
2. Keep changes scoped and backward-compatible.
3. Add or update tests for behavioral changes.
4. Run the backend and frontend quality gates before opening a pull request.
5. Document security-sensitive or operational changes.

---

# License

MIT — see [LICENSE](LICENSE).
