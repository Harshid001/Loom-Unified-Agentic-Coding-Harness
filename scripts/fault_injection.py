#!/usr/bin/env python3
"""Run explicitly approved staging fault/recovery commands and emit evidence."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path


def validate_guard(*, environment: str, enabled: bool, confirmed: bool) -> None:
    normalized = environment.strip().lower()
    if normalized != "staging":
        raise RuntimeError("Fault injection is allowed only when LOOM_ENV=staging")
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
    output = "\n".join(part for part in (completed.stdout.strip(), completed.stderr.strip()) if part)
    return completed.returncode, output[-4000:], elapsed


def execute(
    *,
    scenario: str,
    disrupt_command: str,
    recover_command: str,
    timeout: float,
    recovery_timeout: float,
) -> dict[str, object]:
    started_at = time.time()
    disrupt_code, disrupt_output, disrupt_duration = run_command(disrupt_command, timeout)

    recovery_code = -1
    recovery_output = ""
    recovery_duration = 0.0
    try:
        recovery_code, recovery_output, recovery_duration = run_command(recover_command, recovery_timeout)
    finally:
        finished_at = time.time()

    status = "passed" if disrupt_code == 0 and recovery_code == 0 else "failed"
    return {
        "schema_version": 1,
        "scenario": scenario,
        "status": status,
        "started_at": started_at,
        "finished_at": finished_at,
        "disruption": {
            "exit_code": disrupt_code,
            "duration_seconds": round(disrupt_duration, 3),
            "output": disrupt_output,
        },
        "recovery": {
            "exit_code": recovery_code,
            "duration_seconds": round(recovery_duration, 3),
            "output": recovery_output,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run guarded staging fault-injection tests")
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--disrupt-command", required=True)
    parser.add_argument("--recover-command", required=True)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--recovery-timeout", type=float, default=120.0)
    parser.add_argument("--evidence", type=Path, default=Path("fault-recovery-evidence.json"))
    parser.add_argument("--confirm-staging", action="store_true")
    args = parser.parse_args()

    try:
        enabled = os.getenv("FAULT_INJECTION_ENABLED", "false").strip().lower() == "true"
        validate_guard(
            environment=os.getenv("LOOM_ENV", ""),
            enabled=enabled,
            confirmed=args.confirm_staging,
        )
        if args.timeout <= 0 or args.recovery_timeout <= 0:
            raise ValueError("timeouts must be positive")
        evidence = execute(
            scenario=args.scenario,
            disrupt_command=args.disrupt_command,
            recover_command=args.recover_command,
            timeout=args.timeout,
            recovery_timeout=args.recovery_timeout,
        )
        args.evidence.parent.mkdir(parents=True, exist_ok=True)
        args.evidence.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        print(json.dumps(evidence, indent=2))
        return 0 if evidence["status"] == "passed" else 1
    except (RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
        print(f"FAULT INJECTION: FAILED\n- {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
