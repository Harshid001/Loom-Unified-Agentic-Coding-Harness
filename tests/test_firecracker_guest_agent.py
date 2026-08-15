import json
import tarfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from loom.sandbox import firecracker_guest_agent
from loom.sandbox.firecracker_guest_agent import (
    _exec,
    _handle,
    _safe_extract,
    _validate_env,
)


def test_guest_agent_extract_blocks_absolute_and_parent_paths(tmp_path: Path):
    archive = tmp_path / "bad.tar"
    source = tmp_path / "source"
    source.mkdir()
    (source / "ok.txt").write_text("ok")
    with tarfile.open(archive, "w") as tar:
        tar.add(source / "ok.txt", arcname="../escape.txt")

    with pytest.raises(ValueError, match="tar member escapes"):
        _safe_extract(archive, tmp_path / "out")


def test_guest_agent_extract_blocks_symlink_members(tmp_path: Path):
    archive = tmp_path / "symlink.tar"
    with tarfile.open(archive, "w") as tar:
        info = tarfile.TarInfo("escape")
        info.type = tarfile.SYMTYPE
        info.linkname = "/etc/passwd"
        tar.addfile(info)

    with pytest.raises(ValueError, match="unsupported archive member type"):
        _safe_extract(archive, tmp_path / "out")


def test_guest_agent_extract_valid(tmp_path: Path):
    archive = tmp_path / "good.tar"
    source = tmp_path / "source"
    source.mkdir()
    (source / "hello.txt").write_text("hello world")
    with tarfile.open(archive, "w") as tar:
        tar.add(source / "hello.txt", arcname="hello.txt")

    out_dir = tmp_path / "out"
    _safe_extract(archive, out_dir)
    assert (out_dir / "hello.txt").read_text() == "hello world"


def test_validate_env():
    # Valid env
    valid = _validate_env({"KEY": "value", "OTHER": "123"})
    assert valid == {"KEY": "value", "OTHER": "123"}

    # Forbidden key
    with pytest.raises(ValueError, match="forbidden environment"):
        _validate_env({"LD_PRELOAD": "/bad.so"})

    # Too many env vars
    with pytest.raises(ValueError, match="too many"):
        _validate_env({f"K_{i}": "v" for i in range(129)})

    # Invalid value with null byte
    with pytest.raises(ValueError, match="invalid environment variable value"):
        _validate_env({"KEY": "val\x00ue"})


def test_exec_valid(tmp_path: Path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr(firecracker_guest_agent, "WORKSPACE", workspace)

    result = _exec({"argv": ["python", "-c", "print('guest agent')"], "cwd": str(workspace), "timeout": 5})
    assert result["status"] == "ok"
    assert result["exit_code"] == 0
    assert "guest agent" in result["stdout"]
    assert result["timed_out"] is False


def test_exec_invalid_argv():
    with pytest.raises(ValueError, match="argv must be a non-empty string list"):
        _exec({"argv": []})

    with pytest.raises(ValueError, match="timeout out of range"):
        _exec({"argv": ["echo", "1"], "timeout": 0})


def test_handle_health():
    mock_sock = MagicMock()
    mock_sock.makefile.return_value.readline.return_value = b'{"op":"health"}\n'

    _handle(mock_sock)
    mock_sock.sendall.assert_called_once_with(b'{"status":"ok","runtime":"loom-guest-agent"}\n')


def test_handle_exec(tmp_path: Path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr(firecracker_guest_agent, "WORKSPACE", workspace)

    mock_sock = MagicMock()
    mock_sock.makefile.return_value.readline.return_value = (
        json.dumps({"op": "exec", "argv": ["python", "-c", "print('exec ok')"], "cwd": str(workspace)}).encode() + b"\n"
    )

    _handle(mock_sock)
    assert mock_sock.sendall.called
    sent = mock_sock.sendall.call_args[0][0].decode()
    data = json.loads(sent)
    assert data["status"] == "ok"
    assert "exec ok" in data["stdout"]
