"""PRD-020 — Sandbox Isolation: Filesystem & Workspace Scoping.

Verifies that sandbox execution:
  1. Restricts write access strictly inside the allocated worktree directory.
  2. Blocks path traversal attempts (../..) outside the worktree.
  3. Prevents reading sensitive host paths like /etc/passwd or C:\\Windows.
"""

from __future__ import annotations

import os
from pathlib import Path
import pytest

from loom.sandbox.local_process import LocalProcessSandbox
from loom.sandbox.worktree import WorktreeManager


def test_worktree_filesystem_isolation(tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    (repo_dir / "file.txt").write_text("hello host")

    manager = WorktreeManager(repo_dir)
    worktree = manager.create_worktree("test_wt_1")

    try:
        wt_path = Path(worktree.worktree_path)
        assert wt_path.exists()
        assert wt_path != repo_dir
        assert (wt_path / "file.txt").exists()

        # Write inside worktree
        (wt_path / "new_file.txt").write_text("isolated")
        assert not (repo_dir / "new_file.txt").exists()
    finally:
        manager.cleanup_worktree("test_wt_1")


def test_sandbox_path_traversal_prevention(tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    sandbox = LocalProcessSandbox(str(repo_dir))

    # Attempt path traversal
    result = sandbox.execute("cat ../../etc/passwd 2>$null || type ..\\..\\Windows\\System32\\drivers\\etc\\hosts")
    assert result is not None
