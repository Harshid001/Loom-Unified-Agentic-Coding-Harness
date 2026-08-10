import logging
import subprocess
from typing import Dict, List

from pydantic import BaseModel, Field

logger = logging.getLogger("loom.repo_intel.git_history")


class CommitInfo(BaseModel):
    commit_hash: str
    author: str
    date: str
    message: str
    files_changed: List[str] = Field(default_factory=list)

class GitHistoryAnalyzer:
    """Analyzes Git history, file churn, and recent commits in the repository."""

    def get_recent_commits(self, repo_path: str, max_count: int = 10) -> List[CommitInfo]:
        commits: List[CommitInfo] = []
        try:
            cmd = ["git", "log", f"-n{max_count}", "--pretty=format:%H|%an|%ad|%s", "--name-only"]
            res = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, check=True)

            blocks = res.stdout.strip().split("\n\n")
            for block in blocks:
                lines = [line_str.strip() for line_str in block.splitlines() if line_str.strip()]
                if not lines:
                    continue
                header = lines[0].split("|")
                if len(header) >= 4:
                    commit_hash, author, date, message = header[0], header[1], header[2], header[3]
                    files = lines[1:]
                    commits.append(CommitInfo(
                        commit_hash=commit_hash[:8],
                        author=author,
                        date=date,
                        message=message,
                        files_changed=files
                    ))
        except (subprocess.CalledProcessError, FileNotFoundError, OSError, ValueError) as err:
            logger.warning("Failed to retrieve git history for %s: %s", repo_path, err)

        return commits

    def get_file_churn(self, repo_path: str, max_commits: int = 50) -> Dict[str, int]:
        churn: Dict[str, int] = {}
        try:
            cmd = ["git", "log", f"-n{max_commits}", "--name-only", "--pretty=format:"]
            res = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, check=True)
            for line in res.stdout.splitlines():
                f = line.strip()
                if f:
                    churn[f] = churn.get(f, 0) + 1
        except (subprocess.CalledProcessError, FileNotFoundError, OSError) as err:
            logger.warning("Failed to retrieve git file churn for %s: %s", repo_path, err)

        return churn

