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
    "LOOM_BACKUP_S3_BUCKET",
    "LOOM_MAX_RUN_COST_USD",
    "LOOM_MAX_RUN_DURATION_SECONDS",
    "LOOM_MAX_RUN_TOKENS",
)

_TRUE_VALUES = {"1", "true", "yes", "on"}


def is_production() -> bool:
    """Return whether Loom is running with a production security posture.

    An unset environment is intentionally treated as production-like for
    security purposes. Development bypasses must be explicit with both
    ``LOOM_ENV=development`` and ``DEV_MODE=true``.
    """
    env = os.getenv("LOOM_ENV", "").strip().lower()
    dev_mode = os.getenv("DEV_MODE", "").strip().lower() in _TRUE_VALUES
    return env in {"", "prod", "production"} or not (env == "development" and dev_mode)


def validate_authentication_environment() -> None:
    """Fail closed unless authentication or explicit development mode is configured.

    This validation is intentionally narrower than the full production bootstrap
    so local server startup can report the authentication requirement without
    requiring every production infrastructure variable at import time.
    """
    env = os.getenv("LOOM_ENV", "").strip().lower()
    dev_mode = os.getenv("DEV_MODE", "").strip().lower() in _TRUE_VALUES

    if env == "development" and dev_mode:
        return

    if not os.getenv("API_KEY"):
        raise RuntimeError(
            "Loom startup blocked: API_KEY is required unless LOOM_ENV=development and DEV_MODE=true."
        )


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

    for name in ("LOOM_MAX_RUN_COST_USD", "LOOM_MAX_RUN_DURATION_SECONDS", "LOOM_MAX_RUN_TOKENS"):
        try:
            if float(os.getenv(name, "0")) <= 0:
                raise ValueError
        except ValueError as exc:
            raise RuntimeError(f"Production startup blocked: {name} must be a positive number") from exc

    if os.getenv("LOOM_TOKEN_ADMIN_ENABLED", "false").lower() in _TRUE_VALUES:
        raise RuntimeError(
            "Production startup blocked: LOOM_TOKEN_ADMIN_ENABLED requires an explicit privileged control-plane deployment"
        )
