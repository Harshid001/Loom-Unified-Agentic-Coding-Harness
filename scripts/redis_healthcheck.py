#!/usr/bin/env python3
"""Check Redis connectivity and basic read/write behavior."""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from urllib.parse import urlparse

from redis import Redis


def validate_redis_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"redis", "rediss"} or not parsed.hostname:
        raise RuntimeError("REDIS_URL must be a Redis URL")


def check(redis_url: str) -> dict[str, object]:
    validate_redis_url(redis_url)
    started = time.perf_counter()
    client = Redis.from_url(
        redis_url,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
    )
    key = f"loom:healthcheck:{time.time_ns()}"
    client.ping()
    client.set(key, "ok", ex=30)
    value = client.get(key)
    client.delete(key)
    latency_ms = (time.perf_counter() - started) * 1000
    try:
        info = client.info(section="server")
    finally:
        client.close()
    if value != "ok":
        raise RuntimeError("Redis SET/GET verification failed")
    return {
        "schema_version": 1,
        "status": "passed",
        "redis_version": info.get("redis_version"),
        "connection_latency_ms": round(latency_ms, 3),
        "timestamp": time.time(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Redis deployment health")
    parser.add_argument("--redis-url", default=os.getenv("REDIS_URL"))
    parser.add_argument("--evidence", type=Path, default=Path("redis-health-evidence.json"))
    args = parser.parse_args()
    if not args.redis_url:
        parser.error("--redis-url or REDIS_URL is required")
    evidence = check(args.redis_url)
    args.evidence.parent.mkdir(parents=True, exist_ok=True)
    args.evidence.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
