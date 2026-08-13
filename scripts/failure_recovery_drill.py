#!/usr/bin/env python3
"""Execute a deployment-specific failure/recovery drill and record timings.

The script deliberately delegates fault injection to explicit operator-supplied
commands so it cannot accidentally damage an environment by guessing how to
stop a service. Recovery is verified through Loom liveness/readiness probes.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path

import httpx


def wait_ready(url: str, timeout: float, interval: float, deadline: float) -> float:
    started = time.perf_counter()
    while time.perf_counter() - started < deadline:
        try:
            response = httpx.get(url, timeout=timeout)
            if 200 <= response.status_code < 300:
                return time.perf_counter() - started
        except httpx.HTTPError:
            pass
        time.sleep(interval)
    raise RuntimeError(f"service did not recover within {deadline:.1f}s: {url}")


def run_command(command: str) -> None:
    completed = subprocess.run(command, shell=True, check=False, text=True, capture_output=True)
    if completed.returncode != 0:
        raise RuntimeError(
            f"fault/recovery command failed ({completed.returncode}): {completed.stderr.strip() or completed.stdout.strip()}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a controlled Loom failure/recovery drill")
    parser.add_argument("--readiness-url", required=True)
    parser.add_argument("--failure-command", required=True, help="Operator-supplied fault injection command")
    parser.add_argument("--recovery-command", default=None, help="Optional explicit recovery command")
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--recovery-deadline", type=float, default=120.0)
    parser.add_argument("--evidence", type=Path, default=Path("failure-recovery-evidence.json"))
    args = parser.parse_args()

    evidence: dict[str, object] = {"timestamp": time.time(), "readiness_url": args.readiness_url}
    outage_started = time.perf_counter()

    print("Injecting controlled failure...")
    run_command(args.failure_command)
    evidence["failure_injected_seconds"] = round(time.perf_counter() - outage_started, 4)

    if args.recovery_command:
        print("Running explicit recovery command...")
        run_command(args.recovery_command)

    print("Waiting for readiness recovery...")
    recovery_seconds = wait_ready(
        args.readiness_url,
        timeout=args.timeout,
        interval=args.interval,
        deadline=args.recovery_deadline,
    )
    evidence["time_to_recovery_seconds"] = round(recovery_seconds, 4)
    evidence["recovered"] = True

    args.evidence.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(f"RECOVERY DRILL: PASSED ({recovery_seconds:.3f}s)")
    print(f"evidence={args.evidence}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
