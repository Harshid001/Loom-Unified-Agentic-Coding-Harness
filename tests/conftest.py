# Tests exercise the development behavior explicitly; production/runtime code
# defaults to the fail-closed posture when these variables are absent.

import os

os.environ.setdefault("LOOM_ENV", "development")
os.environ.setdefault("DEV_MODE", "true")
