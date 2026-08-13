#!/usr/bin/env python3
"""Run a guarded staging disruption/recovery sequence and verify service health."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path


def validate_guard(*, environment: str, enabled: bool, confirmed: bool) -> None:
    if environment.strip().lower() != "staging":
        raise RuntimeError("Recovery probes are allowed only when LOOM_ENV=staging")
    if not enabled:
        raise RuntimeError("FAULT_INJECTION_ENABLED must be true")
    if not confirmed:
        raise RuntimeError("--confirm-staging is required for destructive staging tests")


def run_command(command: str, timeout: float) -> tuple[int, str, float]:
    started = time.perf_counter()
    completed = subprocess.run(
        command,
        shell=True,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    elapsed = time.perf_counter() - started
    output = "\n".join(
        part for part in (completed.stdout.strip(), completed.stderr.strip()) if part
    )
    return completed.returncode, output[-4000:], elapsed


def probe_until_healthy(
    health_command: str,
    *,
    timeout: float,
    interval: float,
) -> tuple[bool, int, str, float, int]:
    started = time.perf_counter()
    attempts = 0
    last_code = -1
    last_output = ""

    while time.perf_counter() - started <= timeout:
        attempts += 1
        last_code, last_output, _ = run_command(health_command, min(interval, timeout))
        if last_code == 0:
            return True, last_code, last_output, time.perf_counter() - started, attempts
        time.sleep(interval)

    return False, last_code, last_output, time.perf_counter() - started, attempts


def execute(
    *,
    scenario: str,
    disrupt_command: str,
    recover_command: str,
    health_command: str,
    disruption_timeout: float,
    recovery_timeout: float,
    health_timeout: float,
    health_interval: float,
) -> dict[str, object]:
    started_at = time.time()
    disruption_code, disruption_output, disruption_duration = run_command(
        disrupt_command, disruption_timeout
    )

    recovery_code = -1
    recovery_output = ""
    recovery_duration = 0.0
    healthy = False
    health_code = -1
    health_output = ""
    health_duration = 0.0
    health_attempts = 0

    try:
        recovery_code, recovery_output, recovery_duration = run_command(
            recover_command, recovery_timeout
        )
        if recovery_code == 0:
            (
                healthy,
                health_code,
                health_output,
                health_duration,
                health_attempts,
            ) = probe_until_healthy(
                health_command,
                timeout=health_timeout,
                interval=health_interval,
            )
    finally:
        finished_at = time.time()

    status = (
        "passed"
        if disruption_code == 0 and recovery_code == 0 and healthy
        else "failed"
    )

    return {
        "schema_version": 1,
        "scenario": scenario,
        "status": status,
        "started_at": started_at,
        "finished_at": finished_at,
        "disruption": {
            "exit_code": disruption_code,
            "duration_seconds": round(disruption_duration, 3),
            "output": disruption_output,
        },
        "recovery": {
            "exit_code": recovery_code,
            "duration_seconds": round(recovery_duration, 3),
            "output": recovery_output,
        },
        "health_probe": {
            "passed": healthy,
            "exit_code": health_code,
            "duration_seconds": round(health_duration, 3),
            "attempts": health_attempts,
            "output": health_output,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a guarded staging recovery probe")
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--disrupt-command", required=True)
    parser.add_argument("--recover-command", required=True)
    parser.add_argument("--health-command", required=True)
    parser.add_argument("--disruption-timeout", type=float, default=60.0)
    parser.add_argument("--recovery-timeout", type=float, default=120.0)
    parser.add_argument("--health-timeout", type=float, default=120.0)
    parser.add_argument("--health-interval", type=float, default=2.0)
    parser.add_argument("--evidence", type=Path, default=Path("recovery-evidence.json"))
    parser.add_argument("--confirm-staging", action="store_true")
    args = parser.parse_args()

    try:
        validate_guard(
            environment=os.getenv("LOOM_ENV", ""),
            enabled=os.getenv("FAULT_INJECTION_ENABLED", "false").strip().lower() == "true",
            confirmed=args.confirm_staging,
        )
        values = (
            args.disruption_timeout,
            args.recovery_timeout,
            args.health_timeout,
            args.health_interval,
        )
        if any(value <= 0 for value in values):
            raise ValueError("timeouts and health interval must be positive")

        evidence = execute(
            scenario=args.scenario,
            disrupt_command=args.disrupt_command,
            recover_command=args.recover_command,
            health_command=args.health_command,
            disruption_timeout=args.disruption_timeout,
            recovery_timeout=args.recovery_timeout,
            health_timeout=args.health_timeout,
            health_interval=args.health_interval,
        )
        args.evidence.parent.mkdir(parents=True, exist_ok=True)
        args.evidence.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        print(json.dumps(evidence, indent=2))
        return 0 if evidence["status"] == "passed" else 1
    except (RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
        print(f"RECOVERY PROBE: FAILED\n- {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
