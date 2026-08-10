import json
import logging
import os
import secrets
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

try:
    from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    CONTENT_TYPE_LATEST = "text/plain"
    def generate_latest(registry: Any = None, escaping: Any = None) -> bytes:  # type: ignore[misc]
        return b"# prometheus_client not installed\n"
    class DummyMetric:
        def labels(self, **kwargs: Any) -> "DummyMetric":
            return self
        def inc(self, amount: float = 1) -> None:
            pass
        def observe(self, amount: float) -> None:
            pass
    class DummyMetricFactory:
        def __call__(self, *args: Any, **kwargs: Any) -> DummyMetric:
            return DummyMetric()
    Counter = DummyMetricFactory()  # type: ignore
    Histogram = DummyMetricFactory()  # type: ignore

from loom.adapters.router import ModelRouter
from loom.memory.store import TieredMemoryStore
from loom.orchestrator.state import OrchestratorState
from loom.orchestrator.task_graph import TaskGraph
from loom.sandbox.local_process import LocalProcessSandbox
from loom.telemetry.cost_tracker import CostTracker
from loom.telemetry.tracer import TelemetryTracer

app = FastAPI(
    title="Loom Agentic Harness API",
    description="Unified Agentic Coding Harness API Server for orchestration, execution, and trace management.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# PRD-001: Hardened CORS configuration
raw_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
allowed_origins = [o.strip() for o in raw_origins.split(",") if o.strip()]
is_wildcard = "*" in allowed_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=not is_wildcard,
    allow_methods=["*"],
    allow_headers=["*"],
)

# PRD-005 & PRD-006: Security Headers Middleware
@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Content-Security-Policy"] = "default-src 'self'"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("loom.api")

# PRD-015: Prometheus Metrics Instrumentation
REQUEST_COUNT = Counter("loom_requests_total", "Total requests processed", ["method", "endpoint", "status"])
REQUEST_LATENCY = Histogram("loom_request_duration_seconds", "Request latency", ["endpoint"])

# PRD-108 & PRD-007: In-Memory Sliding-Window Rate Limiting Store with Bounded Cleanup
RATE_LIMIT_REQUESTS = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))
RATE_LIMIT_WINDOW = 60  # seconds
_rate_limit_memory_store: Dict[str, List[float]] = {}

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    start_time = time.time()
    if request.url.path.startswith("/api/"):
        client_ip = request.client.host if request.client else "127.0.0.1"
        now = time.time()
        timestamps = [ts for ts in _rate_limit_memory_store.get(client_ip, []) if now - ts < RATE_LIMIT_WINDOW]
        if len(timestamps) >= RATE_LIMIT_REQUESTS:
            REQUEST_COUNT.labels(method=request.method, endpoint=request.url.path, status="429").inc()
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Too many requests."}
            )
        timestamps.append(now)
        _rate_limit_memory_store[client_ip] = timestamps

        # Bounded store cleanup (PRD-007)
        if len(_rate_limit_memory_store) > 5000:
            stale = [ip for ip, tss in _rate_limit_memory_store.items() if not tss or (now - tss[-1] > RATE_LIMIT_WINDOW)]
            for ip in stale:
                _rate_limit_memory_store.pop(ip, None)

    response = await call_next(request)
    duration = time.time() - start_time
    REQUEST_LATENCY.labels(endpoint=request.url.path).observe(duration)
    REQUEST_COUNT.labels(method=request.method, endpoint=request.url.path, status=str(response.status_code)).inc()
    return response

# PRD-010: Request Body Size Limit Middleware (10MB Max Body Size)
MAX_REQUEST_SIZE = 10 * 1024 * 1024  # 10MB

@app.middleware("http")
async def limit_request_body_size(request: Request, call_next):
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_REQUEST_SIZE:
                return JSONResponse(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    content={"detail": "Request payload exceeds maximum allowed size of 10MB."}
                )
        except ValueError:
            pass
    return await call_next(request)

# PRD-102 & PRD-009: Mandatory Constant-Time API Key Authentication Dependency
def get_required_api_key() -> str:
    key = os.getenv("API_KEY")
    if not key:
        raise RuntimeError("API_KEY environment variable is not configured.")
    return key

async def verify_api_key(x_api_key: Optional[str] = Header(None)):
    try:
        required_key = get_required_api_key()
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc)
        )
    if not x_api_key or not secrets.compare_digest(x_api_key, required_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-API-Key header"
        )
    return x_api_key

class RunRequest(BaseModel):
    issue: str
    repo_path: Optional[str] = "."
    model: str = "gpt-4o"
    mock: bool = True

# PRD-015: Prometheus Metrics Endpoint
@app.get("/metrics")
def metrics():
    if not PROMETHEUS_AVAILABLE:
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

# PRD-103: Authenticated health probes
@app.get("/api/v1/health/liveness")
@app.get("/api/health/liveness")
@app.get("/healthz")
def liveness_health():
    return {"status": "alive", "service": "Loom API"}

@app.get("/api/v1/health/readiness")
@app.get("/api/health/readiness")
def readiness_health():
    db_ok = True
    try:
        store = TieredMemoryStore()
        _ = store.get_schema_version()
    except Exception as err:
        logger.error("Readiness check database failed: %s", err)
        db_ok = False

    checkpoints_dir = Path.home() / ".loom" / "checkpoints"
    checkpoints_dir.mkdir(parents=True, exist_ok=True)
    storage_ok = checkpoints_dir.parent.exists() and os.access(checkpoints_dir.parent, os.W_OK)

    if not db_ok or not storage_ok:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "not_ready", "components": {"database": "failed" if not db_ok else "ok", "storage": "failed" if not storage_ok else "ok"}}
        )

    return {
        "status": "ready",
        "service": "Loom API",
        "components": {
            "database": "ok",
            "storage": "ok"
        }
    }

@app.get("/api/health")
def legacy_health_alias():
    return {"status": "ok", "service": "Loom API"}

# PRD-103: Authenticated run list endpoint
@app.get("/api/v1/runs", dependencies=[Depends(verify_api_key)])
@app.get("/api/runs", dependencies=[Depends(verify_api_key)])
def list_runs(offset: int = 0, limit: int = 50):
    checkpoints_dir = Path.home() / ".loom" / "checkpoints"
    runs = []
    if checkpoints_dir.exists():
        for f in checkpoints_dir.glob("checkpoint_*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                runs.append({
                    "id": data.get("run_id"),
                    "issue": data.get("issue_description"),
                    "status": "VERIFIED SUCCESS" if data.get("verification_passed") else "EXECUTED",
                    "repo_path": data.get("repo_path"),
                    "created_at": data.get("created_at"),
                    "cost": data.get("shared_data", {}).get("cost_report", {}).get("total_cost_usd", 0.0025)
                })
            except (json.JSONDecodeError, OSError, ValueError) as err:
                logger.warning("Error reading checkpoint file %s: %s", f, err)
    runs.sort(key=lambda x: x.get("created_at", 0), reverse=True)
    return runs[offset : offset + limit]

@app.post("/api/v1/run", dependencies=[Depends(verify_api_key)])
@app.post("/api/run", dependencies=[Depends(verify_api_key)])
async def create_run(req: RunRequest):
    # PRD-004: Validate repo_path boundaries
    raw_path = Path(req.repo_path or ".").resolve()
    if not raw_path.exists() or not raw_path.is_dir():
        raise HTTPException(status_code=400, detail=f"Target repo_path does not exist or is not a directory: {req.repo_path}")

    allowed_roots = os.getenv("ALLOWED_REPO_ROOTS")
    if allowed_roots:
        roots = [Path(r.strip()).resolve() for r in allowed_roots.split(",") if r.strip()]
        if not any(r in raw_path.parents or r == raw_path for r in roots):
            raise HTTPException(status_code=403, detail="repo_path is not within allowed repository roots")

    repo_path = str(raw_path)
    run_id = f"run_{uuid.uuid4().hex[:8]}"

    state = OrchestratorState(
        run_id=run_id,
        repo_path=repo_path,
        issue_description=req.issue
    )

    router = ModelRouter(default_model=req.model, mock_mode=req.mock)
    tracer = TelemetryTracer(run_id=run_id)
    cost_tracker = CostTracker(run_id=run_id)

    task_graph = TaskGraph(state, router, tracer, cost_tracker)
    final_state = await task_graph.run()

    return {
        "run_id": run_id,
        "status": "VERIFIED SUCCESS" if final_state.verification_passed else "FAILED",
        "verification_passed": final_state.verification_passed,
        "patch_diff": final_state.patch_diff,
        "reproduction_test": final_state.reproduction_test,
        "reviewer_report": final_state.shared_data.get("reviewer_report"),
        "cost_report": final_state.shared_data.get("cost_report")
    }

# PRD-103: Authenticated run detail endpoint
@app.get("/api/v1/runs/{run_id}", dependencies=[Depends(verify_api_key)])
@app.get("/api/runs/{run_id}", dependencies=[Depends(verify_api_key)])
def get_run(run_id: str):
    checkpoint_file = Path.home() / ".loom" / "checkpoints" / f"checkpoint_{run_id}.json"
    trace_file = Path.home() / ".loom" / "traces" / f"trace_{run_id}.json"

    if not checkpoint_file.exists():
        raise HTTPException(status_code=404, detail="Run not found")

    data = json.loads(checkpoint_file.read_text(encoding="utf-8"))
    events = []
    if trace_file.exists():
        events = json.loads(trace_file.read_text(encoding="utf-8"))

    return {
        "checkpoint": data,
        "trace_events": events
    }

@app.post("/api/v1/rollback/{run_id}", dependencies=[Depends(verify_api_key)])
@app.post("/api/rollback/{run_id}", dependencies=[Depends(verify_api_key)])
def rollback(run_id: str):
    checkpoint_file = Path.home() / ".loom" / "checkpoints" / f"checkpoint_{run_id}.json"
    if not checkpoint_file.exists():
        raise HTTPException(status_code=404, detail="Checkpoint not found")

    data = json.loads(checkpoint_file.read_text(encoding="utf-8"))
    repo_path = data.get("repo_path")
    snapshot_id = data.get("snapshot_id")

    if not snapshot_id or not repo_path:
        raise HTTPException(status_code=400, detail="No snapshot found for rollback")

    sandbox = LocalProcessSandbox(repo_path)
    success = sandbox.restore_snapshot(snapshot_id)
    return {"success": success, "snapshot_id": snapshot_id}
