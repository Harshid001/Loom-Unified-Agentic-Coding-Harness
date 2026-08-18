#!/usr/bin/env python3
"""Probe Loom liveness/readiness endpoints and emit release evidence."""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import httpx


def probe(url: str, timeout: float) -> tuple[int, float, str]:
    started = time.perf_counter()
    response = httpx.get(url, timeout=timeout)
    elapsed = time.perf_counter() - started
    return response.status_code, elapsed, response.text[:500]


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe Loom release health endpoints")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--evidence", type=Path, default=Path("release-health-evidence.json"))
    args = parser.parse_args()

    endpoints = {
        "liveness": f"{args.base_url.rstrip('/')}/healthz",
        "readiness": f"{args.base_url.rstrip('/')}/api/v1/health/readiness",
    }
    from typing import Any
    checks: dict[str, Any] = {}
    evidence: dict[str, Any] = {
        "timestamp": time.time(),
        "base_url": args.base_url,
        "checks": checks,
    }
    failed = False

    for name, url in endpoints.items():
        try:
            status, latency, body = probe(url, args.timeout)
            ok = 200 <= status < 300
            failed = failed or not ok
            evidence["checks"][name] = {
                "url": url,
                "status": status,
                "latency_seconds": round(latency, 4),
                "ok": ok,
                "body_preview": body,
            }
            print(f"{name}: status={status} latency={latency:.3f}s")
        except Exception as exc:
            failed = True
            evidence["checks"][name] = {"url": url, "ok": False, "error": str(exc)}
            print(f"{name}: ERROR {exc}")

    args.evidence.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(f"evidence={args.evidence}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
