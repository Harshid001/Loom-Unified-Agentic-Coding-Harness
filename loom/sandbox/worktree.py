import logging
import shutil
import subprocess
import time
from pathlib import Path
from typing import Dict

logger = logging.getLogger("loom.sandbox.worktree")


class WorktreeManager:
    """Manages Git worktree snapshots for zero-risk rollback before patch applications."""

    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path).resolve()
        self.snapshots: Dict[str, str] = {}

    def create_snapshot(self, label: str) -> str:
        snapshot_id = f"snap_{int(time.time())}_{label}"
        snapshot_dir = self.repo_path / ".loom_snapshots" / snapshot_id
        snapshot_dir.parent.mkdir(parents=True, exist_ok=True)

        try:
            # Attempt git worktree add if repo is a git repo root
            if not (self.repo_path / ".git").exists():
                raise OSError(f"{self.repo_path} is not a git repository root")
            cmd = ["git", "worktree", "add", "-b", f"loom/{snapshot_id}", str(snapshot_dir), "HEAD"]
            subprocess.run(cmd, cwd=self.repo_path, capture_output=True, check=True)
            self.snapshots[snapshot_id] = str(snapshot_dir)
        except (subprocess.CalledProcessError, FileNotFoundError, OSError) as err:
            logger.info("Git worktree creation failed for %s (%s), falling back to directory copy", snapshot_id, err)
            # Fallback copy if not git repo or worktree fails
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
            # PRD-003: Disk lookup fallback for cross-process instance restoration
            candidate = (self.repo_path / ".loom_snapshots" / snapshot_id).resolve()
            snapshots_root = (self.repo_path / ".loom_snapshots").resolve()
            if candidate.exists() and candidate.is_dir() and snapshots_root in candidate.parents:
                self.snapshots[snapshot_id] = str(candidate)
            else:
                return False

        snapshot_path = Path(self.snapshots[snapshot_id])
        if not snapshot_path.exists():
            return False

        try:
            # Restore files back to repo root
            for item in snapshot_path.iterdir():
                if item.name in [".git", ".loom_snapshots"]:
                    continue
                dest = self.repo_path / item.name
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
            path = Path(self.snapshots[snapshot_id])
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
