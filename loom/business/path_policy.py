"""Sensitive-path protection for the commit gateway (spec §3.4).

Deterministic, unit-testable policy evaluation: parse the paths touched by a
patch, match them against the org's `sensitive_path_globs`, and decide whether
the patch may proceed. The PatcherAgent enforces the decision before any
`git apply`, so sensitive files (auth, billing, migrations, vault refs) can
never be modified by an unattended run.
"""

import fnmatch
from dataclasses import dataclass, field
from typing import List, Optional

from loom.business.models import Organization

DEFAULT_SENSITIVE_GLOBS: List[str] = [
    "**/auth/**",
    "**/billing/**",
    "**/migrations/**",
    "**/secrets/**",
    "**/.env",
    "**/*.pem",
]


def extract_touched_paths(patch_diff: str) -> List[str]:
    """Parse `+++ b/...` lines from a unified diff into normalized repo paths."""
    touched: List[str] = []
    for line in patch_diff.splitlines():
        if line.startswith("+++ "):
            path = line[4:].replace("\t", " ").strip()
            if not path or path == "/dev/null":
                continue
            path = path.split(" ", 1)[0]
            if path.startswith("b/"):
                path = path[2:]
            elif path.startswith("a/"):
                path = path[2:]
            elif path.startswith("/"):
                continue
            if path and path not in touched:
                touched.append(path)
    return touched


def matches_sensitive_glob(path: str, globs: Optional[List[str]] = None) -> bool:
    candidates = globs if globs is not None else DEFAULT_SENSITIVE_GLOBS
    normalized = path.replace("\\", "/")
    if normalized.startswith("./"):
        normalized = normalized[2:]
    for pattern in candidates:
        norm_pattern = pattern.replace("\\", "/").lstrip("./")
        if fnmatch.fnmatch(normalized, norm_pattern):
            return True
        if "/" in norm_pattern and fnmatch.fnmatch(normalized, norm_pattern.lstrip("**/")):
            return True
    return False


def sensitive_paths_in_patch(patch_diff: str, org: Optional[Organization] = None) -> List[str]:
    globs = list(org.sensitive_path_globs) if org is not None else DEFAULT_SENSITIVE_GLOBS
    return [p for p in extract_touched_paths(patch_diff) if matches_sensitive_glob(p, globs)]


@dataclass
class CommitGatewayDecision:
    allowed: bool
    blocked_paths: List[str] = field(default_factory=list)
    reason: str = ""
    status: str = "allowed"

    def __bool__(self) -> bool:
        return self.allowed


def evaluate_commit_gateway(
    patch_diff: str,
    org: Optional[Organization] = None,
    allow_with_audit: bool = False,
) -> CommitGatewayDecision:
    """Commit gateway (spec §3.4): block patches touching sensitive paths.

    - Default policy: block (hard denial) → status `security_hold`.
    - `allow_with_audit=True`: permit but flag the run for review (`audit_only`).
    """
    blocked = sensitive_paths_in_patch(patch_diff, org)
    if not blocked:
        return CommitGatewayDecision(allowed=True, status="allowed")
    if allow_with_audit:
        return CommitGatewayDecision(
            allowed=True,
            blocked_paths=blocked,
            reason=f"Sensitive paths touched, flagged for review: {', '.join(blocked)}",
            status="audit_only",
        )
    return CommitGatewayDecision(
        allowed=False,
        blocked_paths=blocked,
        reason=f"Sensitive paths blocked by commit gateway: {', '.join(blocked)}",
        status="security_hold",
    )


@dataclass
class PatchApprovalPolicy:
    """Configurable patch risk & human review governance policy (compliance-auditable)."""

    max_autonomous_diff_lines: int = 150
    min_autonomous_confidence: float = 0.60
    require_human_signoff: bool = False
    sensitive_path_globs: List[str] = field(default_factory=lambda: list(DEFAULT_SENSITIVE_GLOBS))

    @classmethod
    def enterprise_default(cls) -> "PatchApprovalPolicy":
        """Strict enterprise-grade compliance policy: tighter line limits, higher confidence, mandatory signoff."""
        return cls(
            max_autonomous_diff_lines=75,
            min_autonomous_confidence=0.85,
            require_human_signoff=True,
        )

    def classify_risk(
        self,
        diff_size: int,
        touched_files: List[str],
        prior_confidence: Optional[float] = None,
    ) -> bool:
        """Classify whether a proposed patch carries high risk and requires manual approval/consensus."""
        # 1. Path sensitivity check
        for file_path in touched_files:
            clean = file_path.strip().removeprefix("b/").removeprefix("a/")
            if matches_sensitive_glob(clean, self.sensitive_path_globs) or matches_sensitive_glob(
                file_path, self.sensitive_path_globs
            ):
                return True

        # 2. Diff line count threshold
        if diff_size > self.max_autonomous_diff_lines:
            return True

        # 3. Model confidence threshold
        if prior_confidence is not None and prior_confidence < self.min_autonomous_confidence:
            return True

        return False

