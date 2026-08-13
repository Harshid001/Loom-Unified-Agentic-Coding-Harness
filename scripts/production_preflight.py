"""Production readiness preflight checks.

This command is intentionally deterministic and does not mutate infrastructure.
It validates the configuration surface and the local artifacts required before a
production deployment is attempted.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REQUIRED_PRODUCTION_VARS = (
    "LOOM_ENV",
    "API_KEY",
    "DASHBOARD_AUTH_TOKEN",
    "ALLOWED_REPO_ROOTS",
    "DATABASE_URL",
    "REDIS_URL",
    "LOOM_FIRECRACKER_WORKER_URL",
    "LOOM_FIRECRACKER_WORKER_TOKEN",
    "LOOM_BACKUP_ENCRYPTION_KEY",
)

PLACEHOLDER_MARKERS = (
    "your-",
    "replace-with-",
    "changeme",
    "example",
    "password@",
)


def _is_placeholder(value: str) -> bool:
    lowered = value.strip().lower()
    return not lowered or any(marker in lowered for marker in PLACEHOLDER_MARKERS)


def validate_environment(*, allow_placeholders: bool = False) -> list[str]:
    errors: list[str] = []

    if os.getenv("LOOM_ENV", "").strip().lower() not in {"prod", "production"}:
        errors.append("LOOM_ENV must be 'production' for the production preflight")

    for name in REQUIRED_PRODUCTION_VARS:
        value = os.getenv(name)
        if not value:
            errors.append(f"{name} is not configured")
        elif not allow_placeholders and name != "LOOM_ENV" and _is_placeholder(value):
            errors.append(f"{name} contains a placeholder value")

    if os.getenv("LOOM_TOKEN_ADMIN_ENABLED", "false").strip().lower() in {"1", "true", "yes"}:
        errors.append("LOOM_TOKEN_ADMIN_ENABLED must remain false until the privileged control-plane is deployed")

    if os.getenv("RATE_LIMIT_ALLOW_LOCAL_FALLBACK", "false").strip().lower() in {"1", "true", "yes"}:
        errors.append("RATE_LIMIT_ALLOW_LOCAL_FALLBACK must be false in production")

    return errors


def validate_artifacts(repo_root: Path) -> list[str]:
    errors: list[str] = []
    required_files = (
        repo_root / "pyproject.toml",
        repo_root / "web" / "package.json",
        repo_root / ".github" / "workflows" / "ci.yml",
        repo_root / ".env.example",
        repo_root / "docs" / "deployment.md",
    )
    for path in required_files:
        if not path.exists():
            errors.append(f"missing required repository artifact: {path.relative_to(repo_root)}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Loom production deployment prerequisites")
    parser.add_argument("--repo-root", default=".", help="Repository root to inspect")
    parser.add_argument(
        "--allow-placeholders",
        action="store_true",
        help="Allow placeholder values; useful for CI schema validation",
    )
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    errors = validate_environment(allow_placeholders=args.allow_placeholders)
    errors.extend(validate_artifacts(repo_root))

    if errors:
        print("PRODUCTION PREFLIGHT: FAILED")
        for error in errors:
            print(f"- {error}")
        return 1

    print("PRODUCTION PREFLIGHT: PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
