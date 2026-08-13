"""
Loom — Unified Agentic Coding Harness
"""

import os


def _normalize_security_environment() -> None:
    """Make the secure runtime posture the process default.

    Loom only enables its development authentication bypass when both
    ``LOOM_ENV=development`` and ``DEV_MODE=true`` are explicit. Any other
    configuration is treated as production-like so an accidentally exposed
    server cannot inherit the legacy development bypass.
    """
    env = os.getenv("LOOM_ENV", "").strip().lower()
    dev_mode = os.getenv("DEV_MODE", "").strip().lower() in {"1", "true", "yes", "on"}
    if env == "development" and dev_mode:
        return
    if env != "production":
        os.environ["LOOM_ENV"] = "production"


_normalize_security_environment()

__version__ = "0.1.0"
