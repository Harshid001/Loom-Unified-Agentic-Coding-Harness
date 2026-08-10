# Loom — Unified Agentic Coding Harness 🧶

> **Enterprise-Grade, Model-Independent Autonomous Coding Agent Harness**  
> Takes any repository and issue description through the complete engineering loop — onboarding, reproduction, planning, patching, build/test verification, evidence bundling, and instant rollback.

---

## 🌟 Key Highlights

- **Model-Independent Architecture**: Seamlessly route sub-agent tasks across Anthropic (Claude 3.5 Sonnet), OpenAI (GPT-4o), Google Gemini, Ollama, or local LLM endpoints.
- **Verification-First Execution**: Requires empirical, verifiable proof (passing test runs and clean build logs) before declaring success.
- **Sandboxed Execution & Instant Rollback**: Isolated execution environments using Git worktree process sandboxes with 1-click snapshot restoration.
- **7-Tiered Memory System with Provenance**: Persistent SQLite (WAL mode) / PostgreSQL store tracking project conventions, architectural decisions, and invalidation rules.
- **Dynamic Context Budgeting & Security**: AST symbol relevance ranking, prompt injection sanitization (`PromptSanitizer`), and model token window budgeting.
- **Visual Web Dashboard & Terminal CLI**: Unified experience with a Next.js (App Router) interactive DAG trace viewer and a terminal-first Typer CLI.
- **Enterprise Observability**: Native Prometheus metrics (`/metrics`), OpenTelemetry tracing, cost tracking reports, and controlled ablation benchmarking.

---

## 📐 System Architecture

```text
                                  +-----------------------+
                                  |    User Request /     |
                                  |  Web Dashboard / CLI  |
                                  +-----------+-----------+
                                              |
                                              v
                                  +-----------------------+
                                  |     Model Router      |
                                  | (Claude / GPT / Local)|
                                  +-----------+-----------+
                                              |
                                              v
+-----------------------------------------------------------------------------------+
|                           DAG Task Graph Execution Engine                         |
|                                                                                   |
|  [Onboarding Agent] -> [Reproduction Agent] -> [Patcher Agent] -> [Verifier Agent] |
|         |                     |                     |                  |          |
|         v                     v                     v                  v          |
|  Repo Mapper / AST     Reproduction Test      Code Patch      Verification Bundle |
+-----------------------------------------------------------------------------------+
                                              |
                                              v
                                  +-----------------------+
                                  | Evidence Review Agent |
                                  |  (Final Verification) |
                                  +-----------+-----------+
                                              |
                                              v
                                  +-----------------------+
                                  | Local Sandbox & Git   |
                                  | Snapshot Rollback Store|
                                  +-----------------------+
```

---

## 🚀 Quick Start Guide

### Prerequisites
- **Python**: `>= 3.10`
- **Node.js**: `>= 20.0` (for Web Dashboard)

---

### 1. Direct Terminal Installation (1 Command)

Install Loom directly from GitHub into any terminal without cloning manually:

```bash
pip install git+https://github.com/Harshid001/Loom-Unified-Agentic-Coding-Harness.git
```

Or install locally from a cloned repository:

```bash
git clone https://github.com/Harshid001/Loom-Unified-Agentic-Coding-Harness.git
cd Loom-Unified-Agentic-Coding-Harness
pip install -e .
```

---

### 2. Environment Configuration

Copy `.env.example` to `.env` and set your API keys:

```bash
cp .env.example .env
```

Example `.env` configuration:
```env
API_KEY=your-secret-backend-api-key
DASHBOARD_AUTH_TOKEN=your-web-dashboard-auth-token
MODEL_DEFAULT=claude-3-5-sonnet-20241022
ANTHROPIC_API_KEY=sk-ant-api03-...
OPENAI_API_KEY=sk-proj-...
```

---

## 💡 Running Loom on Any Project

Loom supports three flexible execution modes for any target codebase on your machine.

### Method A: Single-Command Execution (`loom fix`) — *Recommended*

Navigate to **any project directory** on your system and run:

```bash
# Navigate to target codebase
cd /path/to/your-target-project

# Run Loom harness in 1 command (Offline Mock Mode)
loom fix "Fix calculation error in total_price calculation"

# Run with live LLM (e.g. Claude 3.5 Sonnet)
loom fix "Fix calculation error in total_price calculation" --no-mock --model claude-3-5-sonnet-20241022
```

---

### Method B: Step-by-Step CLI Execution

```bash
# 1. Intake and map the repository
loom init --path /path/to/your-target-project

# 2. Set the active issue
loom issue "Add validation for duplicate email addresses on registration"

# 3. Execute the DAG Task Graph
loom run --no-mock --model gpt-4o

# 4. View execution trace & DAG events
loom trace <run_id>

# 5. Rollback changes if needed
loom rollback <run_id>
```

---

### Method C: Visual Web Dashboard

1. **Launch the FastAPI Server**:
   ```bash
   loom server --port 8000
   ```

2. **Launch the Next.js Dashboard**:
   ```bash
   cd web
   npm run dev
   ```

3. **Open Dashboard**: Navigate to [http://localhost:3000](http://localhost:3000), click **"Start Execution Run"**, enter your target project path and issue description!

---

## ⚡ Native Process Deployment (No Docker Required)

Loom runs 100% natively on Python and Node.js without requiring Docker or container runtime engines.

### Method 1: PM2 Ecosystem (One-Command Startup)
Launch both backend FastAPI server and Next.js Web Dashboard in background processes using the provided `ecosystem.config.js`:

```bash
# 1. Install PM2 globally
npm install -g pm2

# 2. Launch all Loom services in 1 command
pm2 start ecosystem.config.js

# 3. Check status & logs
pm2 status
pm2 logs
```

---

### Method 2: Direct Terminal Startup
Run backend API and web frontend directly in separate terminals:

```bash
# Terminal 1: Launch FastAPI Backend Server
loom server --port 8000

# Terminal 2: Launch Next.js Web Dashboard
cd web
npm run dev
```

---

## 🛠️ CLI Reference

| Command | Usage | Description |
|---|---|---|
| `loom version` | `loom version` | Display Loom CLI version. |
| `loom init` | `loom init [--path <dir>]` | Intake codebase, build AST symbol index and memory store. |
| `loom issue` | `loom issue "<prompt>" [--path <dir>]` | Set active issue description for execution. |
| `loom run` | `loom run [--mock / --no-mock] [--model <name>] [--api-key <key>] [--api-base <url>]` | Execute the DAG task graph through all specialist agents. |
| `loom fix` | `loom fix "<prompt>" [--mock / --no-mock] [--model <name>] [--api-key <key>] [--api-base <url>]` | Single-command shortcut to intake, set issue, and run harness. |
| `loom trace` | `loom trace <run_id>` | Display interactive tree view of execution trace events and costs. |
| `loom rollback` | `loom rollback <run_id>` | Restore target workspace to pre-patch snapshot state. |
| `loom bench` | `loom bench` | Execute controlled same-model ablation matrix benchmarks. |
| `loom server` | `loom server [--port 8000]` | Start Uvicorn FastAPI backend server. |

---

## 🧪 Testing & Code Quality Verification

Loom enforces strict quality and security standards across Python backend and Next.js frontend codebases:

```bash
# Python Backend Verification
pytest                  # Unit & integration tests with coverage report (34 tests)
mypy loom               # Static type checker (0 errors)
ruff check loom         # Code linter (0 issues)

# Next.js Frontend Verification (in ./web)
npx tsc --noEmit        # TypeScript typecheck (0 errors)
npm test                # Vitest component & auth tests (8 tests)
npm run lint            # ESLint rules check
npm run build           # Production build verification
```

---

## 🛡️ Security & OWASP Protection

- **Prompt Injection Defense**: Sanitizes raw repository file inputs via `PromptSanitizer`, stripping instructions like `ignore previous instructions`, `system:`, or `<|im_start|>`.
- **Constant-Time Authentication**: Authenticates backend API requests via `secrets.compare_digest` against `X-API-Key`.
- **Hardened HTTP Headers**: Sets `X-Content-Type-Options`, `X-Frame-Options`, `X-XSS-Protection`, `Content-Security-Policy`, and `Strict-Transport-Security`.
- **Bounded Request Limits**: Enforces 10MB payload size limits and sliding-window IP rate limiting.

---

## 📜 License

This project is licensed under the MIT License — see the [LICENSE](file:///d:/NewVolumeE/Unified%20agentic%20coding%20harness/LICENSE) file for details.
