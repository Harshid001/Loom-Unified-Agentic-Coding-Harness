from pathlib import Path

import pytest

from scripts.load_slo_gate import percentile
from scripts.production.capture_baseline import _run_tests


def test_percentile_empty_returns_zero():
    assert percentile([], 0.95) == 0.0


def test_percentile_uses_sorted_values():
    values = [0.5, 0.1, 0.2, 0.9, 0.3]
    assert percentile(values, 0.50) == 0.3
    assert percentile(values, 0.95) == 0.9


class TestBaselineAggregation:
    """Regression tests for the baseline aggregation bug where a FAIL sub-check
    could roll up into an overall PASS / PRODUCTION READY verdict.
    """

    def test_pytest_invocation_has_no_json_report_flags(self):
        """_run_tests must not pass --json-report (plugin is not installed)."""
        import inspect
        src = inspect.getsource(_run_tests)
        assert "--json-report" not in src

    def test_run_tests_returns_nonzero_rc_on_arg_error(self, monkeypatch):
        """When pytest rejects args (rc != 0), _run_tests must return status='fail'."""
        import subprocess

        from scripts.production import capture_baseline

        # Mock subprocess.run to simulate pytest rejecting --json-report
        bad_result = subprocess.CompletedProcess(
            args=["python", "-m", "pytest", "tests/", "--json-report"],
            returncode=4,
            stdout="",
            stderr="unrecognized arguments: --json-report",
        )
        monkeypatch.setattr(capture_baseline.subprocess, "run", lambda *a, **kw: bad_result)

        result = _run_tests(Path("."))
        assert result["status"] == "fail"
        assert result["returncode"] == 4
        # summary may be empty because the parser looks for "passed"/"failed"/"error"
        # but the critical invariants — status and returncode — are correct

    def test_capture_exits_nonzero_on_any_fail(self, monkeypatch):
        """If ANY sub-check fails, capture() must exit 1 (not 0)."""

        from scripts.production import capture_baseline

        # Mock all sub-check functions to return deterministic results:
        # pytest=fail, ruff=pass, mypy=pass, pip_audit=pass, gitleaks=skipped,
        # npm_audit=warn, frontend_build=fail
        mocks = {
            "_run_tests": lambda repo: {"gate": "pytest", "status": "fail", "returncode": 1,
                                         "passed": 0, "failed": 1, "errors": 0, "summary": "1 failed",
                                         "duration_seconds": 0.1},
            "_run_lint": lambda repo: {"gate": "ruff", "status": "pass", "returncode": 0,
                                        "violation_count": 0, "output_summary": "ok", "duration_seconds": 0.1},
            "_run_mypy": lambda repo: {"gate": "mypy", "status": "pass", "returncode": 0,
                                        "error_count": 0, "output_summary": "ok", "duration_seconds": 0.1},
            "_run_pip_audit": lambda repo: {"gate": "pip_audit", "status": "pass", "returncode": 0,
                                             "vulnerability_count": 0, "output_summary": "ok", "duration_seconds": 0.1},
            "_run_gitleaks": lambda repo: {"gate": "gitleaks", "status": "skipped", "returncode": 0,
                                            "output_summary": "", "duration_seconds": 0.0},
            "_run_npm_audit": lambda repo: {"gate": "npm_audit", "status": "warn", "returncode": 1,
                                             "vulnerability_count": 0, "duration_seconds": 0.1},
            "_run_frontend_build": lambda repo: {"gate": "frontend_build", "status": "fail", "returncode": 1,
                                                  "output_summary": "npm not found", "duration_seconds": 0.1},
            "_git_sha": lambda repo: "abc123",
            "_git_branch": lambda repo: "main",
            "_python_version": lambda: "3.13.0",
            "_node_version": lambda: "not found",
            "_npm_version": lambda: "not found",
        }
        for name, fn in mocks.items():
            monkeypatch.setattr(capture_baseline, name, fn)

        # Patch platform.platform so _write_baseline_doc gets a string
        monkeypatch.setattr(capture_baseline.platform, "platform", lambda: "Linux-5.4-x86_64")

        repo = Path(__file__).resolve().parents[1]  # repo root
        out = repo / "artifacts" / "release" / "test-gate-regression"
        out.mkdir(parents=True, exist_ok=True)

        with pytest.raises(SystemExit) as exc_info:
            capture_baseline.capture(repo, out)
        assert exc_info.value.code == 1, (
            "capture() must exit 1 when any sub-check fails (test_results, "
            "security_results, OR build_results). Old bug: exited 0."
        )

    def test_capture_passes_when_all_green(self, monkeypatch):
        """When all sub-checks pass, capture() must exit 0 (no SystemExit)."""
        from scripts.production import capture_baseline

        mocks = {
            "_run_tests": lambda repo: {"gate": "pytest", "status": "pass", "returncode": 0,
                                         "passed": 10, "failed": 0, "errors": 0, "summary": "10 passed",
                                         "duration_seconds": 0.1},
            "_run_lint": lambda repo: {"gate": "ruff", "status": "pass", "returncode": 0,
                                        "violation_count": 0, "output_summary": "ok", "duration_seconds": 0.1},
            "_run_mypy": lambda repo: {"gate": "mypy", "status": "pass", "returncode": 0,
                                        "error_count": 0, "output_summary": "ok", "duration_seconds": 0.1},
            "_run_pip_audit": lambda repo: {"gate": "pip_audit", "status": "pass", "returncode": 0,
                                             "vulnerability_count": 0, "output_summary": "ok", "duration_seconds": 0.1},
            "_run_gitleaks": lambda repo: {"gate": "gitleaks", "status": "skipped", "returncode": 0,
                                            "output_summary": "", "duration_seconds": 0.0},
            "_run_npm_audit": lambda repo: {"gate": "npm_audit", "status": "warn", "returncode": 1,
                                             "vulnerability_count": 0, "duration_seconds": 0.1},
            "_run_frontend_build": lambda repo: {"gate": "frontend_build", "status": "pass", "returncode": 0,
                                                  "output_summary": "ok", "duration_seconds": 0.1},
            "_git_sha": lambda repo: "abc123",
            "_git_branch": lambda repo: "main",
            "_python_version": lambda: "3.13.0",
            "_node_version": lambda: "20.0.0",
            "_npm_version": lambda: "10.0.0",
        }
        for name, fn in mocks.items():
            monkeypatch.setattr(capture_baseline, name, fn)
        monkeypatch.setattr(capture_baseline.platform, "platform", lambda: "Linux-5.4-x86_64")

        repo = Path(__file__).resolve().parents[1]
        out = repo / "artifacts" / "release" / "test-gate-regression-pass"
        out.mkdir(parents=True, exist_ok=True)

        # Should NOT raise SystemExit — all checks pass
        capture_baseline.capture(repo, out)
