import os  # noqa: I001


# Tests exercise the development behavior explicitly; production/runtime code
# defaults to the fail-closed posture when these variables are absent.
os.environ.setdefault("LOOM_ENV", "development")
os.environ.setdefault("DEV_MODE", "true")
# Allow in-memory rate-limit fallback so tests that temporarily switch to
# LOOM_ENV=production don't require a live Redis instance.
os.environ.setdefault("RATE_LIMIT_ALLOW_LOCAL_FALLBACK", "true")
# Provide a Fernet-compatible key for webhook secret encryption in tests.
os.environ.setdefault("LOOM_BACKUP_ENCRYPTION_KEY", "TENb1wM_WPGIrSSzFhBeRXjzszrMF2iJcEagUCfRltA=")
