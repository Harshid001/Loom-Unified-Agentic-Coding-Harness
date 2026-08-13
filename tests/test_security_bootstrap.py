import pytest

from loom.runtime.bootstrap import is_production, validate_authentication_environment


def test_missing_environment_is_production_like(monkeypatch):
    monkeypatch.delenv("LOOM_ENV", raising=False)
    monkeypatch.delenv("DEV_MODE", raising=False)
    monkeypatch.delenv("API_KEY", raising=False)

    assert is_production() is True
    with pytest.raises(RuntimeError, match="API_KEY is required"):
        validate_authentication_environment()


def test_production_requires_api_key(monkeypatch):
    monkeypatch.setenv("LOOM_ENV", "production")
    monkeypatch.delenv("DEV_MODE", raising=False)
    monkeypatch.delenv("API_KEY", raising=False)

    assert is_production() is True
    with pytest.raises(RuntimeError, match="API_KEY is required"):
        validate_authentication_environment()


def test_explicit_development_mode_allows_startup(monkeypatch):
    monkeypatch.setenv("LOOM_ENV", "development")
    monkeypatch.setenv("DEV_MODE", "true")
    monkeypatch.delenv("API_KEY", raising=False)

    assert is_production() is False
    validate_authentication_environment()


def test_development_without_explicit_bypass_still_requires_api_key(monkeypatch):
    monkeypatch.setenv("LOOM_ENV", "development")
    monkeypatch.delenv("DEV_MODE", raising=False)
    monkeypatch.delenv("API_KEY", raising=False)

    assert is_production() is True
    with pytest.raises(RuntimeError, match="API_KEY is required"):
        validate_authentication_environment()


def test_development_with_api_key_is_allowed_without_bypass(monkeypatch):
    monkeypatch.setenv("LOOM_ENV", "development")
    monkeypatch.delenv("DEV_MODE", raising=False)
    monkeypatch.setenv("API_KEY", "test-api-key")

    assert is_production() is True
    validate_authentication_environment()
