# Comprehensive Prompt for Market-Differentiated Production Completion

**Role & Goal**:
You are an expert AI software engineer tasked with driving the "Loom" Agentic Coding Harness project to its 100% final, production-ready state. The core foundation (Phase 0) and Phase 1+ (API server, orchestrator, execution pipeline) are already completed. 

Your objective is not just to finish the code, but to **differentiate Loom in the market** by transforming it from a "fast patch generator" into an **auditable, trustworthy, and continuous infrastructure** for engineering teams. The focus is entirely on Verifiable Proof, Continuous Integration, and Solving Review Fatigue.

Please execute the following tasks systematically based on priority:

## 1. CI/CD Integration & GitHub Ecosystem (Top Priority)
Transform Loom from a reactive CLI tool into proactive infrastructure.
- **GitHub Action / CI Integration**: Create a GitHub Action that runs Loom on every PR. If verification passes, auto-approve the PR. If it fails, block the merge with the evidence bundle as the rejection reason.
- **PR Auto-Comment**: Automatically post the evidence bundle as a PR comment in GitHub so reviewers see the green test results, the 3-line summary (root cause, change, proof), and the cryptographic receipt without leaving the platform.
- **Pre-commit Hook / Watch Mode**: Implement `loom watch` to monitor for new issues, reproduce them, and proactively open PRs with verified patches.

## 2. Elevate Verifiable Proof (Web Dashboard & Export)
Make the SHA-256 cryptographic evidence chain the primary "Wow" feature.
- **Browser-Side Verification UI**: In the Next.js Web Dashboard, implement browser-side Web Crypto verification of backend seals. Display a highly visible "Green Checkmark" with a SHA-256 fingerprint for verified runs.
- **Compliance Export (PDF/JSON)**: Enable 1-click export of the full evidence chain to JSON or PDF for compliance reviews (SOC 2, ISO 27001) and post-mortems.

## 3. Team Memory & Learning Across Runs
Make Loom smarter over time by leveraging the existing 7-tier memory store.
- **Pattern Recognition**: Use the memory store to learn from past fixes. If the same bug class appears, surface the previous verified solution.
- **Team Knowledge Base**: Aggregate evidence bundles across an organization.
- **Model Performance Tracking**: Utilize the cost ledger to track and display which model (Claude, GPT-4o, etc.) performs best on the specific codebase.

## 4. Web Dashboard & Billing Completion
- **Next.js Dashboard**: Complete the missing UI views to support the features above (evidence verification, team memory, compliance exports). Ensure it flawlessly integrates with all 40+ backend FastAPI endpoints.
- **Stripe Billing Cutover (Phase 5)**: Integrate the Stripe `StripeBillingAdapter` (`loom/business/billing_provider.py`), webhooks, checkout, and portal sessions to fully commercialize the platform.

## 5. Production Deployment Gates Verification
Repository code must enforce and pass all target-environment deployment gates:
- **Database & Services**: Verify PostgreSQL and Redis are reachable, healthy, and sized correctly. Ensure migrations (`scripts/postgres_migrate.py`) apply cleanly.
- **Sandbox Isolation**: Validate that Tier C runs an isolated Firecracker worker (`scripts/e2e_firecracker_validation.sh`). Populate and verify `infra/firecracker/SHA256SUM`.
- **Backup & Load Testing**: Prove backup DR (`scripts/restore_drill.py`) and ensure real-world topology concurrency tests pass (`scripts/load_test.py`) with measured SLOs and verified rollback procedures.

**Execution Rules**:
- Prioritize trust and verification over speed. Loom's narrative is "Zero regressions. Proven."
- Do not bypass state machine guards or RBAC permissions (`loom/business/models.py`).
- Provide terminal outputs proving deployment gates pass.
- Deliver a final status report confirming Loom is ready for commercialization and enterprise deployment.
