"""Tests for WorktreeManager snapshot pruning and artifact filtering."""

import time

from loom.sandbox.worktree import WorktreeManager


def test_worktree_ignores_heavy_build_artifacts(tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()

    # Create source files
    (repo_dir / "src").mkdir()
    (repo_dir / "src" / "index.ts").write_text("console.log('hello')")

    # Create heavy build/cache files that should be ignored
    (repo_dir / ".next").mkdir()
    (repo_dir / ".next" / "heavy_bundle.js").write_text("x" * 10000)
    (repo_dir / "node_modules").mkdir()
    (repo_dir / "node_modules" / "pkg.js").write_text("y" * 10000)
    (repo_dir / "dist").mkdir()
    (repo_dir / "dist" / "output.js").write_text("z" * 10000)
    (repo_dir / "__pycache__").mkdir()
    (repo_dir / "__pycache__" / "cached.pyc").write_text("c" * 10000)

    manager = WorktreeManager(str(repo_dir), max_retained_snapshots=3)
    snap_id = manager.create_snapshot("test_ignore")
    snap_dir = repo_dir / ".loom_snapshots" / snap_id

    try:
        assert snap_dir.exists()
        # Source file must exist in snapshot
        assert (snap_dir / "src" / "index.ts").exists()
        # Heavy build and cache directories must NOT exist in snapshot
        assert not (snap_dir / ".next").exists()
        assert not (snap_dir / "node_modules").exists()
        assert not (snap_dir / "dist").exists()
        assert not (snap_dir / "__pycache__").exists()
    finally:
        manager.cleanup_snapshot(snap_id)


def test_worktree_auto_prunes_older_snapshots(tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    (repo_dir / "app.py").write_text("print('app')")

    # Manager configured to retain max 2 snapshots
    manager = WorktreeManager(str(repo_dir), max_retained_snapshots=2)

    snap1 = manager.create_snapshot("snap1")
    time.sleep(0.05)
    manager.create_snapshot("snap2")
    time.sleep(0.05)

    snapshots_dir = repo_dir / ".loom_snapshots"
    assert len(list(snapshots_dir.glob("snap_*"))) <= 2

    # Creating a 3rd snapshot should automatically prune snap1
    snap3 = manager.create_snapshot("snap3")

    current_snaps = [d.name for d in snapshots_dir.glob("snap_*")]
    assert len(current_snaps) <= 2
    assert snap3 in current_snaps
    assert snap1 not in current_snaps


def test_cleanup_all_snapshots(tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    (repo_dir / "main.py").write_text("print(1)")

    manager = WorktreeManager(str(repo_dir), max_retained_snapshots=5)
    manager.create_snapshot("s1")
    manager.create_snapshot("s2")

    snapshots_dir = repo_dir / ".loom_snapshots"
    assert len(list(snapshots_dir.glob("snap_*"))) >= 1

    removed = manager.cleanup_all_snapshots()
    assert removed >= 1
    assert len(list(snapshots_dir.glob("snap_*"))) == 0
