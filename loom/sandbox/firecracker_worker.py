"""Authenticated Firecracker worker service for Loom Tier C."""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, status
from prometheus_client import Counter, Gauge, Histogram, make_asgi_app
from pydantic import BaseModel, Field
from starlette.middleware.wsgi import WSGIMiddleware

from loom.sandbox.base import CommandResult
from loom.sandbox.firecracker_vm import FirecrackerConfig, FirecrackerVM, FirecrackerVMError, reconcile_runtime
from loom.sandbox.worktree import WorktreeManager

app = FastAPI(title="Loom Firecracker Worker", version="1.0.0", docs_url=None, redoc_url=None)

WORKER_TOKEN = os.getenv("LOOM_FIRECRACKER_WORKER_TOKEN") or os.getenv("SANDBOX_WORKER_TOKEN")
REPO_ROOT = Path(os.getenv("LOOM_FIRECRACKER_REPO_ROOT", "/var/repos")).resolve()
ENFORCE_ORG_ROOT = os.getenv("LOOM_FIRECRACKER_ENFORCE_ORG_ROOT", "true").lower() in {"1", "true", "yes"}
RUNTIME_DIR = Path(os.getenv("LOOM_FIRECRACKER_RUNTIME_DIR", "/var/lib/loom/firecracker")).resolve()
EVIDENCE_DIR = Path(os.getenv("LOOM_FIRECRACKER_EVIDENCE_DIR", "/var/lib/loom/evidence")).resolve()
FIRECRACKER_BIN = Path(os.getenv("FIRECRACKER_BIN", "/usr/local/bin/firecracker")).resolve()
KERNEL_PATH = Path(os.getenv("LOOM_FIRECRACKER_KERNEL", "/var/lib/loom/firecracker/kernel/vmlinux")).resolve()
ROOTFS_PATH = Path(os.getenv("LOOM_FIRECRACKER_ROOTFS", "/var/lib/loom/firecracker/rootfs.ext4")).resolve()
VCPUS = int(os.getenv("LOOM_FIRECRACKER_VCPUS", "2"))
MEMORY_MB = int(os.getenv("LOOM_FIRECRACKER_MEMORY_MB", "4096"))
APPROVED_VERSION = os.getenv("LOOM_FIRECRACKER_VERSION", "1.16.1").strip()
APPROVED_HASH_FILE = Path(os.getenv(
    "LOOM_FIRECRACKER_APPROVED_HASH_FILE",
    str(Path(__file__).resolve().parents[2] / "infra/firecracker/SHA256SUM"),
)).resolve()

if not WORKER_TOKEN:
    raise RuntimeError("LOOM_FIRECRACKER_WORKER_TOKEN must be configured")

def _safe_metric(metric_cls: Any, name: str, documentation: str, *args: Any, **kwargs: Any) -> Any:
    try:
        return metric_cls(name, documentation, *args, **kwargs)
    except Exception:
        try:
            from prometheus_client import REGISTRY
            collector = REGISTRY._names_to_collectors.get(name)
            if collector is not None:
                return collector
        except Exception:
            pass
        return metric_cls(name, documentation, *args, **kwargs)


VM_BOOT_TOTAL = _safe_metric(Counter, "firecracker_vm_boot_total", "Firecracker VM boots attempted")
VM_FAILURES_TOTAL = _safe_metric(Counter, "firecracker_vm_failures_total", "Firecracker VM failures")
VM_CLEANUP_FAILURES_TOTAL = _safe_metric(Counter, "firecracker_vm_cleanup_failures_total", "Firecracker VM cleanup failures")
EXECUTION_DURATION = _safe_metric(Histogram, "firecracker_execution_duration", "Firecracker execution duration seconds")
ACTIVE_VMS = _safe_metric(Gauge, "firecracker_active_vms", "Active Firecracker VMs")
WORKER_QUEUE_DEPTH = _safe_metric(Gauge, "firecracker_worker_queue_depth", "Firecracker worker queue depth")
app.mount("/metrics", WSGIMiddleware(make_asgi_app()))


class ExecuteRequest(BaseModel):
    run_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    org_id: str = Field(min_length=1, max_length=128)
    repo_path: str
    argv: Optional[List[str]] = None
    command: Optional[str] = None
    cwd: Optional[str] = None
    timeout: int = Field(default=60, ge=1, le=3600)
    env: Dict[str, str] = Field(default_factory=dict)
    network: bool = False


class SnapshotRequest(BaseModel):
    org_id: str = Field(min_length=1, max_length=128)
    repo_path: str
    label: str = "snapshot"


class RestoreRequest(BaseModel):
    org_id: str = Field(min_length=1, max_length=128)
    repo_path: str
    snapshot_id: str


def authenticate(authorization: Optional[str] = Header(None)) -> None:
    expected = f"Bearer {WORKER_TOKEN}"
    if not authorization or len(authorization) != len(expected) or not secrets.compare_digest(authorization, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Firecracker worker credential")


def resolve_repo(repo_path: str, org_id: str | None = None) -> Path:
    requested = Path(repo_path).resolve()
    try:
        requested.relative_to(REPO_ROOT)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="repo_path is outside Firecracker repository root") from exc
    if ENFORCE_ORG_ROOT:
        if not org_id or not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", org_id):
            raise HTTPException(status_code=403, detail="invalid org_id for repository isolation")
        org_root = (REPO_ROOT / org_id).resolve()
        try:
            requested.relative_to(org_root)
        except ValueError as exc:
            raise HTTPException(status_code=403, detail="repo_path is outside the requesting org root") from exc
    if not requested.is_dir():
        raise HTTPException(status_code=404, detail="repository path does not exist")
    return requested


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def host_health() -> dict:
    if os.name != "posix":
        raise RuntimeError("Firecracker worker requires Linux")
    if os.uname().machine != "x86_64":  # type: ignore[attr-defined]
        raise RuntimeError("current worker validation policy requires x86_64")
    kvm = Path("/dev/kvm")
    if not kvm.exists() or not os.access(kvm, os.R_OK | os.W_OK):
        raise RuntimeError("/dev/kvm is not readable/writable by the worker")
    if not FIRECRACKER_BIN.is_file() or not os.access(FIRECRACKER_BIN, os.X_OK):
        raise RuntimeError("Firecracker binary is unavailable")
    if not KERNEL_PATH.is_file():
        raise RuntimeError("Firecracker kernel image is unavailable")
    if not ROOTFS_PATH.is_file():
        raise RuntimeError("Firecracker rootfs image is unavailable")
    version_output = os.popen(f"{str(FIRECRACKER_BIN)} --version").read().strip()
    if APPROVED_VERSION not in version_output:
        raise RuntimeError(f"Firecracker version mismatch: expected {APPROVED_VERSION}, got {version_output}")
    expected_hashes = [line.strip().lower() for line in APPROVED_HASH_FILE.read_text(encoding="utf-8").splitlines() if re.fullmatch(r"[0-9a-fA-F]{64}", line.strip())] if APPROVED_HASH_FILE.is_file() else []
    if len(expected_hashes) != 1 or set(expected_hashes[0]) == {"0"}:
        raise RuntimeError("approved Firecracker SHA256 is missing or still a placeholder")
    actual_binary_hash = sha256_file(FIRECRACKER_BIN)
    if actual_binary_hash.lower() != expected_hashes[0]:
        raise RuntimeError("Firecracker binary SHA256 mismatch")
    return {
        "status": "ok",
        "runtime": "firecracker",
        "kvm": True,
        "kernel": f"sha256:{sha256_file(KERNEL_PATH)}",
        "rootfs": f"sha256:{sha256_file(ROOTFS_PATH)}",
        "version": APPROVED_VERSION,
        "binary": f"sha256:{actual_binary_hash}",
    }


@app.get("/health")
def health(_: None = Depends(authenticate)):
    try:
        return host_health()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/execute")
def execute(req: ExecuteRequest, _: None = Depends(authenticate)):
    if req.network:
        raise HTTPException(status_code=400, detail="network-enabled Tier C execution is not enabled")
    try:
        host_health()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    repo = resolve_repo(req.repo_path, req.org_id)
    argv = req.argv
    if argv is None:
        if not req.command:
            raise HTTPException(status_code=400, detail="argv or command is required")
        argv = ["/bin/sh", "-lc", req.command]

    started = time.monotonic()
    vm_id = f"vm-{uuid.uuid4().hex}"
    metadata = {
        "run_id": req.run_id,
        "vm_id": vm_id,
        "worker_id": os.getenv("LOOM_FIRECRACKER_WORKER_ID", os.uname().nodename if hasattr(os, "uname") else "worker-host"),
        "org_id": req.org_id,
        "repo_path": str(repo),
        "kernel_hash": sha256_file(KERNEL_PATH),
        "rootfs_hash": sha256_file(ROOTFS_PATH),
        "resource_limits": {"vcpu_count": VCPUS, "memory_mb": MEMORY_MB},
        "network_policy": "disabled",
        "started_at": time.time(),
    }
    config = FirecrackerConfig(
        binary=FIRECRACKER_BIN,
        kernel=KERNEL_PATH,
        rootfs=ROOTFS_PATH,
        runtime_dir=RUNTIME_DIR,
        vcpus=VCPUS,
        memory_mb=MEMORY_MB,
    )
    config.validate()
    VM_BOOT_TOTAL.inc()
    ACTIVE_VMS.inc()
    try:
        with FirecrackerVM(config, vm_id, metadata) as vm:
            vm.sync_repository(repo)
            result = vm.exec(argv, cwd=req.cwd or "/workspace", timeout=req.timeout, env=req.env)
        result["duration_seconds"] = round(time.monotonic() - started, 3)
        result["timed_out"] = bool(result.get("timed_out", False))
        result.pop("status", None)
        command_text = req.command or " ".join(argv)
        evidence = {
            **metadata,
            "finished_at": time.time(),
            "exit_code": int(result.get("exit_code", 1)),
            "timeout": result.get("timed_out", False),
            "stdout_sha256": hashlib.sha256(str(result.get("stdout", "")).encode()).hexdigest(),
            "stderr_sha256": hashlib.sha256(str(result.get("stderr", "")).encode()).hexdigest(),
            "cleanup_status": "complete",
        }
        EVIDENCE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
        (EVIDENCE_DIR / f"{req.run_id}.json").write_text(json.dumps(evidence, sort_keys=True, indent=2), encoding="utf-8")
        EXECUTION_DURATION.observe(result["duration_seconds"])
        return CommandResult(
            command=command_text,
            exit_code=int(result.get("exit_code", 1)),
            stdout=str(result.get("stdout", "")),
            stderr=str(result.get("stderr", "")),
            duration_seconds=float(result["duration_seconds"]),
            timed_out=bool(result.get("timed_out", False)),
        ).model_dump()
    except (FirecrackerVMError, OSError, ValueError) as exc:
        VM_FAILURES_TOTAL.inc()
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        ACTIVE_VMS.dec()


@app.post("/snapshot")
def snapshot(req: SnapshotRequest, _: None = Depends(authenticate)):
    repo = resolve_repo(req.repo_path, req.org_id)
    manager = WorktreeManager(str(repo))
    return {"snapshot_id": manager.create_snapshot(req.label)}


@app.post("/restore")
def restore(req: RestoreRequest, _: None = Depends(authenticate)):
    repo = resolve_repo(req.repo_path, req.org_id)
    manager = WorktreeManager(str(repo))
    return {"restored": manager.restore_snapshot(req.snapshot_id)}


@app.post("/recover")
def recover(_: None = Depends(authenticate)):
    return reconcile_runtime(RUNTIME_DIR)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=os.getenv("LOOM_FIRECRACKER_BIND", "127.0.0.1"), port=int(os.getenv("LOOM_FIRECRACKER_PORT", "8101")))
