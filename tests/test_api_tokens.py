import pytest

from loom.auth.api_tokens import ApiTokenStore, TokenAdministrationDisabled


def _store(tmp_path) -> ApiTokenStore:
    return ApiTokenStore(storage_dir=str(tmp_path / "tokens"))


def test_issue_returns_plaintext_once_and_hash_at_rest(tmp_path, monkeypatch):
    monkeypatch.setenv("LOOM_ENV", "development")
    store = _store(tmp_path)
    record, token = store.issue("user_a", org_id="org_1", label="cli")
    assert record.token_hash != token
    assert record.prefix == token[:8]
    assert record.active is True

    raw = (tmp_path / "tokens" / "api_tokens.jsonl").read_text(encoding="utf-8")
    assert token not in raw
    assert record.token_hash in raw


def test_verify_accepts_only_issued_token(tmp_path, monkeypatch):
    monkeypatch.setenv("LOOM_ENV", "development")
    store = _store(tmp_path)
    _, token = store.issue("user_a", org_id="org_1")
    assert store.verify(token) is not None
    assert store.verify(f"{token}x") is None
    assert store.verify("nope") is None


def test_verify_matches_user(tmp_path, monkeypatch):
    monkeypatch.setenv("LOOM_ENV", "development")
    store = _store(tmp_path)
    _, token_a = store.issue("user_a", org_id="org_1")
    _, token_b = store.issue("user_b", org_id="org_1")
    assert store.verify(token_a).user_id == "user_a"
    assert store.verify(token_b).user_id == "user_b"


def test_revoke_disables_token(tmp_path, monkeypatch):
    monkeypatch.setenv("LOOM_ENV", "development")
    store = _store(tmp_path)
    record, token = store.issue("user_a", org_id="org_1")
    assert store.revoke(record.id) is True
    assert store.verify(token) is None
    assert store.revoke(record.id) is False


def test_revoke_all_for_user(tmp_path, monkeypatch):
    monkeypatch.setenv("LOOM_ENV", "development")
    store = _store(tmp_path)
    _, token_a1 = store.issue("user_a", org_id="org_1")
    _, token_a2 = store.issue("user_a", org_id="org_1")
    _, token_b = store.issue("user_b", org_id="org_1")
    assert store.revoke_all_for_user("user_a") == 2
    assert store.verify(token_a1) is None
    assert store.verify(token_a2) is None
    assert store.verify(token_b) is not None


def test_reload_from_disk_preserves_hashes(tmp_path, monkeypatch):
    monkeypatch.setenv("LOOM_ENV", "development")
    store = _store(tmp_path)
    _, token = store.issue("user_a", org_id="org_1")
    reloaded = ApiTokenStore(storage_dir=str(tmp_path / "tokens"))
    assert reloaded.verify(token).user_id == "user_a"
    assert reloaded.verify(f"{token}x") is None


def test_production_disables_token_admin_by_default(tmp_path, monkeypatch):
    monkeypatch.setenv("LOOM_ENV", "production")
    monkeypatch.delenv("LOOM_TOKEN_ADMIN_ENABLED", raising=False)
    store = _store(tmp_path)

    with pytest.raises(TokenAdministrationDisabled):
        store.issue("user_a", org_id="org_1")


def test_production_blocks_direct_registry_enumeration(tmp_path, monkeypatch):
    monkeypatch.setenv("LOOM_ENV", "development")
    store = _store(tmp_path)
    store.issue("user_a", org_id="org_1")

    monkeypatch.setenv("LOOM_ENV", "production")
    monkeypatch.delenv("LOOM_TOKEN_ADMIN_ENABLED", raising=False)

    with pytest.raises(TokenAdministrationDisabled):
        list(store._records.values())


def test_production_still_allows_token_verification(tmp_path, monkeypatch):
    monkeypatch.setenv("LOOM_ENV", "development")
    store = _store(tmp_path)
    _, token = store.issue("user_a", org_id="org_1")

    monkeypatch.setenv("LOOM_ENV", "production")
    monkeypatch.delenv("LOOM_TOKEN_ADMIN_ENABLED", raising=False)

    assert store.verify(token) is not None
