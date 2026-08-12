import json
import logging
import os
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator, List, Optional

from loom.memory.models import InvalidationRule, MemoryItem, MemoryTier

logger = logging.getLogger("loom.memory.store")


class TieredMemoryStore:
    """Persistent 7-tier memory store with provenance, invalidation handling, WAL concurrency, and live backups.
    Supports SQLite and PostgreSQL via SQLAlchemy when DATABASE_URL is configured."""

    def __init__(self, db_path: Optional[str] = None):
        database_url = os.getenv("DATABASE_URL")
        self._pg_engine: Optional[Any] = None
        if database_url and (database_url.startswith("postgresql://") or database_url.startswith("postgres://")):
            self.is_postgres = True
            self.db_url = database_url
            try:
                from sqlalchemy import create_engine

                self._pg_engine = create_engine(self.db_url, pool_size=5, max_overflow=10)
            except ImportError:
                self._pg_engine = None
        else:
            self.is_postgres = False

        if not db_path:
            db_path = os.getenv("LOOM_DB_PATH")
        if not db_path:
            db_dir = Path.home() / ".loom"
            db_dir.mkdir(parents=True, exist_ok=True)
            db_path = str(db_dir / "memory.db")
        self.db_path = db_path

        self._init_db()

    def _get_pg_engine(self):
        if self._pg_engine is None and self.is_postgres:
            from sqlalchemy import create_engine

            self._pg_engine = create_engine(self.db_url, pool_size=5, max_overflow=10)
        return self._pg_engine

    @contextmanager
    def connect(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager that ensures SQLite connections are properly closed on exit."""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
        except Exception:
            pass
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self):
        if self.is_postgres:
            self._init_postgres_db()
            return

        with self.connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at REAL
                )
            """)
            conn.commit()
        self._apply_migrations()

    def _init_postgres_db(self):
        try:
            from sqlalchemy import text

            engine = self._get_pg_engine()
            if engine:
                with engine.connect() as conn:
                    conn.execute(
                        text("""
                        CREATE TABLE IF NOT EXISTS memory_items (
                            id VARCHAR PRIMARY KEY,
                            org_id VARCHAR NOT NULL DEFAULT 'default',
                            tier VARCHAR NOT NULL,
                            content TEXT NOT NULL,
                            source VARCHAR,
                            confidence DOUBLE PRECISION,
                            scope VARCHAR,
                            created_at DOUBLE PRECISION,
                            last_used_at DOUBLE PRECISION,
                            invalidation TEXT,
                            metadata TEXT
                        )
                    """)
                    )
                    conn.execute(
                        text("CREATE INDEX IF NOT EXISTS idx_org_id ON memory_items(org_id)")
                    )
                    conn.commit()
        except Exception as err:
            logger.error("Failed to initialize PostgreSQL memory DB: %s", err)
            raise

    def get_schema_version(self) -> int:
        if self.is_postgres:
            return 3
        with self.connect() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT MAX(version) FROM schema_migrations")
            row = cursor.fetchone()
            return row[0] if row and row[0] is not None else 0

    def _apply_migrations(self):
        if self.is_postgres:
            return
        current_version = self.get_schema_version()
        migrations = [
            (1, self._migration_v1),
            (2, self._migration_v2),
            (3, self._migration_v3),
        ]
        for version, migration_fn in migrations:
            if current_version < version:
                with self.connect() as conn:
                    migration_fn(conn)
                    conn.execute(
                        "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)", (version, time.time())
                    )
                    conn.commit()

    def _migration_v1(self, conn: sqlite3.Connection):
        conn.execute("""
            CREATE TABLE IF NOT EXISTS memory_items (
                id TEXT PRIMARY KEY,
                tier TEXT NOT NULL,
                content TEXT NOT NULL,
                source TEXT,
                confidence REAL,
                scope TEXT,
                created_at REAL,
                last_used_at REAL,
                invalidation TEXT,
                metadata TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tier ON memory_items(tier)")

    def _migration_v2(self, conn: sqlite3.Connection):
        conn.execute("CREATE INDEX IF NOT EXISTS idx_scope ON memory_items(scope)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_created_at ON memory_items(created_at)")

    def _migration_v3(self, conn: sqlite3.Connection):
        conn.execute("ALTER TABLE memory_items ADD COLUMN org_id TEXT NOT NULL DEFAULT 'default'")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_org_id ON memory_items(org_id)")

    def backup(self, backup_path: str) -> str:
        """Create live online backup of memory database."""
        dest_path = Path(backup_path).resolve()
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dst = sqlite3.connect(str(dest_path))
        try:
            with self.connect() as src:
                src.backup(dst)
        finally:
            dst.close()
        return str(dest_path)

    @staticmethod
    def _is_append_only_tier(tier: Any) -> bool:
        """Tier 3 (EPISODIC) and Tier 5 (VERIFIED_EVIDENCE) are append-only (spec §3.3)."""
        tier_val = tier.value if isinstance(tier, MemoryTier) else tier
        return tier_val in (MemoryTier.EPISODIC.value, MemoryTier.VERIFIED_EVIDENCE.value)

    def _exists(self, item_id: str) -> bool:
        if self.is_postgres:
            from sqlalchemy import text

            engine = self._get_pg_engine()
            if engine:
                with engine.connect() as conn:
                    res = conn.execute(text("SELECT 1 FROM memory_items WHERE id = :id"), {"id": item_id})
                    return res.fetchone() is not None
            return False

        with self.connect() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM memory_items WHERE id = ?", (item_id,))
            return cursor.fetchone() is not None

    def add(self, item: MemoryItem) -> MemoryItem:
        if self._is_append_only_tier(item.tier) and self._exists(item.id):
            logger.info(
                "Append-only tier %s: preserving existing row %s, writing new row with fresh id",
                item.tier,
                item.id,
            )
            item.id = str(uuid.uuid4())
        if self.is_postgres:
            from sqlalchemy import text

            engine = self._get_pg_engine()
            if engine:
                with engine.connect() as conn:
                    conn.execute(
                        text("""
                            INSERT INTO memory_items (id, org_id, tier, content, source, confidence, scope, created_at, last_used_at, invalidation, metadata)
                            VALUES (:id, :org_id, :tier, :content, :source, :confidence, :scope, :created_at, :last_used_at, :invalidation, :metadata)
                            ON CONFLICT (id) DO UPDATE SET
                                org_id = EXCLUDED.org_id,
                                tier = EXCLUDED.tier,
                                content = EXCLUDED.content,
                                source = EXCLUDED.source,
                                confidence = EXCLUDED.confidence,
                                scope = EXCLUDED.scope,
                                created_at = EXCLUDED.created_at,
                                last_used_at = EXCLUDED.last_used_at,
                                invalidation = EXCLUDED.invalidation,
                                metadata = EXCLUDED.metadata
                        """),
                        {
                            "id": item.id,
                            "org_id": item.org_id,
                            "tier": item.tier.value if isinstance(item.tier, MemoryTier) else item.tier,
                            "content": item.content,
                            "source": item.source,
                            "confidence": item.confidence,
                            "scope": item.scope,
                            "created_at": item.created_at,
                            "last_used_at": item.last_used_at,
                            "invalidation": json.dumps(item.invalidation.model_dump()),
                            "metadata": json.dumps(item.metadata),
                        },
                    )
                    conn.commit()
            return item

        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO memory_items
                (id, org_id, tier, content, source, confidence, scope, created_at, last_used_at, invalidation, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.id,
                    item.org_id,
                    item.tier.value if isinstance(item.tier, MemoryTier) else item.tier,
                    item.content,
                    item.source,
                    item.confidence,
                    item.scope,
                    item.created_at,
                    item.last_used_at,
                    json.dumps(item.invalidation.model_dump()),
                    json.dumps(item.metadata),
                ),
            )
            conn.commit()
        return item

    def get_by_tier(self, tier: MemoryTier, org_id: Optional[str] = None) -> List[MemoryItem]:
        tier_val = tier.value if isinstance(tier, MemoryTier) else tier
        items = []
        if self.is_postgres:
            from sqlalchemy import text

            engine = self._get_pg_engine()
            if engine:
                with engine.connect() as conn:
                    if org_id is not None:
                        res = conn.execute(
                            text(
                                "SELECT id, org_id, tier, content, source, confidence, scope, created_at, last_used_at, invalidation, metadata FROM memory_items WHERE tier = :tier AND org_id = :org_id"
                            ),
                            {"tier": tier_val, "org_id": org_id},
                        )
                    else:
                        res = conn.execute(
                            text(
                                "SELECT id, org_id, tier, content, source, confidence, scope, created_at, last_used_at, invalidation, metadata FROM memory_items WHERE tier = :tier"
                            ),
                            {"tier": tier_val},
                        )
                    for r in res.fetchall():
                        items.append(self._row_to_item(r))
            return items

        with self.connect() as conn:
            cursor = conn.cursor()
            if org_id is not None:
                cursor.execute("SELECT id, org_id, tier, content, source, confidence, scope, created_at, last_used_at, invalidation, metadata FROM memory_items WHERE tier = ? AND org_id = ? ORDER BY last_used_at DESC", (tier_val, org_id))
            else:
                cursor.execute("SELECT id, org_id, tier, content, source, confidence, scope, created_at, last_used_at, invalidation, metadata FROM memory_items WHERE tier = ? ORDER BY last_used_at DESC", (tier_val,))
            rows = cursor.fetchall()
            for r in rows:
                items.append(self._row_to_item(r))
        return items

    def search(
        self,
        query: str,
        tier: Optional[MemoryTier] = None,
        limit: int = 10,
        org_id: Optional[str] = None,
    ) -> List[MemoryItem]:
        items = []
        query_str = f"%{query.lower()}%"
        if self.is_postgres:
            from sqlalchemy import text

            engine = self._get_pg_engine()
            if engine:
                with engine.connect() as conn:
                    if tier and org_id is not None:
                        tier_val = tier.value if isinstance(tier, MemoryTier) else tier
                        res = conn.execute(
                            text(
                                "SELECT id, org_id, tier, content, source, confidence, scope, created_at, last_used_at, invalidation, metadata FROM memory_items WHERE tier = :tier AND org_id = :org_id AND LOWER(content) LIKE :q ORDER BY last_used_at DESC LIMIT :lim"
                            ),
                            {"tier": tier_val, "org_id": org_id, "q": query_str, "lim": limit},
                        )
                    elif tier:
                        tier_val = tier.value if isinstance(tier, MemoryTier) else tier
                        res = conn.execute(
                            text(
                                "SELECT id, org_id, tier, content, source, confidence, scope, created_at, last_used_at, invalidation, metadata FROM memory_items WHERE tier = :tier AND LOWER(content) LIKE :q ORDER BY last_used_at DESC LIMIT :lim"
                            ),
                            {"tier": tier_val, "q": query_str, "lim": limit},
                        )
                    elif org_id is not None:
                        res = conn.execute(
                            text(
                                "SELECT id, org_id, tier, content, source, confidence, scope, created_at, last_used_at, invalidation, metadata FROM memory_items WHERE org_id = :org_id AND LOWER(content) LIKE :q ORDER BY last_used_at DESC LIMIT :lim"
                            ),
                            {"org_id": org_id, "q": query_str, "lim": limit},
                        )
                    else:
                        res = conn.execute(
                            text(
                                "SELECT id, org_id, tier, content, source, confidence, scope, created_at, last_used_at, invalidation, metadata FROM memory_items WHERE LOWER(content) LIKE :q ORDER BY last_used_at DESC LIMIT :lim"
                            ),
                            {"q": query_str, "lim": limit},
                        )
                    for r in res.fetchall():
                        item = self._row_to_item(r)
                        items.append(item)
                        self.touch(item.id)
            return items

        with self.connect() as conn:
            cursor = conn.cursor()
            if tier and org_id is not None:
                tier_val = tier.value if isinstance(tier, MemoryTier) else tier
                cursor.execute(
                    "SELECT id, org_id, tier, content, source, confidence, scope, created_at, last_used_at, invalidation, metadata FROM memory_items WHERE tier = ? AND org_id = ? AND LOWER(content) LIKE ? ORDER BY last_used_at DESC LIMIT ?",
                    (tier_val, org_id, query_str, limit),
                )
            elif tier:
                tier_val = tier.value if isinstance(tier, MemoryTier) else tier
                cursor.execute(
                    "SELECT id, org_id, tier, content, source, confidence, scope, created_at, last_used_at, invalidation, metadata FROM memory_items WHERE tier = ? AND LOWER(content) LIKE ? ORDER BY last_used_at DESC LIMIT ?",
                    (tier_val, query_str, limit),
                )
            elif org_id is not None:
                cursor.execute(
                    "SELECT id, org_id, tier, content, source, confidence, scope, created_at, last_used_at, invalidation, metadata FROM memory_items WHERE org_id = ? AND LOWER(content) LIKE ? ORDER BY last_used_at DESC LIMIT ?",
                    (org_id, query_str, limit),
                )
            else:
                cursor.execute(
                    "SELECT id, org_id, tier, content, source, confidence, scope, created_at, last_used_at, invalidation, metadata FROM memory_items WHERE LOWER(content) LIKE ? ORDER BY last_used_at DESC LIMIT ?",
                    (query_str, limit),
                )
            rows = cursor.fetchall()
            for r in rows:
                item = self._row_to_item(r)
                items.append(item)
                self.touch(item.id)
        return items

    def touch(self, item_id: str):
        if self.is_postgres:
            from sqlalchemy import text

            engine = self._get_pg_engine()
            if engine:
                with engine.connect() as conn:
                    conn.execute(
                        text("UPDATE memory_items SET last_used_at = :ts WHERE id = :id"),
                        {"ts": time.time(), "id": item_id},
                    )
                    conn.commit()
            return

        with self.connect() as conn:
            conn.execute("UPDATE memory_items SET last_used_at = ? WHERE id = ?", (time.time(), item_id))
            conn.commit()

    def invalidate_changed(self, changed_files: List[str]):
        """Check all memory items against changed files and purge invalid ones."""
        items = self.get_by_tier(MemoryTier.PROJECT_CONVENTIONS) + self.get_by_tier(MemoryTier.PROCEDURE)
        to_delete = []
        for item in items:
            if item.invalidation.is_invalid(changed_files):
                to_delete.append(item.id)

        if to_delete:
            if self.is_postgres:
                from sqlalchemy import text

                engine = self._get_pg_engine()
                if engine:
                    with engine.connect() as conn:
                        for i in to_delete:
                            conn.execute(text("DELETE FROM memory_items WHERE id = :id"), {"id": i})
                        conn.commit()
            else:
                with self.connect() as conn:
                    conn.executemany("DELETE FROM memory_items WHERE id = ?", [(i,) for i in to_delete])
                    conn.commit()

    def clear_tier(self, tier: MemoryTier, org_id: Optional[str] = None):
        tier_val = tier.value if isinstance(tier, MemoryTier) else tier
        if self.is_postgres:
            from sqlalchemy import text

            engine = self._get_pg_engine()
            if engine:
                with engine.connect() as conn:
                    if org_id is not None:
                        conn.execute(
                            text("DELETE FROM memory_items WHERE tier = :tier AND org_id = :org_id"),
                            {"tier": tier_val, "org_id": org_id},
                        )
                    else:
                        conn.execute(text("DELETE FROM memory_items WHERE tier = :tier"), {"tier": tier_val})
                    conn.commit()
            return

        with self.connect() as conn:
            if org_id is not None:
                conn.execute("DELETE FROM memory_items WHERE tier = ? AND org_id = ?", (tier_val, org_id))
            else:
                conn.execute("DELETE FROM memory_items WHERE tier = ?", (tier_val,))
            conn.commit()

    def _row_to_item(self, row: Any) -> MemoryItem:
        return MemoryItem(
            id=row[0],
            org_id=row[1],
            tier=MemoryTier(row[2]),
            content=row[3],
            source=row[4],
            confidence=row[5],
            scope=row[6],
            created_at=row[7],
            last_used_at=row[8],
            invalidation=InvalidationRule(**json.loads(row[9])),
            metadata=json.loads(row[10]),
        )
