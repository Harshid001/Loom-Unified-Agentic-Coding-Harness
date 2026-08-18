# Loom — Unified Agentic Coding Harness
## Product Requirements Document (PRD) — Hackathon MVP to Production SaaS

| | |
|---|---|
| **Document status** | Draft v1.0 |
| **Source challenge** | AE-01 — Unified Agentic Coding Harness |
| **Prepared** | August 10, 2026 |
| **Working product name** | *Loom* (weaves together model, memory, tools, and verification into one traceable thread) |

---

## 1. Executive Summary

Loom is a model-independent, terminal-first coding agent harness that takes a repository and an issue and carries it through the full engineering loop — onboarding, reproduction, planning, patching, testing, and rollback-ready delivery — while producing hard evidence (tests, traces, cost reports) instead of asking anyone to trust a model's self-reported confidence.

The central bet of the product is architectural, not model-specific: **the harness — its memory, context construction, task graph, sandboxing, and verification pipeline — is the product**, and the model behind it is a swappable component. That is also the commercial wedge: as frontier models commoditize, the durable value shifts to whoever builds the best surrounding system. Loom is designed from day one to be demoed as a hackathon entry, then hardened into a product that individual developers, engineering teams, and regulated enterprises can run daily.

This document extends the AE-01 brief with the additional product, business, architecture, and go-to-market decisions needed to take it from a judged demo to a deployed, revenue-generating system, and it favors free and open-source technology everywhere that doesn't compromise production quality.

---

## 2. Background & Problem Restatement

AE-01 asks for a production-minded coding agent that can take a repository, an issue, and a set of constraints, and produce a verified patch, an execution trace, test evidence, a cost/latency report, and a rollback-ready artifact — while proving, via controlled ablations, that the *harness* (not the underlying model) is responsible for the performance gain. The system must combine a model-agnostic adapter layer, deep repository intelligence, tiered and provenance-tracked memory, a dynamic context manager, a branching task graph with specialist sub-agents, sandboxed command execution, verification-first completion criteria, and full observability — evaluated primarily on Terminal-Bench, with SWE-bench, LiveCodeBench, and hidden tasks as complements.

In short: **it isn't enough to wrap a model in a CLI.** The differentiator has to survive a same-model, same-budget comparison against a baseline harness, and it has to hold up on real, messy repositories — not just curated benchmark tasks.

---

## 3. Goals & Non-Goals

**Goals**
- Deliver a working CLI harness that satisfies every AE-01 required capability and passes the minimum viable demonstration end to end.
- Prove, via ablation, that harness architecture (memory, retrieval, multi-agent structure, verification) produces a measurable, reproducible performance delta over a naive baseline at fixed model and budget.
- Ship a production-shaped system: something that could be installed by a real engineering team next week, not just judged once.
- Keep the default stack free/open-source so the product can run fully self-hosted with zero recurring license cost, while offering a hosted SaaS convenience layer as the monetized surface.

**Non-goals (explicitly out of scope for v1)**
- Fully autonomous production deployment (the harness proposes and verifies; humans approve anything touching prod infra, secrets, or irreversible external side effects).
- Being a general-purpose chat assistant or IDE autocomplete — Loom is scoped to issue-to-verified-patch workflows.
- Training or fine-tuning proprietary models — Loom is model-agnostic by design and should never require a specific vendor's model to function.
- Unrestricted host access — no SSH keys, browser sessions, or standing production credentials, per the AE-01 safety boundary.

---

## 4. Target Users & Personas

| Persona | Who they are | What they need from Loom |
|---|---|---|
| **Independent developer / OSS maintainer** | Solo dev maintaining one or more repos | Fast, low-cost issue triage and patch generation; free tier with bring-your-own API key |
| **Engineering team lead** | Leads a 5–20 person team on a polyglot codebase | Confidence the patch is *actually* verified before review; visibility into what the agent touched and why |
| **Platform / DevEx team** | Owns internal tooling for a larger org | Self-hostable, extensible harness they can wire into their own CI, ticketing, and repo intelligence |
| **Enterprise engineering org** | Regulated industry (finance, healthcare, defense-adjacent) | On-prem/air-gapped deployment, audit logs, RBAC, no data leaving their network, compliance posture |

---

## 5. Business Model & Go-to-Market

### 5.1 Market Landscape

Loom competes in the fast-moving agentic coding tool category alongside Claude Code, Cursor, GitHub Copilot Workspace, Cognition's Devin, Amp, OpenCode, and Codex CLI. Most of these are strong on model integration and editor UX; Loom's positioning is different:

| Dimension | Typical competitor | Loom |
|---|---|---|
| Model coupling | Often tuned around one frontier model | Model-agnostic adapter layer; swap models without touching the harness |
| Completion criteria | Model confidence / user acceptance | Verification-first: builds, tests, linters, static analysis, hidden evaluator tasks |
| Memory | Session-scoped or lightly persistent | Tiered memory with provenance and invalidation rules, inspectable and exportable |
| Deployment | Primarily hosted SaaS | Self-hosted CLI, hosted SaaS, and on-prem/air-gapped, from day one |
| Proof of value | Marketing benchmarks | Reproducible ablation studies the customer can rerun on their own repos |

### 5.2 Pricing & Packaging *(illustrative — to validate with design partners)*

| Tier | Audience | Price | Includes |
|---|---|---|---|
| **Free** | Individuals, OSS | $0 | Full CLI, local sandbox, bring-your-own model API key, community memory store (SQLite, local only) |
| **Pro** | Power individual users | ~$25/mo | Hosted memory sync, hosted trace viewer, priority model routing, usage dashboard |
| **Team** | 5–50 engineers | ~$40/seat/mo | Shared project memory, RBAC, GitHub/GitLab bot, Slack notifications, team cost budgets |
| **Enterprise** | Regulated orgs, large eng orgs | Custom | On-prem/air-gapped deploy, SSO/SAML, audit logging, dedicated support, custom SLA |

### 5.3 Revenue Streams
- **Seat/subscription revenue** (Pro, Team tiers).
- **Usage-based compute markup** for customers who don't bring their own model API key — Loom passes through model costs plus a margin, with hard budget caps to prevent bill shock.
- **Enterprise licensing & support contracts** (on-prem deployment, SLA-backed support, custom integrations).
- **Marketplace revenue share** on premium community-built verifiers, connectors, and repo-intelligence plugins.
- **Professional services** for harness tuning and onboarding on large/legacy monorepos.

### 5.4 Go-to-Market Phases
1. **Phase 0 — Hackathon demo:** unseen-repo demonstration, ablation results, judged deliverables.
2. **Phase 1 — Private beta:** 10–20 design-partner teams (OSS maintainers + one or two friendly engineering orgs), free usage in exchange for structured feedback and benchmark data.
3. **Phase 2 — Public self-serve launch:** Free/Pro/Team tiers, GitHub/GitLab marketplace listing, content marketing around the ablation methodology (the "prove your harness" angle is a strong technical-credibility hook).
4. **Phase 3 — Enterprise expansion:** on-prem packaging, compliance certifications, outbound sales motion into regulated industries.

---

## 6. Product Scope

### 6.1 MVP Scope (hackathon-required)
- Repository intake that builds an initial map and accepts a bounded issue or feature request.
- Issue reproduction with a recorded evidence item and an explicit task graph.
- A coding run that produces a patch, runs the declared verification suite, and recovers from at least one injected failure.
- A same-model, same-budget comparison run: baseline harness vs. Loom.
- A reviewer view explaining completion rationale, remaining uncertainty, and rollback steps.

### 6.2 Production Extension — Extra Features Beyond the Hackathon Brief

**Collaboration & workflow**
- Shared team workspaces with per-project memory and role-based access control.
- GitHub/GitLab bot: auto-triage incoming issues, open draft PRs, respond to review comments, re-run verification on push.
- Human-in-the-loop approval gates for anything touching production config, schema migrations, or external side effects.
- Slack/email notifications on long-running task completion or failure.

**Developer experience**
- VS Code and JetBrains extensions that surface the same trace viewer and task graph inline in the editor.
- Local-first offline mode using local model serving (Ollama/vLLM) for privacy-sensitive codebases with zero external API calls.
- Rollback/undo via git worktree snapshots at every checkpoint, one command to revert.

**Cost & model governance**
- Multi-model routing: cheap/local models handle mechanical sub-tasks (formatting, boilerplate, test scaffolding); frontier models are reserved for planning and hard reasoning steps.
- Per-team spend budgets, alerts, and hard caps.
- Cost/latency report broken down by task-graph node, not just total run.

**Governance & compliance**
- Full audit log of every tool call, file touched, and approval decision.
- On-prem / air-gapped deployment package (Helm chart + offline model serving) for regulated customers.
- Data residency controls and a SOC 2 Type II roadmap once enterprise demand justifies the investment.

**Quality & reliability**
- Nightly benchmark runs against Terminal-Bench/SWE-bench to catch quality regressions before they reach customers.
- Flaky-test detection that distinguishes real regressions from noisy test infrastructure, so verification failures are trustworthy.
- A plugin/tool marketplace so teams can contribute custom verifiers (security scanners, license checkers, perf regression gates) without forking the harness.

---

## 7. Functional Requirements

Each AE-01 capability is broken into concrete requirements. Bracketed items marked **[prod]** are production additions beyond the minimum hackathon bar.

### 7.1 Model-independent adapter layer
- Single internal interface (prompt in, structured tool-call/response out) that every model provider implements.
- Support for at least one hosted frontier provider and one locally-served open-weight model out of the box.
- Adapter swap requires zero changes to context construction, memory, planning, or verification code.
- **[prod]** Automatic per-task-graph-node model routing based on task complexity and configured cost policy.

### 7.2 Repository intelligence
- File map generation on intake (directory structure, language breakdown, build/test entry points).
- AST/symbol indexing via incremental, multi-language parsing.
- Import/call graph construction and test-to-source mapping so the harness knows which tests cover which code.
- Git history awareness (blame, recent churn, related past fixes) as a signal for planning.
- **[prod]** Cross-repo / monorepo dependency graph for organizations running service-oriented architectures.

### 7.3 Tiered memory
- Distinct tiers: working (session), task state, project conventions, episodic outcomes, reusable procedures, user preferences, verified evidence.
- Every memory item carries provenance (source, timestamp, confidence) and an invalidation rule (staleness window, code-change trigger, explicit expiry).
- Memory is inspectable, editable, exportable, and deletable by the user at the item level.
- **[prod]** Shared team memory with per-project scoping and RBAC-gated visibility.

### 7.4 Context manager
- Dynamic token budgeting per task-graph node with relevance scoring over retrieved context.
- Hierarchical summarization so large repos degrade gracefully instead of truncating arbitrarily.
- Stale-context detection that forces re-retrieval after code changes mid-run.
- Prompt-injection resistance: content pulled from the repository or tool output is treated as untrusted data, never as instructions.
- **[prod]** Context diffing in the trace viewer so a reviewer can see exactly what changed between planning and execution context.

### 7.5 Task graph & orchestration
- DAG-based plan with sequential and parallel branches.
- Bounded specialist sub-agents (e.g., reproduction agent, patch agent, test agent, review agent) with independent review checkpoints.
- Early termination and dynamic replanning when a branch fails or new information invalidates the plan.
- **[prod]** Durable, checkpointed execution so a multi-hour task graph survives process restarts and can be paused/resumed by a human.

### 7.6 Sandboxed command execution
- Scoped filesystem access limited to the working repository copy.
- Explicit, default-deny network policy with an allow-list for declared package registries.
- CPU/memory/time resource limits per command; automatic termination on breach.
- Secret isolation — no ambient credentials inside the sandbox unless explicitly scoped and time-boxed.
- Filesystem snapshots before/after each risky operation, with an approval gate before anything irreversible.
- Emergency kill switch reachable from the CLI and the dashboard.
- **[prod]** Multiple isolation backends (lightweight containers for trusted local dev, microVMs for hosted/multi-tenant execution).

### 7.7 Verification-first completion
- A task is only "done" when the declared verification suite (build, tests, linters, type checks, static analysis) passes — never on model self-assessment alone.
- Regression tests run against the pre-change baseline to catch newly broken behavior.
- Hidden evaluator tasks (organizer- or customer-provided) as an additional, harness-blind check.
- **[prod]** Flaky-test classification so a failing verification step is reported as "real regression" vs. "known-flaky" with supporting historical data.

### 7.8 Observability
- Full trace of plan revisions, retrieved context, tool calls, files touched, tests run, failures, and recovery actions.
- Token and cost usage broken down per node, per model, per run.
- Final evidence bundle (patch, test output, trace, cost report) exported as a single rollback-ready artifact.
- Chain-of-thought is never exposed — only the structured plan, actions, and evidence.
- **[prod]** Web-based trace viewer with shareable links for code review, plus Prometheus/Grafana dashboards for team-level operational visibility.

---

## 8. System Architecture

```
                         ┌──────────────────────────┐
                         │        Loom CLI /         │
                         │     Web Dashboard (UI)     │
                         └─────────────┬─────────────┘
                                       │  gRPC / REST
                         ┌─────────────▼─────────────┐
                         │      Control Plane          │
                         │  Orchestrator + Task Graph   │
                         │  (durable execution engine)  │
                         └──┬──────────┬──────────┬────┘
             ┌──────────────┘          │          └──────────────┐
             ▼                         ▼                         ▼
  ┌────────────────────┐   ┌────────────────────┐   ┌────────────────────┐
  │ Model Adapter Layer │   │  Context Manager    │   │  Repo Intelligence  │
  │ (provider-agnostic) │   │ (retrieval, budget,  │   │ (AST/symbol index,  │
  │                      │   │  summarization)      │   │  call graph, git)   │
  └──────────┬──────────┘   └──────────┬──────────┘   └──────────┬──────────┘
             │                         │                          │
             └────────────┬────────────┴──────────────┬───────────┘
                           ▼                           ▼
              ┌────────────────────┐        ┌────────────────────────┐
              │  Tiered Memory      │        │ Sandboxed Execution      │
              │ (Postgres+pgvector, │        │ (microVM/container pool, │
              │  Redis working set) │        │  scoped FS/network)      │
              └──────────┬──────────┘        └────────────┬────────────┘
                          │                                │
                          ▼                                ▼
              ┌────────────────────────────────────────────────────┐
              │         Verification & Evidence Pipeline             │
              │ builds · tests · linters · static analysis · hidden  │
              │ tasks → evidence bundle + rollback-ready artifact     │
              └───────────────────────┬────────────────────────────┘
                                      ▼
                        ┌────────────────────────────┐
                        │   Observability & Benchmark  │
                        │  (OTel traces, Prometheus,    │
                        │   Terminal-Bench/SWE-bench     │
                        │   runner, ablation harness)    │
                        └────────────────────────────┘
```

**Planes, at a glance**
- **Control plane** — the orchestrator, task graph engine, and API surface. Stateless where possible; durable state lives in Postgres.
- **Execution plane** — sandboxed command execution, isolated per task, no shared state between runs.
- **Data plane** — tiered memory, repo intelligence indices, and the evidence/observability store.

---

## 9. Technology Stack

Chosen to be production-grade while defaulting to free/open-source components everywhere that doesn't sacrifice quality. Hosted/paid options are noted only where open-source alternatives would meaningfully compromise the product.

| Layer | Recommended technology | Why |
|---|---|---|
| CLI & orchestrator core | **Go** | Single cross-platform static binary, strong concurrency (goroutines), mature CLI ecosystem (Cobra, Viper), easy to operate |
| Durable task-graph execution | **Temporal** (open source) | Battle-tested durable workflow engine — checkpoints, retries, pause/resume for multi-hour agent runs |
| Repository parsing / symbol index | **Tree-sitter** + **ripgrep** + **scip/ctags** | Fast, incremental, multi-language parsing; widely adopted (GitHub, Neovim); all open source |
| Sandboxed execution | **gVisor** (default) / **Firecracker microVMs** (multi-tenant hosted) | Strong isolation with low overhead; both open source, both battle-tested at scale (Google, AWS) |
| Structured + vector memory | **PostgreSQL** + **pgvector** | One database for relational task/provenance state and embeddings — avoids running a second specialized vector DB |
| Working memory / cache / queue | **Redis** or **NATS** | Lightweight, open source, low-latency session state and inter-service messaging |
| Local-only / offline mode | **SQLite** | Zero-server single-user memory store for the free/local CLI experience |
| Model adapter layer | **LiteLLM** (open source) + native SDKs | Unified interface across hosted providers and locally served models |
| Local/offline model serving | **Ollama** / **vLLM** | Free, self-hosted inference for air-gapped or cost-sensitive deployments |
| Static analysis / linters | Per-language OSS tools (ESLint, Ruff/Pyright, golangci-lint, Clippy) | Reuse the ecosystem's best tools rather than reinventing them |
| Observability | **OpenTelemetry** → **Prometheus** + **Grafana** + **Tempo/Jaeger** + **Loki** | Full open-source "LGTM"-style stack, vendor-neutral instrumentation |
| Web dashboard | **Next.js/React**, **TypeScript**, **Tailwind CSS**, **shadcn/ui** | Fast to build, widely known, free component ecosystem |
| Auth / SSO | **Ory** or **Keycloak** (open source) | Enterprise SSO/SAML without a proprietary IdP dependency |
| Secrets management | **HashiCorp Vault** (open source core) | Scoped, time-boxed secret issuance into sandboxes |
| Infra as code | **Terraform** (open source core) | Reproducible provisioning across cloud or on-prem |
| Container/VM orchestration | **Kubernetes** + **containerd**/**Kata Containers** | Standard, portable, works the same on cloud or on-prem |
| CI/CD | **GitHub Actions** (or self-hosted **Gitea + Woodpecker CI** for a fully free stack) | Free for open-source use; self-hosted option removes recurring cost entirely |
| Usage metering / billing | **OpenMeter** (open source) + Stripe | Open-source metering with a pragmatic, industry-standard billing integration |

---

## 10. Data & Memory Model

Each memory item is stored with the same core shape regardless of tier, so provenance and invalidation logic stays uniform:

| Field | Purpose |
|---|---|
| `id` | Unique identifier |
| `tier` | working / task_state / project_conventions / episodic / procedure / user_preference / verified_evidence |
| `content` | The stored fact, summary, or procedure |
| `embedding` | Vector representation (pgvector) for semantic retrieval |
| `source` | Where it came from — file, run ID, user statement, tool output |
| `confidence` | Confidence score, especially for episodic/inferred items |
| `created_at` / `last_used_at` | For recency scoring |
| `invalidation_rule` | Explicit expiry, code-change trigger, or manual invalidation |
| `scope` | Personal / project / team, for RBAC-gated visibility |

Retrieval combines vector similarity with structural signals from repo intelligence (e.g., "boost memory items tied to files in the current call graph") rather than relying on embeddings alone.

---

## 11. Security, Sandboxing & Threat Model

Per the AE-01 safety boundary, Loom **never** receives unrestricted host credentials, private files outside the working repo, SSH keys, browser sessions, or standing production deployment authority.

| Threat | Mitigation |
|---|---|
| Prompt injection via repository content or tool output | All external content is treated as untrusted data, never as instructions; the model's tool-call surface is the only path to action |
| Malicious or compromised dependency fetched mid-run | Network allow-list restricted to declared package registries; dependency install steps run inside the sandbox, not the control plane |
| Credential exfiltration | No ambient secrets in the sandbox; secrets are scoped and time-boxed via Vault, injected only for the specific step that needs them |
| Runaway resource usage | Hard CPU/memory/time limits per command, with automatic termination and an emergency kill switch |
| Irreversible action taken without review | Filesystem snapshots before risky operations; explicit human approval gate before anything irreversible |
| Benchmark gaming (leaked tests, hidden-task inspection) | Hidden evaluator tasks are never exposed to the harness's retrieval or memory layers; verification suite is declared up front, not discovered |
| Multi-tenant isolation failure (hosted SaaS) | microVM-level isolation (Firecracker) per tenant run, not just container-level |

---

## 12. API & CLI Design

**CLI (illustrative)**
```
loom init                     # intake a repo, build initial map
loom issue "fix: null pointer in checkout flow"
loom run                      # execute the current task graph
loom trace <run-id>           # inspect plan, tool calls, evidence
loom rollback <run-id>        # revert to pre-run snapshot
loom bench --suite terminal-bench --baseline
```

**Team/enterprise API surface (illustrative)**
```
POST /v1/runs                 # start a new harness run
GET  /v1/runs/{id}/trace      # structured trace + evidence bundle
GET  /v1/runs/{id}/cost       # cost/latency report
POST /v1/memory/export        # export a project's memory tier
POST /v1/policy/budget        # set a team spend cap
```

---

## 13. Deployment & Infrastructure

- **Local mode (free tier):** single binary, SQLite memory, Docker/gVisor sandbox, bring-your-own model API key or local Ollama model. No server dependency.
- **Hosted SaaS (Pro/Team):** Kubernetes-based control plane, Postgres+pgvector, Redis, Temporal, per-run Firecracker microVMs for execution, autoscaled by queue depth.
- **On-prem/air-gapped (Enterprise):** Helm chart deploying the full stack inside the customer's network, with vLLM/Ollama for fully offline model serving where required.
- **CI/CD:** GitHub Actions builds multi-arch CLI binaries and container images on every merge, runs the full verification and benchmark suite, and publishes Helm chart releases on tagged versions.

---

## 14. Observability, Evaluation & Benchmarking

- **Primary benchmark:** Terminal-Bench. **Complements:** SWE-bench Verified/Lite, LiveCodeBench, internal repository-understanding tasks, and organizer/customer-provided hidden issues.
- **Tracked metrics:** pass rate, hidden-test pass rate, cost per successful task, token usage, tool-call failure rate, recovery rate, stale-context rate, human interventions required, and safety-policy violations.
- **Ablation matrix (same model, same budget, every time):**

| Ablation | Compares |
|---|---|
| Memory on vs. off | Value of the tiered memory system |
| Structural retrieval on vs. off | Value of AST/call-graph-aware context |
| Single-agent vs. multi-agent | Value of the task-graph/specialist structure |
| Cold vs. warm memory | Value of accumulated project knowledge over time |
| Baseline harness vs. Loom | The headline number — same model, different harness |

Nightly benchmark runs feed a regression dashboard (Grafana) so quality drift is caught before it reaches customers — a production discipline the hackathon demo doesn't strictly require, but that the business depends on.

---

## 15. Non-Functional Requirements

- **Performance:** a typical single-issue run on a mid-sized repo should complete verification within a target latency band (to be tuned per benchmark data) without requiring manual context pruning.
- **Scalability:** hosted control plane must support many concurrent isolated runs per team without cross-tenant interference.
- **Reliability:** durable task-graph execution must survive process restarts; SaaS tiers target a published uptime SLA once out of beta.
- **Portability:** the same core binary and container images must run identically in local, cloud, and air-gapped environments.
- **Data residency:** enterprise deployments must support keeping all repository and memory data inside the customer's network boundary.

---

## 16. Roadmap & Milestones

| Phase | Focus | Illustrative timeframe |
|---|---|---|
| 0 — Hackathon demo | MVP scope, ablation proof, unseen-repo demo | Weeks 0–4 |
| 1 — Alpha | Harden sandboxing, add durable task graph (Temporal), local mode polish | Weeks 4–10 |
| 2 — Private beta | Design partners, GitHub/GitLab bot, hosted trace viewer | Months 3–5 |
| 3 — Public launch | Free/Pro/Team self-serve, billing, marketplace v0 | Months 5–8 |
| 4 — Enterprise | On-prem package, SSO, audit logging, compliance roadmap | Months 8–14 |

---

## 17. Success Metrics / KPIs

**Product:** activation rate (first verified patch within N minutes of intake), task completion rate, time-to-first-verified-patch, weekly active repositories.
**Business:** MRR, seat expansion within existing teams, net revenue retention, CAC/LTV once paid acquisition begins.
**Technical:** benchmark pass-rate trend across releases, cost-per-successful-task trend, recovery rate from injected failures.

---

## 18. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Harness gains don't hold up outside curated benchmarks | Continuous nightly benchmarking on real, messy internal and partner repos, not just Terminal-Bench/SWE-bench |
| Model provider pricing/availability shifts | Model-agnostic adapter layer and multi-model routing keep the business insulated from any single vendor |
| Sandbox escape or isolation failure | Defense in depth — microVM isolation, network allow-lists, no ambient credentials, regular third-party security review |
| Enterprise sales cycle length outpaces self-serve revenue | Keep the free/self-hosted tier genuinely useful so bottom-up adoption seeds enterprise conversations |
| Cost overruns from usage-based tier | Hard per-team budgets and alerts, BYO-key option always available |

---

## 19. Illustrative Infra Cost Notes

At beta scale, the largest variable cost is model API usage, which is why usage-based pricing defaults to pass-through-plus-margin, with a free BYO-key path for cost-sensitive users. On the infrastructure side, every core component chosen above (Postgres, Redis, Temporal, Kubernetes, gVisor/Firecracker, the OpenTelemetry/Prometheus/Grafana stack, Terraform) has a genuinely free, self-hostable path, so a design-partner or small-team deployment can run at near-zero license cost — the only recurring costs are compute/hosting and model API usage, both of which scale with actual usage rather than being fixed overhead.

---

## 20. Requirement Traceability Matrix

| AE-01 requirement | Addressed in |
|---|---|
| 11. Model-independent adapter layer | §7.1, §9 |
| 12. Repository intelligence | §7.2, §8 |
| 13. Tiered memory with provenance | §7.3, §10 |
| 14. Context manager | §7.4 |
| 15. Task graph with specialist agents | §7.5, §8 |
| 16. Sandboxed command execution | §7.6, §11 |
| 17. Verification-first completion | §7.7 |
| 18. Observability | §7.8, §14 |
| 19–23. Minimum viable demonstration | §6.1 |
| 24–26. Evaluation and benchmarks | §14 |
| 27–28. Hard-mode extensions | §6.2, §16 (roadmap) |
| Safety boundary | §3 (non-goals), §11 |
| 29–33. Expected deliverables | §6.1, §12, §13 |

---

## 21. Open Questions / Next Steps

- Which repositories will serve as the private-beta design-partner set, and what's the target ablation delta to headline in the hackathon demo?
- Should the free tier ship with a local open-weight model by default (fully $0 to try) or require a BYO API key from day one?
- What compliance certification (SOC 2 vs. ISO 27001) should be prioritized first based on the earliest enterprise conversations?
