"""Durable run-state interface for distributed workers."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from time import time
from typing import Dict, Optional


class RunState(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    FAILED = "failed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    SECURITY_HOLD = "security_hold"
    CONFLICT_RESOLUTION = "conflict_resolution"
    ROLLED_BACK = "rolled_back"


_ALLOWED = {
    RunState.QUEUED: {RunState.RUNNING, RunState.CANCELLED},
    RunState.RUNNING: {RunState.PAUSED, RunState.FAILED, RunState.COMPLETED, RunState.CANCELLED, RunState.SECURITY_HOLD, RunState.CONFLICT_RESOLUTION, RunState.ROLLED_BACK},
    RunState.PAUSED: {RunState.RUNNING, RunState.CANCELLED},
    RunState.SECURITY_HOLD: {RunState.RUNNING, RunState.CANCELLED},
    RunState.CONFLICT_RESOLUTION: {RunState.RUNNING, RunState.CANCELLED},
    RunState.FAILED: set(),
    RunState.COMPLETED: set(),
    RunState.CANCELLED: set(),
    RunState.ROLLED_BACK: set(),
}


@dataclass
class RunStateRecord:
    run_id: str
    org_id: str
    state: RunState = RunState.QUEUED
    version: int = 0
    worker_id: Optional[str] = None
    heartbeat_at: Optional[float] = None
    metadata: Dict[str, str] = field(default_factory=dict)


class InvalidRunTransition(ValueError):
    pass


def transition(record: RunStateRecord, target: RunState, *, expected_version: Optional[int] = None) -> RunStateRecord:
    if expected_version is not None and record.version != expected_version:
        raise InvalidRunTransition("stale run-state version")
    if target not in _ALLOWED.get(record.state, set()):
        raise InvalidRunTransition(f"invalid run transition: {record.state.value} -> {target.value}")
    record.state = target
    record.version += 1
    record.heartbeat_at = time() if target == RunState.RUNNING else record.heartbeat_at
    return record


def heartbeat(record: RunStateRecord, worker_id: str) -> RunStateRecord:
    if record.state != RunState.RUNNING:
        raise InvalidRunTransition("heartbeat is only valid for running jobs")
    record.worker_id = worker_id
    record.heartbeat_at = time()
    return record
