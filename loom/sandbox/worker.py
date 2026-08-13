"""Dedicated sandbox worker service.

Only this service should have access to the Docker daemon socket in production.
The API process talks to it over an authenticated internal HTTP connection.
"""

import os
import secrets
from pathlib import Path
from typing import Dict, List, Optional, Union

from fastapi import Depends, FastAPI, Header, HTTPException, status
from pydantic import BaseModel, Field

from loom.sandbox.docker_sandbox import DockerSandbox

app = FastAPI(title="Loom Sandbox Worker", version="1.0.0", docs_url=None, redoc_url=None)

HOST_REPO_ROOT = Path(os.getenv("SANDBOX_HOST_REPO_ROOT", "/var/repos")).resolve()
CONTAINER_REPO_ROOT = Path(os.getenv("SANDBOX_CONTAINER_REPO_ROOT", "/workspace")).resolve()
WORKER_TOKEN = os.getenv("SANDBOX_WORKER_TOKEN")
ALLOW_NETWORK = os.getenv("SANDBOX_ALLOW_NETWORK", "false").lower() in {"1", "true", "yes"}

if not WORKER_TOKEN:
    raise RuntimeError("SANDBOX_WORKER_TOKEN must be configured")


def authenticate(authorization: Optional[str] = Header(None)) -> None:
    expected = f"Bearer {WORKER_TOKEN}"
    if not authorization or len(authorization) != len(expected) or not secrets.compare_digest(authorization, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid sandbox worker credential")


def resolve_repo_path(repo_path: str) -> Path:
    requested = Path(repo_path).resolve()
    try:
        relative = requested.relative_to(CONTAINER_REPO_ROOT)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="repo_path is outside the sandbox worker repository root") from exc
    host_path = (HOST_REPO_ROOT / relative).resolve()
    try:
        host_path.relative_to(HOST_REPO_ROOT)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="resolved repository path escapes host repository root") from exc
    if not host_path.is_dir():
        raise HTTPException(status_code=404, detail="repository path does not exist")
    return host_path


class ExecuteRequest(BaseModel):
    repo_path: str
    cmd: Union[str, List[str]]
    cwd: Optional[str] = None
    timeout: int = Field(default=60, ge=1, le=3600)
    env: Dict[str, str] = Field(default_factory=dict)


class SnapshotRequest(BaseModel):
    repo_path: str
    label: str = "snapshot"


class RestoreRequest(BaseModel):
    repo_path: str
    snapshot_id: str


@app.get("/health")
def health(_: None = Depends(authenticate)):
    return {"status": "ok", "docker": "required"}


@app.post("/execute")
def execute(req: ExecuteRequest, _: None = Depends(authenticate)):
    host_repo = resolve_repo_path(req.repo_path)
    host_cwd = None
    if req.cwd:
        requested_cwd = Path(req.cwd).resolve()
        try:
            requested_cwd.relative_to(Path(req.repo_path).resolve())
        except ValueError as exc:
            raise HTTPException(status_code=403, detail="cwd escapes repository path") from exc
        host_cwd = str(host_repo / requested_cwd.relative_to(Path(req.repo_path).resolve()))

    sandbox = DockerSandbox(
        str(host_repo),
        cpu_limit=2.0,
        memory_mb=4096,
        allow_network=ALLOW_NETWORK,
        allow_local_fallback=False,
    )
    result = sandbox.run_command(req.cmd, cwd=host_cwd, timeout=req.timeout, env=req.env)
    return result.model_dump()


@app.post("/snapshot")
def snapshot(req: SnapshotRequest, _: None = Depends(authenticate)):
    host_repo = resolve_repo_path(req.repo_path)
    sandbox = DockerSandbox(str(host_repo), allow_local_fallback=False)
    return {"snapshot_id": sandbox.create_snapshot(req.label)}


@app.post("/restore")
def restore(req: RestoreRequest, _: None = Depends(authenticate)):
    host_repo = resolve_repo_path(req.repo_path)
    sandbox = DockerSandbox(str(host_repo), allow_local_fallback=False)
    return {"restored": sandbox.restore_snapshot(req.snapshot_id)}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8100")))
