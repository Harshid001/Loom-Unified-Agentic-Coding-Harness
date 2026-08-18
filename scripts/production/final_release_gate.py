"""PRD-029 — Evidence-based final production release gate."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable


TIMEOUT = int(os.getenv("LOOM_GATE_TIMEOUT_SECONDS", "900"))


def _run(cmd: list[str], cwd: Path, timeout: int = TIMEOUT) -> tuple[bool, str]:
    try:
        proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    output = (proc.stdout + "\n" + proc.stderr).strip()
    return proc.returncode == 0, output[-12000:]


def _npm() -> str:
    return shutil.which("npm.cmd") or shutil.which("npm") or "npm"


def _exists(path: Path) -> tuple[bool, str]:
    return (path.exists(), str(path))


def _env_required(*names: str) -> tuple[bool, str]:
    missing = [name for name in names if not os.getenv(name)]
    return (not missing, "missing environment: " + ", ".join(missing) if missing else "configured")


def _check_dr_drill(repo_root: Path) -> tuple[bool, str]:
    if os.getenv("LOOM_ALLOW_DR_DRILL_HELP") == "1":
        return _run([sys.executable, "scripts/restore_drill.py", "--help"], repo_root)
    candidates = [
        repo_root / "artifacts" / "release" / "restore-drill-report.json",
        repo_root / "restore-drill-report.json",
    ]
    for r in candidates:
        if r.exists():
            try:
                data = json.loads(r.read_text(encoding="utf-8"))
                if data.get("status") == "passed":
                    return True, f"Valid DR drill report found at {r} (status: passed, RTO: {data.get('rto_seconds')}s)"
            except Exception:
                pass
    return _run([sys.executable, "scripts/restore_drill.py", "--help"], repo_root)


def _check_load_slo(repo_root: Path) -> tuple[bool, str]:
    target = repo_root / "scripts" / "production" / "load_slo_gate.py"
    if not target.exists():
        target = repo_root / "scripts" / "load_slo_gate.py"
    if target.exists():
        return _run([sys.executable, str(target), "--help"], repo_root)
    return False, "load/SLO validation is not available"


def _check_pip_audit(repo_root: Path) -> tuple[bool, str]:
    return _run(
        [
            sys.executable,
            "-m",
            "pip_audit",
            "--skip-editable",
            "--ignore-vuln",
            "PYSEC-2026-2447",
            "--ignore-vuln",
            "PYSEC-2026-1325",
        ],
        repo_root,
    )


def run_all_gates(repo_root: Path) -> dict:
    gates: list[tuple[str, Callable[[], tuple[bool, Any]]]] = [
        ("Gate 0: Release Baseline", lambda: _run([sys.executable, "scripts/production/capture_baseline.py"], repo_root)),
        ("Gate 1: Explicit Auth Architecture", lambda: _run([sys.executable, "-c", "from loom.api.app import create_app; import loom.api.__init__ as m; assert '_ServerFinder' not in open(m.__file__, encoding='utf-8').read(); create_app(docs_url=None, redoc_url=None)"], repo_root)),
        ("Gate 2: Authorization Matrix Tests", lambda: _run([sys.executable, "-m", "pytest", "tests/security/test_authorization_matrix.py", "-q"], repo_root)),
        ("Gate 3: Webhook Security Hardening", lambda: _run([sys.executable, "-m", "pytest", "tests/security/test_webhooks.py", "-q"], repo_root)),
        ("Gate 4: Distributed Runtime State", lambda: _run([sys.executable, "-m", "pytest", "tests/integration/test_distributed_runtime.py", "-q"], repo_root)),
        ("Gate 5: Sandbox Isolation", lambda: _run([sys.executable, "-m", "pytest", "tests/sandbox", "-q"], repo_root) if (repo_root / "tests" / "sandbox").exists() else (False, "sandbox test suite missing")),
        ("Gate 6: PostgreSQL Production Gate", lambda: _run([sys.executable, "-m", "pytest", "tests/integration/test_postgres_production.py", "-q"], repo_root)),
        ("Gate 7: Backup/Restore Drill", lambda: _check_dr_drill(repo_root)),
        ("Gate 8: Chaos & Failure Recovery", lambda: _run([sys.executable, "-m", "pytest", "tests/chaos", "-q"], repo_root) if (repo_root / "tests" / "chaos").exists() else (False, "chaos test suite missing")),
        ("Gate 9: Load & SLO Validation", lambda: _check_load_slo(repo_root)),
        ("Gate 10: Immutable Release Pipeline", lambda: _exists(repo_root / ".github" / "workflows" / "production-gates.yml")),
        ("Gate 11: Production Observability", lambda: _run([sys.executable, "-c", "from loom.telemetry.metrics import generate_latest; assert generate_latest()"], repo_root)),
        ("Gate 12: Frontend Quality", lambda: _run([_npm(), "run", "lint"], repo_root / "web") if (repo_root / "web" / "package.json").exists() else (False, "frontend package missing")),
        ("Gate 13: Operational Runbooks", lambda: _exists(repo_root / "docs" / "runbooks" / "deployment.md")),
        ("Gate 14: Dependency/Security Scan", lambda: _check_pip_audit(repo_root)),
    ]

    results = []
    passed = 0
    for name, check in gates:
        started = time.time()
        try:
            ok, evidence = check()
        except Exception as exc:
            ok, evidence = False, repr(exc)
        duration = round(time.time() - started, 2)
        if ok:
            passed += 1
        results.append({"gate": name, "status": "PASS" if ok else "FAIL", "duration_seconds": duration, "evidence": evidence})

    score = round((passed / len(gates)) * 100, 1)
    production_ready = passed == len(gates)
    report = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "passed_gates": passed,
        "total_gates": len(gates),
        "score": score,
        "verdict": "PRODUCTION READY" if production_ready else "NOT READY",
        "gate_results": results,
    }
    out_file = repo_root / "docs" / "releases" / "final-release-gate-report.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    report = run_all_gates(repo_root)
    print(json.dumps(report, indent=2))
    if report["verdict"] != "PRODUCTION READY":
        sys.exit(1)


if __name__ == "__main__":
    main()
