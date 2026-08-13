"""Tenant-safe team memory synchronization primitives."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Iterable, List


@dataclass(frozen=True)
class MemoryRecord:
    id: str
    org_id: str
    content: str
    version: int
    content_hash: str

    @classmethod
    def make(cls, id: str, org_id: str, content: str, version: int) -> "MemoryRecord":
        return cls(id, org_id, content, version, sha256(content.encode("utf-8")).hexdigest())


def resolve_conflict(local: MemoryRecord, remote: MemoryRecord) -> MemoryRecord:
    if local.org_id != remote.org_id:
        raise ValueError("cross-organization memory merge is forbidden")
    if remote.version != local.version:
        return remote if remote.version > local.version else local
    return remote if remote.content_hash > local.content_hash else local


def merge_records(local: Iterable[MemoryRecord], remote: Iterable[MemoryRecord]) -> tuple[List[MemoryRecord], int]:
    merged = {item.id: item for item in local}
    conflicts = 0
    for item in remote:
        current = merged.get(item.id)
        if current is None:
            merged[item.id] = item
            continue
        if current != item:
            conflicts += 1
            merged[item.id] = resolve_conflict(current, item)
    return list(merged.values()), conflicts
