from pathlib import Path

from loom.sandbox.firecracker_sandbox import FirecrackerSandbox


def test_firecracker_provider_fails_closed_without_worker(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("LOOM_FIRECRACKER_WORKER_SOCKET", raising=False)
    monkeypatch.delenv("LOOM_FIRECRACKER_WORKER_CMD", raising=False)

    result = FirecrackerSandbox(str(tmp_path)).run_command(["python", "-c", "print(1)"])

    assert result.exit_code == 125
    assert "LOOM_FIRECRACKER_WORKER_SOCKET" in result.stderr
