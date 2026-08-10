# Loom Agentic Harness — Production Deployment Guide

This document outlines deployment configurations, containerization, environment variables, security policies, and monitoring setups for Loom.

---

## 1. Quick Start with Docker Compose

To deploy both the **Python Harness Backend API** and the **Next.js Web Dashboard** via Docker Compose:

```bash
# Clone and navigate to workspace
cd "Unified agentic coding harness"

# Build and start services in detached mode
docker-compose up --build -d

# Check running container statuses
docker-compose ps
```

Services exposed:
- **Backend API**: `http://localhost:8000`
- **OpenAPI / Swagger UI**: `http://localhost:8000/docs`
- **Web Dashboard**: `http://localhost:3000`

---

## 1.5 Docker Alternatives (Daemonless / Native Deployment)

If Docker Desktop is not available, use one of these alternatives:

### Alternative A: PM2 Process Manager (Native Python + Node)
```bash
npm install -g pm2
pm2 start "loom server --port 8000" --name loom-api
pm2 start "npm run start" --cwd ./web --name loom-web
pm2 save
```

### Alternative B: Podman / Podman-Compose (Drop-in Daemonless Replacement)
```bash
podman-compose up --build -d
```

---

## 2. Environment Variable Configuration

Create a `.env` file in the root directory (refer to [.env.example](file:///d:/NewVolumeE/Unified%20agentic%20coding%20harness/.env.example)):

| Variable Name | Default | Description |
| :--- | :--- | :--- |
| `API_KEY` | *(Required)* | Secret key for securing API endpoints via `X-API-Key` header |
| `DASHBOARD_AUTH_TOKEN` | *(Required in Prod)* | Token for securing Next.js Web BFF endpoints (fails closed if missing in non-dev envs) |
| `ALLOWED_REPO_ROOTS` | *(Empty / All)* | Comma-separated list of allowed root directories for `repo_path` execution |
| `ALLOWED_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000` | Comma-separated CORS allowed origin origins |
| `RATE_LIMIT_PER_MINUTE` | `60` | Max API requests per minute per IP address |
| `MODEL_DEFAULT` | `gpt-4o` | Default LLM model identifier for agent routing |
| `LOOM_DB_PATH` | `~/.loom/memory.db` | Persistent SQLite database file path |
| `ANTHROPIC_API_KEY` | *(Empty)* | Anthropic LLM API Key |
| `OPENAI_API_KEY` | *(Empty)* | OpenAI LLM API Key |

---

## 3. Health & Monitoring Probes

Loom provides Kubernetes-style liveness and readiness endpoints under `/api/v1/health/`:

- **Liveness Probe**: `GET /api/v1/health/liveness`
  - Returns `200 OK` with `{"status": "alive"}`
- **Readiness Probe**: `GET /api/v1/health/readiness`
  - Validates SQLite database connectivity and filesystem access. Returns `200 OK` when healthy or `503 Service Unavailable` if database access fails.

---

## 4. Manual Backend Server Startup

To run the backend API server directly using Python:

```bash
pip install -e .
loom server --host 0.0.0.0 --port 8000
```
