# Tests exercise the development behavior explicitly; production/runtime code
# defaults to the fail-closed posture when these variables are absent.

import os

import pytest

os.environ.setdefault("LOOM_ENV", "development")
os.environ.setdefault("DEV_MODE", "true")


@pytest.fixture(autouse=True)
def reset_global_test_state(monkeypatch):
    monkeypatch.setenv("LOOM_ENV", "development")
    monkeypatch.setenv("DEV_MODE", "true")
    from loom.auth.context import clear_principal

    clear_principal()
    yield
    clear_principal()
