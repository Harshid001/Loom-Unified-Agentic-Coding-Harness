"""Concurrent API load test for Loom production deployments.

Example:
    python scripts/load_test.py --base-url http://localhost:8000 --api-key "$API_KEY" \
        --concurrency 20 --requests 100
"""

from __future__ import annotations

import argparse
import asyncio
import statistics
import time
from dataclasses import dataclass

import httpx


@dataclass
class Result:
    latency: float
    status: int
    error: str = ""


async def run_request(client: httpx.AsyncClient, url: str, headers: dict[str, str], issue: str) -> Result:
    started = time.perf_counter()
    try:
        response = await client.post(
            f"{url.rstrip('/')}/api/v1/run",
            json={"issue": issue, "repo_path": ".", "mock": True, "async_mode": True},
            headers=headers,
        )
        return Result(time.perf_counter() - started, response.status_code, "")
    except Exception as exc:  # pragma: no cover - exercised by real deployments
        return Result(time.perf_counter() - started, 0, str(exc))


async def main_async(args: argparse.Namespace) -> int:
    semaphore = asyncio.Semaphore(args.concurrency)
    headers = {"X-API-Key": args.api_key}

    async with httpx.AsyncClient(timeout=args.timeout) as client:
        async def limited(index: int) -> Result:
            async with semaphore:
                return await run_request(client, args.base_url, headers, f"load-test-{index}")

        started = time.perf_counter()
        results = await asyncio.gather(*(limited(i) for i in range(args.requests)))
        elapsed = time.perf_counter() - started

    latencies = sorted(r.latency for r in results)
    successes = [r for r in results if 200 <= r.status < 300]
    failures = [r for r in results if r not in successes]

    def percentile(value: float) -> float:
        if not latencies:
            return 0.0
        index = min(len(latencies) - 1, max(0, round((len(latencies) - 1) * value)))
        return latencies[index]

    throughput = len(results) / elapsed if elapsed > 0 else 0.0
    print(f"requests={len(results)} concurrency={args.concurrency}")
    print(f"successes={len(successes)} failures={len(failures)}")
    print(f"throughput={throughput:.2f} requests/sec")
    print(f"p50={percentile(0.50):.3f}s p95={percentile(0.95):.3f}s p99={percentile(0.99):.3f}s")
    if latencies:
        print(f"mean={statistics.mean(latencies):.3f}s max={max(latencies):.3f}s")
    for failure in failures[:10]:
        print(f"failure status={failure.status} error={failure.error}")

    return 0 if not failures else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Load test the Loom run API")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--requests", type=int, default=50)
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()
    if args.concurrency < 1 or args.requests < 1:
        parser.error("--concurrency and --requests must be positive")
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
