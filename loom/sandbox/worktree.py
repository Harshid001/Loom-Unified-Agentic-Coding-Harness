import logging
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger("loom.sandbox.worktree")

_LABEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]{0,79}$")

SNAPSHOT_IGNORED_PATTERNS = (
    ".loom_snapshots",
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "env",
    ".next",
    "dist",
    "build",
    "out",
    ".turbo",
    "target",
    "bin",
    "obj",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "coverage",
    "htmlcov",
    ".cache",
    ".pnpm-store",
    ".yarn",
    "*.tsbuildinfo",
    "*.pyc",
    "*.pyo",
    "*.pyd",
    "*.egg-info",
    ".DS_Store",
    "Thumbs.db",
)


def _safe_snapshot_label(label: str) -> str:
    value = str(label or "snapshot").strip()
    if not _LABEL_RE.fullmatch(value) or value in {".", ".."}:
        raise ValueError("Invalid snapshot label")
    return value


def _copy_tree_no_links(source: Path, destination: Path) -> None:
    for item in source.iterdir():
        dest = destination / item.name
        if item.is_symlink():
            raise ValueError(f"Symlink is not permitted in snapshot restore: {item}")
        if item.is_dir():
            dest.mkdir(parents=True, exist_ok=True)
            _copy_tree_no_links(item, dest)
        else:
            shutil.copy2(item, dest)


def _snapshot_sort_key(p: Path) -> tuple[int, float]:
    parts = p.name.split("_", 2)
    if len(parts) >= 2 and parts[1].isdigit():
        return (int(parts[1]), p.stat().st_mtime)
    return (0, p.stat().st_mtime)


@dataclass(frozen=True)
class WorktreeHandle:
    snapshot_id: str
    worktree_path: str

    def __str__(self) -> str:
        return self.worktree_path

    def __fspath__(self) -> str:
        return self.worktree_path


class WorktreeManager:
    """Manages Git worktree snapshots for zero-risk rollback before patch applications.

    Includes automatic snapshot pruning and heavy build artifact filtering (.next, dist,
    node_modules, venvs, caches) to prevent runaway disk usage.
    """

    def __init__(self, repo_path: str, max_retained_snapshots: int = 3, max_age_seconds: int = 86400):
        self.repo_path = Path(repo_path).resolve()
        self.snapshots: Dict[str, str] = {}
        self.max_retained_snapshots = max(1, max_retained_snapshots)
        self.max_age_seconds = max_age_seconds

    def prune_snapshots(self, max_retained: Optional[int] = None, max_age_seconds: Optional[int] = None) -> int:
        """Prunes stale or excess snapshots from disk, keeping only the most recent."""
        snapshots_root = (self.repo_path / ".loom_snapshots").resolve()
        if not snapshots_root.exists() or not snapshots_root.is_dir():
            return 0

        retained_limit = self.max_retained_snapshots if max_retained is None else max(0, max_retained)
        age_limit = self.max_age_seconds if max_age_seconds is None else max_age_seconds
        now = time.time()
        removed_count = 0

        try:
            # Collect all existing snapshot directories
            entries: List[Path] = [
                d for d in snapshots_root.iterdir() if d.is_dir() and d.name.startswith("snap_")
            ]
            # Sort by snapshot timestamp key (oldest first)
            entries.sort(key=_snapshot_sort_key)

            for entry in list(entries):
                st_mtime = entry.stat().st_mtime
                is_expired = (now - st_mtime) > age_limit
                is_over_limit = len(entries) > retained_limit

                if is_expired or is_over_limit:
                    snap_id = entry.name
                    self._remove_snapshot_dir(entry, snap_id)
                    entries.remove(entry)
                    removed_count += 1
        except Exception as err:
            logger.warning("Error while pruning snapshots: %s", err)

        return removed_count

    def _remove_snapshot_dir(self, path: Path, snapshot_id: str) -> None:
        try:
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(path)],
                cwd=self.repo_path,
                capture_output=True,
            )
        except (subprocess.CalledProcessError, FileNotFoundError, OSError):
            pass

        if path.exists():
            shutil.rmtree(path, ignore_errors=True)

        if snapshot_id in self.snapshots:
            del self.snapshots[snapshot_id]

    def create_snapshot(self, label: str) -> str:
        # Automatically prune old snapshots before creating a new one to cap disk usage
        self.prune_snapshots(max_retained=self.max_retained_snapshots - 1)

        safe_label = _safe_snapshot_label(label)
        snapshot_id = f"snap_{time.time_ns()}_{safe_label}"
        snapshot_dir = (self.repo_path / ".loom_snapshots" / snapshot_id).resolve()
        snapshots_root = (self.repo_path / ".loom_snapshots").resolve()
        if snapshots_root not in snapshot_dir.parents:
            raise ValueError("Snapshot path escaped repository snapshots root")
        snapshot_dir.parent.mkdir(parents=True, exist_ok=True)

        try:
            if not (self.repo_path / ".git").exists():
                raise OSError(f"{self.repo_path} is not a git repository root")
            cmd = ["git", "worktree", "add", "-b", f"loom/{snapshot_id}", str(snapshot_dir), "HEAD"]
            subprocess.run(cmd, cwd=self.repo_path, capture_output=True, check=True)
            self.snapshots[snapshot_id] = str(snapshot_dir)
        except (subprocess.CalledProcessError, FileNotFoundError, OSError) as err:
            logger.info("Git worktree creation failed for %s (%s), falling back to directory copy", snapshot_id, err)
            if snapshot_dir.exists():
                shutil.rmtree(snapshot_dir, ignore_errors=True)
            shutil.copytree(
                self.repo_path,
                snapshot_dir,
                ignore=shutil.ignore_patterns(*SNAPSHOT_IGNORED_PATTERNS),
                symlinks=False,
            )
            self.snapshots[snapshot_id] = str(snapshot_dir)

        return snapshot_id

    def create_worktree(self, label: str) -> WorktreeHandle:
        """Backward-compatible object API exposing the materialized worktree path."""
        snapshot_id = self.create_snapshot(label)
        return WorktreeHandle(snapshot_id=snapshot_id, worktree_path=self.snapshots[snapshot_id])

    def restore_snapshot(self, snapshot_id: str) -> bool:
        if snapshot_id not in self.snapshots:
            candidate = (self.repo_path / ".loom_snapshots" / snapshot_id).resolve()
            snapshots_root = (self.repo_path / ".loom_snapshots").resolve()
            if candidate.exists() and candidate.is_dir() and snapshots_root in candidate.parents:
                self.snapshots[snapshot_id] = str(candidate)
            else:
                return False

        snapshot_path = Path(self.snapshots[snapshot_id]).resolve()
        snapshots_root = (self.repo_path / ".loom_snapshots").resolve()
        if snapshots_root not in snapshot_path.parents or not snapshot_path.exists():
            return False

        try:
            snapshot_items = {item.name for item in snapshot_path.iterdir()}
            # Remove untracked files/directories in repo_path that were created after snapshot
            for repo_item in self.repo_path.iterdir():
                if repo_item.name in {".git", ".loom_snapshots"}:
                    continue
                if repo_item.name not in snapshot_items:
                    if repo_item.is_dir() and not repo_item.is_symlink():
                        shutil.rmtree(repo_item, ignore_errors=True)
                    else:
                        try:
                            repo_item.unlink()
                        except OSError:
                            pass

            for item in snapshot_path.iterdir():
                if item.name in [".git", ".loom_snapshots"]:
                    continue
                if item.is_symlink():
                    raise ValueError(f"Symlink is not permitted in snapshot restore: {item}")
                dest = (self.repo_path / item.name).resolve()
                if self.repo_path not in dest.parents and dest != self.repo_path:
                    return False
                if item.is_dir():
                    if dest.exists():
                        shutil.rmtree(dest, ignore_errors=True)
                    _copy_tree_no_links(item, dest)
                else:
                    shutil.copy2(item, dest)
            return True
        except (OSError, IOError, shutil.Error, ValueError) as err:
            logger.error("Failed to restore snapshot %s: %s", snapshot_id, err)
            return False

    def cleanup_snapshot(self, snapshot_id: str) -> None:
        snapshots_root = (self.repo_path / ".loom_snapshots").resolve()
        target_path: Optional[Path] = None

        if snapshot_id in self.snapshots:
            target_path = Path(self.snapshots[snapshot_id]).resolve()
        else:
            candidate = (snapshots_root / snapshot_id).resolve()
            if candidate.exists() and snapshots_root in candidate.parents:
                target_path = candidate

        if target_path and snapshots_root in target_path.parents:
            self._remove_snapshot_dir(target_path, snapshot_id)

    def cleanup_all_snapshots(self) -> int:
        """Removes all snapshots in .loom_snapshots directory."""
        return self.prune_snapshots(max_retained=0, max_age_seconds=0)

    def cleanup_worktree(self, worktree_id: str) -> None:
        """Backward-compatible alias for cleanup_snapshot()."""
        self.cleanup_snapshot(worktree_id)
