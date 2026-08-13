import hashlib
import hmac

import pytest

from loom.api.hardening import RedisRateLimiter, ProductionSecurityError, validate_webhook_url, verify_webhook_signature
from loom.sandbox.worktree import _safe_snapshot_label


def test_snapshot_label_rejects_traversal():
    with pytest.raises(ValueError):
        _safe_snapshot_label("../../outside")
    assert _safe_snapshot_label("safe-label_01") == "safe-label_01"


def test_webhook_url_requires_https_and_allowlisted_host(monkeypatch):
    with pytest.raises(Exception):
        validate_webhook_url("http://hooks.slack.com/services/test")
    with pytest.raises(Exception):
        validate_webhook_url("https://example.com/hook")


def test_webhook_signature_verification(monkeypatch):
    body = b'{"action":"opened"}'
    secret = "super-secret"
    signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    monkeypatch.setenv("LOOM_ENV", "production")
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", secret)
    headers = {"x-hub-signature-256": signature}
    assert verify_webhook_signature("/api/v1/integrations/github/webhook", headers, body) is True
    headers["x-hub-signature-256"] = "sha256=bad"
    assert verify_webhook_signature("/api/v1/integrations/github/webhook", headers, body) is False


@pytest.mark.asyncio
async def test_local_rate_limiter_enforces_limit(monkeypatch):
    monkeypatch.setenv("LOOM_ENV", "development")
    monkeypatch.delenv("REDIS_URL", raising=False)
    limiter = RedisRateLimiter(limit=2, window_seconds=60)
    assert await limiter.allow("key") is True
    assert await limiter.allow("key") is True
    assert await limiter.allow("key") is False


@pytest.mark.asyncio
async def test_production_requires_redis_unless_explicit_fallback(monkeypatch):
    monkeypatch.setenv("LOOM_ENV", "production")
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("RATE_LIMIT_ALLOW_LOCAL_FALLBACK", raising=False)
    limiter = RedisRateLimiter(limit=1)
    with pytest.raises(ProductionSecurityError):
        await limiter.allow("key")
