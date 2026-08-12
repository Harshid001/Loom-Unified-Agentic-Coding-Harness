# Loom — Agentic Coding Harness Development Guide

## Quick Start

```bash
# Install dependencies
pip install -e ".[dev]"

# Run all tests
python -m pytest tests/ -v

# Run specific test files
python -m pytest tests/test_orchestrator.py tests/test_business.py -v

# Run with coverage
python -m pytest tests/ -v --cov=loom --cov-report=term-missing

# Lint
ruff check loom/ tests/

# Type check
mypy loom/
```

## Architecture Overview

```
loom/
├── adapters/       # Model router, LLM adapter (LiteLLM-based)
├── api/            # FastAPI server, webhooks
├── auth/           # API token management
├── business/       # Business logic: entitlements, billing, RBAC, audit, rollup
├── cli/            # CLI + TUI, plugins, recovery
├── context/        # Context budget manager, prompt sanitizer
├── db/             # Records store (SQLite for Solo, Postgres for Team+)
├── integrations/   # CI bot (GitHub/GitLab), Slack
├── memory/         # 7-tier memory store
├── orchestrator/   # DAG execution, state machine, agents
│   └── agents/     # Onboarding, Reproduction, Planner, Patcher, Verifier, Reviewer
├── repo_intel/     # Tree-sitter parser, call graph, git history, repo mapper
├── sandbox/        # Tier A (worktree), Tier B (container), Tier C (microVM)
├── scim/           # SCIM provisioning
├── telemetry/      # Cost tracker, tracer, ablation
└── verification/   # Evidence bundle, verification runner, browser runner
tests/              # Mirrors loom/ structure
web/                # Next.js dashboard (TypeScript)
docs/               # Architecture, business logic, deployment docs
```

## Key Conventions

- **Language:** Python 3.10+, type-hinted with Pydantic models
- **Testing:** pytest with asyncio auto mode, FastAPI TestClient
- **Linting:** ruff (line-length 120, E/F/W/I rules, ignore E501)
- **Model layer:** All domain types in `loom/business/models.py` using Pydantic BaseModel
- **Non-serializable objects:** Store as `shared_data["__key"]` (double underscore prefix) — stripped by checkpoint serializer
- **State machine:** `RunStatus` enum in `task_graph.py` drives DAG transitions. Guards enforce preconditions (e.g., onboarding must produce repo_map before reproduction)
- **Entitlements:** `EntitlementService.check(org_id, feature_key)` — enforced server-side, never UI-only
- **Usage ledger:** Append-only, idempotency key = `SHA256(run_id|step_id|attempt_number|input_context_hash)`
- **Evidence bundles:** Hash-chained (SHA256), tamper-evident, exportable but immutable

## Critical Spec References

- **Business logic spec:** `docs/business_logic.md` — the source of truth for all decision rules
- **Architecture:** `docs/architecture.md`
- **Runbook:** `docs/runbook.md`

## Phase 0 (Business Logic Foundation) — Complete

Entitlement service, usage ledger + metering, RBAC scaffolding all implemented in `loom/business/`.

## Phase 1+ Status

- **Model router** with weighted scoring, fallback cascade, consensus verification: ✓
- **Context budget manager** with TF-IDF, graph proximity, bug density: ✓
- **Sandbox tier selection** with egress enforcement: ✓
- **Verification-first pipeline** with decision matrix: ✓
- **DAG orchestrator** with state machine guards: ✓
- **Evidence bundling** with hash chains: ✓
- **Cost tracking** with per-step model attribution: ✓
- **API server** with 40+ endpoints, RBAC, security headers: ✓
- **Web dashboard** (Next.js): partial
- **SSO/SCIM** (Enterprise): implemented with unit & integration test coverage: ✓
- **Stripe billing cutover** (Phase 5): not started