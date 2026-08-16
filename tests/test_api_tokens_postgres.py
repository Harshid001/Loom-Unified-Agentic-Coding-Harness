import os
import tempfile
import time

from loom.auth.api_tokens import (
    ApiTokenStore,
    get_api_token_store,
    hash_token,
    reset_api_token_store,
)


def test_api_token_store_jsonl_lifecycle():
    with tempfile.TemporaryDirectory() as temp_dir:
        store = ApiTokenStore(storage_dir=temp_dir)
        record, token = store.issue(user_id="usr_123", org_id="org_abc", label="CLI Token")
        assert record.user_id == "usr_123"
        assert record.org_id == "org_abc"
        assert record.active is True
        assert record.prefix == token[:8]
        assert record.token_hash == hash_token(token)

        # Verify
        verified = store.verify(token)
        assert verified is not None
        assert verified.id == record.id
        assert verified.user_id == "usr_123"

        # List active
        active = store.list_active_for_user("usr_123")
        assert len(active) == 1
        assert active[0].id == record.id

        # Count
        assert store.count() == 1

        # Revoke
        revoked = store.revoke(record.id)
        assert revoked is True
        assert store.verify(token) is None
        assert store.count() == 0


def test_api_token_store_expiry():
    with tempfile.TemporaryDirectory() as temp_dir:
        os.environ["LOOM_TOKEN_TTL_SECONDS"] = "1"
        try:
            store = ApiTokenStore(storage_dir=temp_dir)
            record, token = store.issue(user_id="usr_exp", org_id="org_test")
            assert store.verify(token) is not None
            time.sleep(1.1)
            assert store.verify(token) is None
            assert len(store.list_active_for_user("usr_exp")) == 0
        finally:
            os.environ.pop("LOOM_TOKEN_TTL_SECONDS", None)


def test_api_token_store_revoke_all():
    with tempfile.TemporaryDirectory() as temp_dir:
        store = ApiTokenStore(storage_dir=temp_dir)
        r1, t1 = store.issue(user_id="usr_bulk", org_id="org_test", label="T1")
        r2, t2 = store.issue(user_id="usr_bulk", org_id="org_test", label="T2")
        r3, t3 = store.issue(user_id="usr_other", org_id="org_test", label="T3")

        assert store.count() == 3
        count_revoked = store.revoke_all_for_user("usr_bulk")
        assert count_revoked == 2
        assert store.verify(t1) is None
        assert store.verify(t2) is None
        assert store.verify(t3) is not None
        assert store.count() == 1


def test_api_token_singleton():
    reset_api_token_store()
    with tempfile.TemporaryDirectory() as temp_dir:
        s1 = get_api_token_store(storage_dir=temp_dir)
        s2 = get_api_token_store()
        assert s1 is s2
    reset_api_token_store()
