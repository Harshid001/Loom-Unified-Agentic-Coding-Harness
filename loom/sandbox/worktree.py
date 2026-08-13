import logging
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Dict

logger = logging.getLogger("loom.sandbox.worktree")

_LABEL_RE = re.compile(r"^[A-Za-z0-9 ._\-()#+,]{1,80}$")


def _safe_snapshot_label(label: str) -> str:
    value = str(label or "snapshot").strip()
    if not _LABEL_RE.fullmatch(value) or value in {".", ".."}:
        raise ValueError("Invalid snapshot label")
    return value


def _snapshot_slug(label: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", label).strip("-")
    return slug or "snapshot"


class WorktreeManager:
    """Manages Git worktree snapshots for zero-risk rollback before patch applications."""

    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path).resolve()
        self.snapshots: Dict[str, str] = {}

    def create_snapshot(self, label: str) -> str:
        safe_label = _safe_snapshot_label(label)
        snapshot_id = f"snap_{int(time.time())}_{_snapshot_slug(safe_label)}"
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
                ignore=shutil.ignore_patterns(".loom_snapshots", ".venv", "node_modules", ".git"),
            )
            self.snapshots[snapshot_id] = str(snapshot_dir)

        return snapshot_id

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
            for item in snapshot_path.iterdir():
                if item.name in [".git", ".loom_snapshots"]:
                    continue
                dest = (self.repo_path / item.name).resolve()
                if self.repo_path not in dest.parents and dest != self.repo_path:
                    return False
                if item.is_dir():
                    if dest.exists():
                        shutil.rmtree(dest, ignore_errors=True)
                    shutil.copytree(item, dest)
                else:
                    shutil.copy2(item, dest)
            return True
        except (OSError, IOError, shutil.Error) as err:
            logger.error("Failed to restore snapshot %s: %s", snapshot_id, err)
            return False

    def cleanup_snapshot(self, snapshot_id: str):
        if snapshot_id in self.snapshots:
            path = Path(self.snapshots[snapshot_id]).resolve()
            snapshots_root = (self.repo_path / ".loom_snapshots").resolve()
            if snapshots_root not in path.parents:
                return
            if path.exists():
                try:
                    subprocess.run(
                        ["git", "worktree", "remove", "--force", str(path)], cwd=self.repo_path, capture_output=True
                    )
                except (subprocess.CalledProcessError, FileNotFoundError, OSError) as err:
                    logger.warning("Worktree cleanup warning for %s: %s", snapshot_id, err)
                if path.exists():
                    shutil.rmtree(path, ignore_errors=True)
            del self.snapshots[snapshot_id]
