#!/usr/bin/env python3
"""Run an HTTP load test and fail when configured SLOs are missed."""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import httpx


@dataclass(frozen=True)
class Result:
    latency: float
    status: int
    error: str = ""


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * fraction)))
    return ordered[index]


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
    p50 = percentile(latencies, 0.50)
    p95 = percentile(latencies, 0.95)
    p99 = percentile(latencies, 0.99)
    error_rate = failure_count / len(results) if results else 1.0

    failures: list[str] = []
    if error_rate > args.max_error_rate:
        failures.append(f"error rate {error_rate:.4f} exceeds {args.max_error_rate:.4f}")
    if p95 > args.max_p95:
        failures.append(f"p95 {p95:.3f}s exceeds {args.max_p95:.3f}s")
    if p99 > args.max_p99:
        failures.append(f"p99 {p99:.3f}s exceeds {args.max_p99:.3f}s")
    if throughput < args.min_throughput:
        failures.append(f"throughput {throughput:.3f} req/s is below {args.min_throughput:.3f} req/s")

    evidence = {
        "schema_version": 1,
        "timestamp": time.time(),
        "base_url": args.base_url,
        "repo_path": args.repo_path,
        "requests": len(results),
        "concurrency": args.concurrency,
        "timeout_seconds": args.timeout,
        "elapsed_seconds": round(elapsed, 6),
        "successes": len(successes),
        "failures": failure_count,
        "error_rate": round(error_rate, 6),
        "throughput_rps": round(throughput, 6),
        "latency_seconds": {
            "p50": round(p50, 6),
            "p95": round(p95, 6),
            "p99": round(p99, 6),
            "mean": round(statistics.mean(latencies), 6) if latencies else 0.0,
            "max": round(max(latencies), 6) if latencies else 0.0,
        },
        "thresholds": {
            "max_error_rate": args.max_error_rate,
            "max_p95_seconds": args.max_p95,
            "max_p99_seconds": args.max_p99,
            "min_throughput_rps": args.min_throughput,
        },
        "status": "passed" if not failures else "failed",
        "failure_reasons": failures,
        "transport_errors": [item.error for item in results if item.status == 0 and item.error][:10],
        "samples": [asdict(item) for item in results[:10]],
    }

    if args.evidence:
        args.evidence.parent.mkdir(parents=True, exist_ok=True)
        args.evidence.write_text(json.dumps(evidence, indent=2), encoding="utf-8")

    print(f"requests={len(results)} concurrency={args.concurrency}")
    print(f"successes={len(successes)} failures={failure_count}")
    print(f"throughput={throughput:.3f} req/s")
    print(f"p50={p50:.3f}s p95={p95:.3f}s p99={p99:.3f}s")
    if latencies:
        print(f"mean={statistics.mean(latencies):.3f}s max={max(latencies):.3f}s")

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
    parser.add_argument("--evidence", type=Path, default=Path("load-slo-evidence.json"))
    args = parser.parse_args()
    if args.concurrency < 1 or args.requests < 1:
        parser.error("--concurrency and --requests must be positive")
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    if not 0 <= args.max_error_rate <= 1:
        parser.error("--max-error-rate must be between 0 and 1")
    if args.max_p95 <= 0 or args.max_p99 <= 0 or args.min_throughput <= 0:
        parser.error("SLO thresholds must be positive")
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
