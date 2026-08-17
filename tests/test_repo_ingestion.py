import subprocess
from pathlib import Path

import pytest
from fastapi import HTTPException

from loom.api.server import cleanup_run_workspace, clone_remote_repo, is_git_url


def test_is_git_url_detection():
    # Valid Git URLs
    assert is_git_url("https://github.com/acme/my-repo") is True
    assert is_git_url("http://github.com/acme/my-repo") is True
    assert is_git_url("git@github.com:acme/my-repo.git") is True
    assert is_git_url("github.com/acme/my-repo") is True
    assert is_git_url("https://gitlab.com/acme/project.git") is True
    assert is_git_url("git@gitlab.com:acme/project.git") is True

    # Local paths (should not be detected as git URL)
    assert is_git_url(".") is False
    assert is_git_url("./my-project") is False
    assert is_git_url("/var/repos/app") is False
    assert is_git_url("C:\\Users\\user\\projects\\repo") is False


def test_clone_remote_repo_success(tmp_path, monkeypatch):
    run_id = "test_run_clone_123"

    def mock_subprocess_run(cmd, *args, **kwargs):
        # Create the fake repo directory
        dest_dir = Path(cmd[-1])
        dest_dir.mkdir(parents=True, exist_ok=True)
        (dest_dir / "README.md").write_text("Hello Loom")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="Cloned successfully", stderr="")

    monkeypatch.setattr(subprocess, "run", mock_subprocess_run)

    workspace = clone_remote_repo("https://github.com/acme/repo", run_id)
    assert workspace.exists()
    assert (workspace / "README.md").exists()
    assert run_id in str(workspace)

    # Test cleanup
    cleanup_run_workspace(run_id)
    assert not workspace.exists()


def test_clone_remote_repo_auth_failure(monkeypatch):
    run_id = "test_run_auth_fail"

    def mock_subprocess_run(cmd, *args, **kwargs):
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=128,
            stdout="",
            stderr="fatal: Authentication failed for 'https://github.com/acme/private-repo/'",
        )

    monkeypatch.setattr(subprocess, "run", mock_subprocess_run)

    with pytest.raises(HTTPException) as exc_info:
        clone_remote_repo("https://github.com/acme/private-repo", run_id, token="secret_token")
    assert exc_info.value.status_code == 401
    assert "Authentication failed" in exc_info.value.detail
    assert "secret_token" not in exc_info.value.detail


def test_clone_remote_repo_not_found(monkeypatch):
    run_id = "test_run_not_found"

    def mock_subprocess_run(cmd, *args, **kwargs):
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=128,
            stdout="",
            stderr="fatal: repository 'https://github.com/acme/nonexistent/' not found",
        )

    monkeypatch.setattr(subprocess, "run", mock_subprocess_run)

    with pytest.raises(HTTPException) as exc_info:
        clone_remote_repo("https://github.com/acme/nonexistent", run_id)
    assert exc_info.value.status_code == 404
