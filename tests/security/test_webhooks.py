"""PRD-018 — Webhook Security Tests.

Verifies the WebhookSignatureMiddleware:
  1. Blocks requests with missing/invalid HMAC signatures (GitHub)
  2. Blocks requests with missing/invalid token (GitLab)
  3. Passes valid signatures through to handlers
  4. Fixes the double-body-read bug: handler receives full body after middleware reads it
  5. Allows unsigned requests in dev mode when no secret is configured
  6. Blocks unsigned requests in production when no secret is configured
"""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

from loom.api.app import create_app
from loom.api.dependencies import reset_entitlements
from loom.db.records_store import reset_run_record_store


GITHUB_WEBHOOK_PATH = "/api/v1/integrations/github/webhook"
GITLAB_WEBHOOK_PATH = "/api/v1/integrations/gitlab/webhook"

_GITHUB_SECRET = "github-test-secret-xyz"
_GITLAB_SECRET = "gitlab-test-secret-xyz"

_SAMPLE_GITHUB_PAYLOAD = json.dumps({
    "action": "opened",
    "issue": {"title": "Test issue", "number": 42, "labels": []},
    "repository": {"full_name": "myorg/myrepo"},
    "sender": {"login": "user1"},
}).encode()

_SAMPLE_GITLAB_PAYLOAD = json.dumps({
    "object_kind": "issue",
    "object_attributes": {"title": "Test issue", "iid": 7, "labels": []},
    "project": {"path_with_namespace": "mygroup/myproject"},
    "user": {"username": "user1"},
}).encode()


def _github_sig(body: bytes, secret: str = _GITHUB_SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def dev_app(monkeypatch):
    """App in dev mode with no webhook secrets (permissive)."""
    monkeypatch.delenv("GITHUB_WEBHOOK_SECRET", raising=False)
    monkeypatch.delenv("GITLAB_WEBHOOK_SECRET", raising=False)
    monkeypatch.setenv("LOOM_ENV", "development")
    monkeypatch.setenv("API_KEY", "test-key")
    reset_entitlements()
    reset_run_record_store()
    return TestClient(create_app())


@pytest.fixture()
def prod_app(monkeypatch):
    """App in production mode with no webhook secrets (should reject all)."""
    monkeypatch.delenv("GITHUB_WEBHOOK_SECRET", raising=False)
    monkeypatch.delenv("GITLAB_WEBHOOK_SECRET", raising=False)
    monkeypatch.setenv("LOOM_ENV", "production")
    monkeypatch.setenv("API_KEY", "test-key")
    reset_entitlements()
    reset_run_record_store()
    return TestClient(create_app())


@pytest.fixture()
def secured_app(monkeypatch):
    """App with both GitHub and GitLab secrets configured."""
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", _GITHUB_SECRET)
    monkeypatch.setenv("GITLAB_WEBHOOK_SECRET", _GITLAB_SECRET)
    monkeypatch.setenv("LOOM_ENV", "development")
    monkeypatch.setenv("API_KEY", "test-key")
    reset_entitlements()
    reset_run_record_store()
    return TestClient(create_app())


# ---------------------------------------------------------------------------
# GitHub — HMAC signature tests
# ---------------------------------------------------------------------------


def test_github_valid_signature_passes(secured_app):
    """Request with correct HMAC signature must reach the handler (200)."""
    sig = _github_sig(_SAMPLE_GITHUB_PAYLOAD)
    resp = secured_app.post(
        GITHUB_WEBHOOK_PATH,
        content=_SAMPLE_GITHUB_PAYLOAD,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": sig,
            "X-API-Key": "test-key",
        },
    )
    assert resp.status_code == 200, resp.text


def test_github_missing_signature_blocked(secured_app):
    """Request without signature header must be rejected with 401."""
    resp = secured_app.post(
        GITHUB_WEBHOOK_PATH,
        content=_SAMPLE_GITHUB_PAYLOAD,
        headers={"Content-Type": "application/json", "X-API-Key": "test-key"},
    )
    assert resp.status_code == 401


def test_github_wrong_secret_blocked(secured_app):
    """Request with HMAC computed from wrong secret must be rejected with 401."""
    wrong_sig = _github_sig(_SAMPLE_GITHUB_PAYLOAD, secret="wrong-secret")
    resp = secured_app.post(
        GITHUB_WEBHOOK_PATH,
        content=_SAMPLE_GITHUB_PAYLOAD,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": wrong_sig,
            "X-API-Key": "test-key",
        },
    )
    assert resp.status_code == 401


def test_github_tampered_body_blocked(secured_app):
    """HMAC computed on original payload but body swapped — must reject."""
    sig = _github_sig(_SAMPLE_GITHUB_PAYLOAD)
    tampered_body = _SAMPLE_GITHUB_PAYLOAD + b" tampered"
    resp = secured_app.post(
        GITHUB_WEBHOOK_PATH,
        content=tampered_body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": sig,
            "X-API-Key": "test-key",
        },
    )
    assert resp.status_code == 401


def test_github_empty_body_with_matching_signature(secured_app):
    """HMAC of empty body must be checked correctly."""
    empty_body = b""
    sig = _github_sig(empty_body)
    resp = secured_app.post(
        GITHUB_WEBHOOK_PATH,
        content=empty_body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": sig,
            "X-API-Key": "test-key",
        },
    )
    # Empty body is valid JSON-wise; handler should parse gracefully
    assert resp.status_code in (200, 422)


# ---------------------------------------------------------------------------
# GitLab — token tests
# ---------------------------------------------------------------------------


def test_gitlab_valid_token_passes(secured_app):
    """Request with correct GitLab token must reach the handler (200)."""
    resp = secured_app.post(
        GITLAB_WEBHOOK_PATH,
        content=_SAMPLE_GITLAB_PAYLOAD,
        headers={
            "Content-Type": "application/json",
            "X-Gitlab-Token": _GITLAB_SECRET,
            "X-API-Key": "test-key",
        },
    )
    assert resp.status_code == 200, resp.text


def test_gitlab_missing_token_blocked(secured_app):
    """GitLab request without token header must be rejected with 401."""
    resp = secured_app.post(
        GITLAB_WEBHOOK_PATH,
        content=_SAMPLE_GITLAB_PAYLOAD,
        headers={"Content-Type": "application/json", "X-API-Key": "test-key"},
    )
    assert resp.status_code == 401


def test_gitlab_wrong_token_blocked(secured_app):
    """GitLab request with wrong token value must be rejected with 401."""
    resp = secured_app.post(
        GITLAB_WEBHOOK_PATH,
        content=_SAMPLE_GITLAB_PAYLOAD,
        headers={
            "Content-Type": "application/json",
            "X-Gitlab-Token": "wrong-token",
            "X-API-Key": "test-key",
        },
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Production mode: no-secret → reject all
# ---------------------------------------------------------------------------


def test_github_no_secret_prod_mode_blocked(prod_app):
    """In production with no GITHUB_WEBHOOK_SECRET, all inbound webhooks must be blocked."""
    resp = prod_app.post(
        GITHUB_WEBHOOK_PATH,
        content=_SAMPLE_GITHUB_PAYLOAD,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": "sha256=deadbeef",
            "X-API-Key": "test-key",
        },
    )
    assert resp.status_code == 401


def test_gitlab_no_secret_prod_mode_blocked(prod_app):
    """In production with no GITLAB_WEBHOOK_SECRET, all inbound webhooks must be blocked."""
    resp = prod_app.post(
        GITLAB_WEBHOOK_PATH,
        content=_SAMPLE_GITLAB_PAYLOAD,
        headers={
            "Content-Type": "application/json",
            "X-Gitlab-Token": "any-token",
            "X-API-Key": "test-key",
        },
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Dev mode: no-secret → allow through
# ---------------------------------------------------------------------------


def test_github_no_secret_dev_mode_passes(dev_app):
    """In dev mode with no GITHUB_WEBHOOK_SECRET, requests without signatures should pass."""
    resp = dev_app.post(
        GITHUB_WEBHOOK_PATH,
        content=_SAMPLE_GITHUB_PAYLOAD,
        headers={
            "Content-Type": "application/json",
            "X-API-Key": "test-key",
        },
    )
    assert resp.status_code == 200, resp.text


def test_gitlab_no_secret_dev_mode_passes(dev_app):
    """In dev mode with no GITLAB_WEBHOOK_SECRET, requests without tokens should pass."""
    resp = dev_app.post(
        GITLAB_WEBHOOK_PATH,
        content=_SAMPLE_GITLAB_PAYLOAD,
        headers={
            "Content-Type": "application/json",
            "X-API-Key": "test-key",
        },
    )
    assert resp.status_code == 200, resp.text


# ---------------------------------------------------------------------------
# Double-body-read regression test (the core bug being fixed)
# ---------------------------------------------------------------------------


def test_handler_receives_full_body_after_middleware(secured_app):
    """After WebhookSignatureMiddleware reads and verifies the body, the handler
    must also receive the full body (not empty bytes).

    This is the regression test for the double-body-read bug where middleware
    consumed the ASGI receive stream, leaving the handler with an empty body.
    """
    payload = json.dumps({
        "action": "opened",
        "issue": {"title": "Regression body test", "number": 99, "labels": []},
        "repository": {"full_name": "org/body-test-repo"},
        "sender": {"login": "u1"},
    }).encode()

    sig = _github_sig(payload)
    resp = secured_app.post(
        GITHUB_WEBHOOK_PATH,
        content=payload,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": sig,
            "X-API-Key": "test-key",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    # If handler received empty body it would return action="" and repo=""
    assert data.get("repo") == "org/body-test-repo", (
        f"Handler received empty body — double-read bug still present. Got: {data}"
    )
    assert data.get("action") == "opened"


def test_gitlab_handler_receives_full_body_after_middleware(secured_app):
    """Same double-body-read regression test for the GitLab handler."""
    payload = json.dumps({
        "object_kind": "issue",
        "object_attributes": {"title": "GL body test", "iid": 13, "labels": []},
        "project": {"path_with_namespace": "gl/body-repo"},
        "user": {"username": "u2"},
    }).encode()

    resp = secured_app.post(
        GITLAB_WEBHOOK_PATH,
        content=payload,
        headers={
            "Content-Type": "application/json",
            "X-Gitlab-Token": _GITLAB_SECRET,
            "X-API-Key": "test-key",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("repo") == "gl/body-repo", (
        f"Handler received empty body — double-read bug still present. Got: {data}"
    )
    assert data.get("object_kind") == "issue"
