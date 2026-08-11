from loom.memory.models import MemoryItem, MemoryTier
from loom.memory.store import TieredMemoryStore


def test_tiered_memory_store(tmp_path):
    db_path = str(tmp_path / "test_memory.db")
    store = TieredMemoryStore(db_path=db_path)

    item = MemoryItem(
        tier=MemoryTier.PROJECT_CONVENTIONS, content="Use snake_case for Python function names", source="test"
    )
    store.add(item)

    retrieved = store.get_by_tier(MemoryTier.PROJECT_CONVENTIONS)
    assert len(retrieved) == 1
    assert retrieved[0].content == "Use snake_case for Python function names"

    search_res = store.search("snake_case")
    assert len(search_res) == 1


def test_schema_migrations(tmp_path):
    db_path = str(tmp_path / "test_migrations.db")
    store = TieredMemoryStore(db_path=db_path)
    assert store.get_schema_version() >= 2
