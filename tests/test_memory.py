from loom.memory.models import InvalidationRule, MemoryItem, MemoryTier
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
    assert store.get_schema_version() >= 3


def test_memory_items_are_tenant_scoped(tmp_path):
    db_path = str(tmp_path / "tenant.db")
    store = TieredMemoryStore(db_path=db_path)

    store.add(
        MemoryItem(
            org_id="org_a",
            tier=MemoryTier.PROJECT_CONVENTIONS,
            content="org_a convention: tabs",
            source="test",
        )
    )
    store.add(
        MemoryItem(
            org_id="org_b",
            tier=MemoryTier.PROJECT_CONVENTIONS,
            content="org_b convention: tabs",
            source="test",
        )
    )

    assert len(store.get_by_tier(MemoryTier.PROJECT_CONVENTIONS, org_id="org_a")) == 1
    assert len(store.get_by_tier(MemoryTier.PROJECT_CONVENTIONS, org_id="org_b")) == 1
    assert len(store.get_by_tier(MemoryTier.PROJECT_CONVENTIONS)) == 2

    only_a = store.search("tabs", org_id="org_a")
    assert len(only_a) == 1
    assert only_a[0].org_id == "org_a"

    store.clear_tier(MemoryTier.PROJECT_CONVENTIONS, org_id="org_a")
    assert len(store.get_by_tier(MemoryTier.PROJECT_CONVENTIONS, org_id="org_a")) == 0
    assert len(store.get_by_tier(MemoryTier.PROJECT_CONVENTIONS, org_id="org_b")) == 1


def test_default_org_id_and_ttl_expires_at(tmp_path):
    db_path = str(tmp_path / "ttl.db")
    store = TieredMemoryStore(db_path=db_path)

    item = MemoryItem(tier=MemoryTier.PROCEDURE, content="retry procedure", source="test")
    assert item.org_id == "default"
    assert item.ttl_expires_at is None
    store.add(item)

    loaded = store.search("retry procedure")[0]
    assert loaded.org_id == "default"
    assert loaded.ttl_expires_at is None

    ttl_item = MemoryItem(
        tier=MemoryTier.EPISODIC,
        content="expiring fact",
        source="test",
        invalidation=InvalidationRule(rule_type="time_to_live", ttl_seconds=3600),
    )
    expect_expiry = ttl_item.created_at + 3600
    assert abs((ttl_item.ttl_expires_at or 0) - expect_expiry) < 0.001


def test_retriever_scopes_by_org(tmp_path):
    from loom.memory.retriever import MemoryRetriever

    db_path = str(tmp_path / "retriever.db")
    store = TieredMemoryStore(db_path=db_path)
    store.add(
        MemoryItem(
            org_id="org_x",
            tier=MemoryTier.PROJECT_CONVENTIONS,
            content="rename util helpers",
            source="test",
        )
    )
    store.add(
        MemoryItem(
            org_id="org_y",
            tier=MemoryTier.PROJECT_CONVENTIONS,
            content="rename util helpers",
            source="test",
        )
    )

    retriever = MemoryRetriever(store)
    hits_x = retriever.retrieve("rename util helpers", tiers=[MemoryTier.PROJECT_CONVENTIONS], org_id="org_x")
    assert len(hits_x) == 1
    assert hits_x[0].org_id == "org_x"


def test_append_only_tiers_never_overwrite(tmp_path):
    db_path = str(tmp_path / "append_only.db")
    store = TieredMemoryStore(db_path=db_path)

    episodic = MemoryItem(
        id="ep_same_id",
        tier=MemoryTier.EPISODIC,
        content="episodic lesson one",
        source="test",
    )
    store.add(episodic)
    store.add(
        MemoryItem(
            id="ep_same_id",
            tier=MemoryTier.EPISODIC,
            content="episodic lesson two",
            source="test",
        )
    )

    episodic_rows = store.get_by_tier(MemoryTier.EPISODIC)
    assert len(episodic_rows) == 2
    assert {r.content for r in episodic_rows} == {"episodic lesson one", "episodic lesson two"}

    evidence = MemoryItem(
        id="ev_same_id",
        tier=MemoryTier.VERIFIED_EVIDENCE,
        content="verified evidence one",
        source="test",
    )
    store.add(evidence)
    store.add(
        MemoryItem(
            id="ev_same_id",
            tier=MemoryTier.VERIFIED_EVIDENCE,
            content="verified evidence two",
            source="test",
        )
    )
    assert len(store.get_by_tier(MemoryTier.VERIFIED_EVIDENCE)) == 2


def test_mutable_tier_still_replaces_same_id(tmp_path):
    db_path = str(tmp_path / "mutable.db")
    store = TieredMemoryStore(db_path=db_path)

    store.add(
        MemoryItem(
            id="work_same_id",
            tier=MemoryTier.WORKING,
            content="draft v1",
            source="test",
        )
    )
    store.add(
        MemoryItem(
            id="work_same_id",
            tier=MemoryTier.WORKING,
            content="draft v2",
            source="test",
        )
    )
    rows = store.get_by_tier(MemoryTier.WORKING)
    assert len(rows) == 1
    assert rows[0].content == "draft v2"
