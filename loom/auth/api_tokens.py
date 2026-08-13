"""Per-user API token registry with at-rest hashing.

Verification remains available to API authentication. Administrative operations are
explicitly disabled in production unless the privileged control-plane feature flag is
enabled; direct enumeration of the internal registry is guarded as well.
"""

import hashlib
import json
import logging
import os
import secrets
import time
import uuid
from pathlib import Path
from typing import Iterable, List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger("loom.auth.api_tokens")

