"""Production hardening helpers for request authentication, rate limiting, and SSRF controls."""

from __future__ import annotations

import asyncio
import ipaddress
import os
import socket
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any, Awaitable, Callable
from urllib.parse import urlparse

from fastapi import HTTPException
from fastapi.responses import JSONResponse

# ... existing module content omitted in excerpt ...


def _token_from_headers(headers: dict[str, str]) -> str | None:
    raw = headers.get("authorization") or headers.get("x-api-key") or headers.get("x-dashboard-auth")
    if not raw:
        return None
    if raw.lower().startswith("bearer "):
        return raw[7:].strip()
    return raw.strip()


def valid_api_credential(headers: dict[str, str]) -> bool:
    token = _token_from_headers(headers)
    if not token:
        return False
    configured = os.getenv("API_KEY")
    if configured and token == configured:
        return True
    try:
        from secrets import compare_digest
        from loom.auth.api_tokens import get_api_token_store

        record = get_api_token_store().verify(token)
        return record is not None and compare_digest(record.token_hash, record.token_hash)
    except Exception:
        return False


def trusted_client_ip(scope: dict[str, Any]) -> str:
    client = scope.get("client")
    peer = str(client[0]) if isinstance(client, (tuple, list)) and client else "127.0.0.1"
    trusted_proxy = os.getenv("TRUST_PROXY", "false").lower() in {"1", "true", "yes"}
    if trusted_proxy:
        headers = scope.get("headers", [])
        for key, value in headers:
            if key.lower() == b"x-forwarded-for" and value:
                decoded = value.decode("latin-1") if isinstance(value, (bytes, bytearray)) else str(value)
                return decoded.split(",", 1)[0].strip()
    return peer


# ... rest of existing module content remains unchanged ...

@dataclass
class RateLimitState:
    timestamps: deque[float]


class RedisRateLimiter:
    def __init__(self, limit: int, window_seconds: int = 60):
        self.limit = limit
        self.window = window_seconds
        self._local: dict[str, RateLimitState] = defaultdict(lambda: RateLimitState(deque()))
        self._redis = None

    async def _client(self):
        return self._redis
