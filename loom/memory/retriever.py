from typing import List, Optional

from loom.memory.models import MemoryItem, MemoryTier
from loom.memory.store import TieredMemoryStore


class MemoryRetriever:
    """Ranks and retrieves relevant memory items combining recency, confidence, and query match."""

    def __init__(self, store: TieredMemoryStore):
        self.store = store

    def retrieve(
        self,
        query: str,
        tiers: Optional[List[MemoryTier]] = None,
        limit: int = 5,
        org_id: Optional[str] = None,
    ) -> List[MemoryItem]:
        results: List[MemoryItem] = []

        if not tiers:
            tiers = list(MemoryTier)

        for tier in tiers:
            items = self.store.search(query, tier=tier, limit=limit, org_id=org_id)
            results.extend(items)

        # Sort by confidence * recency score
        def score(item: MemoryItem):
            return item.confidence * (1.0 / (1.0 + (item.created_at / 1e9)))

        results.sort(key=score, reverse=True)
        return results[:limit]
