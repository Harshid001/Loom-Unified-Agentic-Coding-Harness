from pathlib import Path

from loom.sandbox.firecracker_sandbox import FirecrackerSandbox


def test_firecracker_provider_fails_closed_without_worker(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("LOOM_FIRECRACKER_WORKER_URL", raising=False)
    monkeypatch.delenv("LOOM_FIRECRACKER_WORKER_TOKEN", raising=False)
    monkeypatch.delenv("LOOM_FIRECRACKER_WORKER_CMD", raising=False)

    result = FirecrackerSandbox(str(tmp_path)).run_command(["python", "-c", "print(1)"])

    assert result.exit_code == 125
    assert "LOOM_FIRECRACKER_WORKER_URL" in result.stderr


def test_firecracker_provider_uses_authenticated_worker(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("LOOM_FIRECRACKER_WORKER_URL", "http://worker:8101")
    monkeypatch.setenv("LOOM_FIRECRACKER_WORKER_TOKEN", "secret")

    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"command": "python -c print(1)", "exit_code": 0, "stdout": "1\n", "stderr": "", "duration_seconds": 0.1}

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, json, headers):
            captured.update({"url": url, "json": json, "headers": headers})
            return FakeResponse()

    monkeypatch.setattr("loom.sandbox.firecracker_sandbox.httpx.Client", lambda **kwargs: FakeClient())
    result = FirecrackerSandbox(str(tmp_path)).run_command(["python", "-c", "print(1)"])

    assert result.exit_code == 0
    assert captured["headers"]["Authorization"] == "Bearer secret"
    assert captured["json"]["network"] is False
