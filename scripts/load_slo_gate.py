#!/usr/bin/env python3
"""Run an HTTP load test and fail when configured SLOs are missed."""
from __future__ import annotations

import argparse
import asyncio
import statistics
import time
from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class Result:
    latency: float
    status: int
    error: str = ""


async def one_request(
    client: httpx.AsyncClient,
    base_url: str,
    api_key: str,
    repo_path: str,
    index: int,
) -> Result:
    started = time.perf_counter()
    try:
        response = await client.post(
            f"{base_url.rstrip('/')}/api/v1/run",
            json={
                "issue": f"slo-gate-{index}",
                "repo_path": repo_path,
                "mock": True,
                "async_mode": True,
            },
            headers={"X-API-Key": api_key},
        )
        return Result(time.perf_counter() - started, response.status_code)
    except Exception as exc:  # pragma: no cover - deployment-only failure mode
        return Result(time.perf_counter() - started, 0, str(exc))


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    index = min(len(values) - 1, max(0, round((len(values) - 1) * fraction)))
    return values[index]


async def run(args: argparse.Namespace) -> int:
    semaphore = asyncio.Semaphore(args.concurrency)
    limits = httpx.Limits(max_connections=args.concurrency, max_keepalive_connections=args.concurrency)

    async with httpx.AsyncClient(timeout=args.timeout, limits=limits) as client:
        async def limited(index: int) -> Result:
            async with semaphore:
                return await one_request(client, args.base_url, args.api_key, args.repo_path, index)

        started = time.perf_counter()
        results = await asyncio.gather(*(limited(i) for i in range(args.requests)))
        elapsed = time.perf_counter() - started

    latencies = [item.latency for item in results]
    successes = [item for item in results if 200 <= item.status < 300]
    failure_count = len(results) - len(successes)
    throughput = len(results) / elapsed if elapsed else 0.0
    p95 = percentile(latencies, 0.95)
    p99 = percentile(latencies, 0.99)
    error_rate = failure_count / len(results) if results else 1.0

    print(f"requests={len(results)} concurrency={args.concurrency}")
    print(f"successes={len(successes)} failures={failure_count}")
    print(f"throughput={throughput:.3f} req/s")
    print(f"p50={percentile(latencies, 0.50):.3f}s p95={p95:.3f}s p99={p99:.3f}s")
    if latencies:
        print(f"mean={statistics.mean(latencies):.3f}s max={max(latencies):.3f}s")

    failures: list[str] = []
    if error_rate > args.max_error_rate:
        failures.append(f"error rate {error_rate:.4f} exceeds {args.max_error_rate:.4f}")
    if p95 > args.max_p95:
        failures.append(f"p95 {p95:.3f}s exceeds {args.max_p95:.3f}s")
    if p99 > args.max_p99:
        failures.append(f"p99 {p99:.3f}s exceeds {args.max_p99:.3f}s")
    if throughput < args.min_throughput:
        failures.append(f"throughput {throughput:.3f} req/s is below {args.min_throughput:.3f} req/s")

    for item in results:
        if item.status == 0 and item.error:
            print(f"transport_error={item.error}")
            break

    if failures:
        print("SLO GATE: FAILED")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("SLO GATE: PASSED")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Loom load testing with explicit SLO thresholds")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--repo-path", required=True)
    parser.add_argument("--concurrency", type=int, default=20)
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--max-error-rate", type=float, default=0.01)
    parser.add_argument("--max-p95", type=float, default=0.50)
    parser.add_argument("--max-p99", type=float, default=1.00)
    parser.add_argument("--min-throughput", type=float, default=10.0)
    args = parser.parse_args()
    if args.concurrency < 1 or args.requests < 1:
        parser.error("--concurrency and --requests must be positive")
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
