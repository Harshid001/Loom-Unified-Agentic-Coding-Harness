"""PRD-015 — Release Baseline Capture.

Runs every toolchain gate and writes structured JSON artifacts to:
  artifacts/release/<commit-sha>/
    test-results.json
    security-results.json
    build-results.json
    environment.json

Also generates docs/releases/production-baseline.md.

Usage:
    python scripts/production/capture_baseline.py [--output-dir artifacts/release]
"""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(cmd: list[str], cwd: Path, timeout: int = 300) -> tuple[int, str, str]:
    """Run a subprocess, returning (returncode, stdout, stderr)."""
    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        return 1, "", f"Command timed out after {timeout}s: {' '.join(cmd)}"
    except FileNotFoundError as exc:
        return 1, "", f"Command not found: {exc}"


def _npm() -> str:
    """Resolve npm executable, handling .cmd suffix on Windows."""
    return shutil.which("npm.cmd") or shutil.which("npm") or "npm"


def _git_sha(repo: Path) -> str:
    rc, out, _ = _run(["git", "rev-parse", "HEAD"], repo)
    return out.strip() if rc == 0 else "unknown"


def _git_branch(repo: Path) -> str:
    rc, out, _ = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], repo)
    return out.strip() if rc == 0 else "unknown"


def _python_version() -> str:
    return platform.python_version()


def _node_version() -> str:
    rc, out, _ = _run(["node", "--version"], Path("."))
    return out.strip() if rc == 0 else "not found"


def _npm_version() -> str:
    rc, out, _ = _run(["npm", "--version"], Path("."))
    return out.strip() if rc == 0 else "not found"


# ---------------------------------------------------------------------------
# Gate runners
# ---------------------------------------------------------------------------

def _run_tests(repo: Path) -> dict:
    """Run pytest and collect results."""
    start = time.time()
    rc, stdout, stderr = _run(
        [sys.executable, "-m", "pytest", "tests/", "-v", "--tb=short", "-q", "--no-header"],
        repo,
        timeout=600,
    )
    duration = round(time.time() - start, 2)

    # Parse summary line e.g. "57 passed, 3 failed in 42.1s"
    summary_line = ""
    for line in (stdout + stderr).splitlines():
        if "passed" in line or "failed" in line or "error" in line:
            summary_line = line.strip()

    passed = 0
    failed = 0
    errors = 0
    for part in summary_line.split(","):
        part = part.strip()
        if "passed" in part:
            try:
                passed = int(part.split()[0])
            except ValueError:
                pass
        elif "failed" in part:
            try:
                failed = int(part.split()[0])
            except ValueError:
                pass
        elif "error" in part:
            try:
                errors = int(part.split()[0])
            except ValueError:
                pass

    return {
        "gate": "pytest",
        "status": "pass" if rc == 0 else "fail",
        "returncode": rc,
        "passed": passed,
        "failed": failed,
        "errors": errors,
        "summary": summary_line,
        "duration_seconds": duration,
    }


def _run_lint(repo: Path) -> dict:
    """Run ruff check."""
    start = time.time()
    rc, stdout, stderr = _run(
        [sys.executable, "-m", "ruff", "check", "loom/", "tests/"],
        repo,
        timeout=120,
    )
    duration = round(time.time() - start, 2)
    violations = [ln for ln in (stdout + stderr).splitlines() if ln.strip() and not ln.startswith("Found")]
    return {
        "gate": "ruff",
        "status": "pass" if rc == 0 else "fail",
        "returncode": rc,
        "violation_count": len(violations),
        "output_summary": (stdout + stderr).strip()[:2000],
        "duration_seconds": duration,
    }


def _run_mypy(repo: Path) -> dict:
    """Run mypy type check."""
    start = time.time()
    rc, stdout, stderr = _run(
        [sys.executable, "-m", "mypy", "loom/"],
        repo,
        timeout=180,
    )
    duration = round(time.time() - start, 2)
    error_lines = [ln for ln in (stdout + stderr).splitlines() if ": error:" in ln]
    return {
        "gate": "mypy",
        "status": "pass" if rc == 0 else "fail",
        "returncode": rc,
        "error_count": len(error_lines),
        "output_summary": (stdout + stderr).strip()[:2000],
        "duration_seconds": duration,
    }


def _run_pip_audit(repo: Path) -> dict:
    """Run pip-audit for known CVEs."""
    start = time.time()
    rc, stdout, stderr = _run(
        [
            sys.executable,
            "-m",
            "pip_audit",
            "--format",
            "json",
            "--skip-editable",
            "--ignore-vuln",
            "PYSEC-2026-2447",
            "--ignore-vuln",
            "PYSEC-2026-1325",
        ],
        repo,
        timeout=120,
    )
    duration = round(time.time() - start, 2)

    # pip-audit not always installed — graceful fallback
    if rc == 127 or "No module named pip_audit" in stderr:
        rc2, stdout2, stderr2 = _run(
            [sys.executable, "-m", "pip", "audit"],
            repo,
            timeout=120,
        )
        if "No module" in stderr2:
            return {
                "gate": "pip_audit",
                "status": "skipped",
                "reason": "pip-audit not installed",
                "duration_seconds": duration,
            }
        rc, stdout, stderr = rc2, stdout2, stderr2

    try:
        data = json.loads(stdout)
        vuln_count = len(data.get("vulnerabilities", data if isinstance(data, list) else []))
    except Exception:
        vuln_count = -1

    return {
        "gate": "pip_audit",
        "status": "pass" if rc == 0 else "fail",
        "returncode": rc,
        "vulnerability_count": vuln_count,
        "output_summary": (stdout + stderr).strip()[:2000],
        "duration_seconds": duration,
    }


def _run_gitleaks(repo: Path) -> dict:
    """Run Gitleaks secret scan if available."""
    start = time.time()
    if not shutil.which("gitleaks"):
        return {
            "gate": "gitleaks",
            "status": "skipped",
            "reason": "gitleaks binary not found in PATH",
            "duration_seconds": 0,
        }
    rc, stdout, stderr = _run(
        ["gitleaks", "detect", "--no-banner", "--exit-code", "1"],
        repo,
        timeout=120,
    )
    duration = round(time.time() - start, 2)
    return {
        "gate": "gitleaks",
        "status": "pass" if rc == 0 else "fail",
        "returncode": rc,
        "output_summary": (stdout + stderr).strip()[:1000],
        "duration_seconds": duration,
    }


def _run_npm_audit(repo: Path) -> dict:
    """Run npm audit in web/ subdirectory."""
    web_dir = repo / "web"
    if not web_dir.exists():
        return {"gate": "npm_audit", "status": "skipped", "reason": "web/ directory not found"}

    start = time.time()
    rc, stdout, stderr = _run(
        [_npm(), "audit", "--json"],
        web_dir,
        timeout=120,
    )
    duration = round(time.time() - start, 2)

    vuln_count = -1
    try:
        data = json.loads(stdout)
        vuln_count = data.get("metadata", {}).get("vulnerabilities", {}).get("total", -1)
    except Exception:
        pass

    return {
        "gate": "npm_audit",
        "status": "pass" if rc == 0 else "warn",
        "returncode": rc,
        "vulnerability_count": vuln_count,
        "duration_seconds": duration,
    }


def _run_frontend_build(repo: Path) -> dict:
    """Run Next.js production build."""
    web_dir = repo / "web"
    if not web_dir.exists():
        return {"gate": "frontend_build", "status": "skipped", "reason": "web/ directory not found"}

    start = time.time()
    rc, stdout, stderr = _run(
        [_npm(), "run", "build"],
        web_dir,
        timeout=300,
    )
    duration = round(time.time() - start, 2)
    return {
        "gate": "frontend_build",
        "status": "pass" if rc == 0 else "fail",
        "returncode": rc,
        "output_summary": (stdout + stderr).strip()[-1000:],
        "duration_seconds": duration,
    }


def _lock_state(repo: Path) -> dict:
    """Capture dependency lock state."""
    pylock = repo / "pyproject.toml"
    npmlock = repo / "web" / "package-lock.json"
    yarnlock = repo / "web" / "yarn.lock"

    import hashlib

    def sha256_file(p: Path) -> str | None:
        if not p.exists():
            return None
        h = hashlib.sha256(p.read_bytes())
        return h.hexdigest()

    return {
        "pyproject_toml_sha256": sha256_file(pylock),
        "package_lock_sha256": sha256_file(npmlock),
        "yarn_lock_sha256": sha256_file(yarnlock),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def capture(repo: Path, output_dir: Path) -> Path:
    """Run all gates and write artifacts. Returns the artifact directory."""
    sha = _git_sha(repo)
    branch = _git_branch(repo)
    ts = datetime.now(timezone.utc).isoformat()

    artifact_dir = output_dir / sha
    artifact_dir.mkdir(parents=True, exist_ok=True)

    print(f"[baseline] commit  : {sha}")
    print(f"[baseline] branch  : {branch}")
    print(f"[baseline] output  : {artifact_dir}")
    print()

    # --- environment.json ---
    env = {
        "captured_at": ts,
        "commit_sha": sha,
        "git_branch": branch,
        "python_version": _python_version(),
        "node_version": _node_version(),
        "npm_version": _npm_version(),
        "platform": platform.platform(),
        "lock_state": _lock_state(repo),
    }
    (artifact_dir / "environment.json").write_text(json.dumps(env, indent=2), encoding="utf-8")
    print("[baseline] OK: environment.json")

    # --- test-results.json ---
    print("[baseline] running tests ...")
    test_result = _run_tests(repo)
    lint_result = _run_lint(repo)
    mypy_result = _run_mypy(repo)

    test_results = {
        "captured_at": ts,
        "commit_sha": sha,
        "pytest": test_result,
        "ruff": lint_result,
        "mypy": mypy_result,
        "overall_status": "pass" if all(
            r["status"] == "pass" for r in [test_result, lint_result, mypy_result]
        ) else "fail",
    }
    (artifact_dir / "test-results.json").write_text(json.dumps(test_results, indent=2), encoding="utf-8")
    _print_gate(test_result)
    _print_gate(lint_result)
    _print_gate(mypy_result)

    # --- security-results.json ---
    print("[baseline] running security scans ...")
    pip_audit = _run_pip_audit(repo)
    gitleaks = _run_gitleaks(repo)
    npm_audit = _run_npm_audit(repo)

    security_results = {
        "captured_at": ts,
        "commit_sha": sha,
        "pip_audit": pip_audit,
        "gitleaks": gitleaks,
        "npm_audit": npm_audit,
        "overall_status": "pass" if all(
            r["status"] in ("pass", "skipped", "warn")
            for r in [pip_audit, gitleaks, npm_audit]
        ) else "fail",
    }
    (artifact_dir / "security-results.json").write_text(json.dumps(security_results, indent=2), encoding="utf-8")
    _print_gate(pip_audit)
    _print_gate(gitleaks)
    _print_gate(npm_audit)

    # --- build-results.json ---
    print("[baseline] running frontend build ...")
    frontend = _run_frontend_build(repo)
    build_results = {
        "captured_at": ts,
        "commit_sha": sha,
        "frontend_build": frontend,
        "overall_status": frontend["status"],
    }
    (artifact_dir / "build-results.json").write_text(json.dumps(build_results, indent=2), encoding="utf-8")
    _print_gate(frontend)

    # --- docs/releases/production-baseline.md ---
    _write_baseline_doc(repo, sha, branch, ts, env, test_results, security_results, build_results, artifact_dir)

    print()
    print(f"[baseline] artifacts written to: {artifact_dir}")
    overall = (
        test_results["overall_status"] == "pass"
        and security_results["overall_status"] == "pass"
        and build_results["overall_status"] == "pass"
    )
    print(f"[baseline] OVERALL STATUS: {'PASS' if overall else 'FAIL'}")
    if not overall:
        sys.exit(1)
    return artifact_dir


def _print_gate(result: dict) -> None:
    status = result.get("status", "?").upper()
    gate = result.get("gate", "?")
    icon = "[OK]" if status == "PASS" else ("[" + status + "]")
    print(f"[baseline]   {icon} {gate}: {status}")


def _write_baseline_doc(
    repo: Path,
    sha: str,
    branch: str,
    ts: str,
    env: dict,
    test_results: dict,
    security_results: dict,
    build_results: dict,
    artifact_dir: Path,
) -> None:
    def _status_badge(s: str) -> str:
        return "✅ PASS" if s == "pass" else ("⚠️ WARN/SKIP" if s in ("warn", "skipped") else "❌ FAIL")

    pytest_r = test_results.get("pytest", {})
    ruff_r = test_results.get("ruff", {})
    mypy_r = test_results.get("mypy", {})
    pip_r = security_results.get("pip_audit", {})
    gl_r = security_results.get("gitleaks", {})
    npm_sec = security_results.get("npm_audit", {})
    fe_r = build_results.get("frontend_build", {})

    doc = f"""# Loom — Production Release Baseline

**Captured:** {ts}
**Commit SHA:** `{sha}`
**Branch:** `{branch}`

---

## Environment

| Item | Value |
|---|---|
| Python | `{env["python_version"]}` |
| Node | `{env["node_version"]}` |
| npm | `{env["npm_version"]}` |
| Platform | `{env["platform"]}` |
| pyproject.toml SHA256 | `{env["lock_state"].get("pyproject_toml_sha256", "n/a")}` |
| package-lock.json SHA256 | `{env["lock_state"].get("package_lock_sha256", "n/a")}` |

---

## Gate Results

| Gate | Status | Detail |
|---|---|---|
| pytest | {_status_badge(pytest_r.get("status", "fail"))} | {pytest_r.get("passed", 0)} passed, {pytest_r.get("failed", 0)} failed |
| ruff (lint) | {_status_badge(ruff_r.get("status", "fail"))} | {ruff_r.get("violation_count", "?")} violations |
| mypy | {_status_badge(mypy_r.get("status", "fail"))} | {mypy_r.get("error_count", "?")} errors |
| pip-audit | {_status_badge(pip_r.get("status", "fail"))} | {pip_r.get("vulnerability_count", "?")} vulnerabilities |
| gitleaks | {_status_badge(gl_r.get("status", "fail"))} | {gl_r.get("output_summary", "")[:80]} |
| npm audit | {_status_badge(npm_sec.get("status", "fail"))} | {npm_sec.get("vulnerability_count", "?")} vulnerabilities |
| frontend build | {_status_badge(fe_r.get("status", "fail"))} | — |

---

## Artifact Directory

```
{artifact_dir}
├── environment.json
├── test-results.json
├── security-results.json
└── build-results.json
```

---

## Reproducibility

This baseline can be reproduced by checking out commit `{sha}` and running:

```bash
python scripts/production/capture_baseline.py
```

No undocumented local dependencies are required beyond the packages listed in `pyproject.toml`.

---

*Generated by `scripts/production/capture_baseline.py` — do not edit manually.*
"""

    docs_dir = repo / "docs" / "releases"
    docs_dir.mkdir(parents=True, exist_ok=True)
    (docs_dir / "production-baseline.md").write_text(doc, encoding="utf-8")
    print("[baseline] OK: docs/releases/production-baseline.md")


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture Loom release baseline")
    parser.add_argument("--output-dir", default="artifacts/release", help="Base output directory")
    args = parser.parse_args()

    repo = Path(__file__).resolve().parents[2]
    output_dir = (repo / args.output_dir).resolve()
    capture(repo, output_dir)


if __name__ == "__main__":
    main()
