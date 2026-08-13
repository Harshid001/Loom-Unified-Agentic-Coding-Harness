"""Production status primitives."""

from dataclasses import dataclass
from time import time


@dataclass(frozen=True)
class StatusSnapshot:
    healthy: bool
    generated_at: float


def healthy_status() -> StatusSnapshot:
    return StatusSnapshot(healthy=True, generated_at=time())
