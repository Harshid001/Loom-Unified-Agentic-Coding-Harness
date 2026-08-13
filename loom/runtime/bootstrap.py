"""Fail-closed production configuration validation."""

# ruff: noqa: I001
import os
from pathlib import Path


PRODUCTION_REQUIRED = (
    "API_KEY",
    "DASHBOARD_AUTH_TOKEN",
    "ALLOWED_REPO_ROOTS",
    "LOOM_BACKUP_ENCRYPTION_KEY",
    "LOOM_SANDBOX_WORKER_URL",
    "SANDBOX_WORKER_TOKEN",
    "REDIS_URL",
)


def is_production() -> bool:
    return os.getenv("LOOM_ENV", "development").lower() in {"prod", "production"}


def validate_production_environment() -> None:
    if not is_production():
        return

    missing = [name for name in PRODUCTION_REQUIRED if not os.getenv(name)]
    if missing:
        raise RuntimeError(
            "Production startup blocked: missing required environment variables: "
            + ", ".join(missing)
        )

    roots = [Path(value.strip()).resolve() for value in os.getenv("ALLOWED_REPO_ROOTS", "").split(",") if value.strip()]
    if not roots:
        raise RuntimeError("Production startup blocked: ALLOWED_REPO_ROOTS must contain at least one repository root")

    if os.getenv("LOOM_TOKEN_ADMIN_ENABLED", "false").lower() in {"1", "true", "yes"}:
        raise RuntimeError(
            "Production startup blocked: LOOM_TOKEN_ADMIN_ENABLED requires an explicit privileged control-plane deployment"
        )
