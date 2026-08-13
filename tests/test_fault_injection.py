import pytest

from scripts.fault_injection import execute, validate_guard


def test_fault_injection_requires_staging():
    with pytest.raises(RuntimeError, match="only when LOOM_ENV=staging"):
        validate_guard(environment="production", enabled=True, confirmed=True)


def test_fault_injection_requires_explicit_enablement():
    with pytest.raises(RuntimeError, match="FAULT_INJECTION_ENABLED"):
        validate_guard(environment="staging", enabled=False, confirmed=True)


def test_fault_injection_requires_confirmation():
    with pytest.raises(RuntimeError, match="--confirm-staging"):
        validate_guard(environment="staging", enabled=True, confirmed=False)


def test_fault_injection_executes_disrupt_and_recovery(monkeypatch):
    responses = iter([
        (0, "disrupt", 0.12),
        (0, "recover", 0.34),
    ])
    monkeypatch.setattr("scripts.fault_injection.run_command", lambda command, timeout: next(responses))

    evidence = execute(
        scenario="unit-test",
        disrupt_command="disrupt",
        recover_command="recover",
        timeout=5,
        recovery_timeout=5,
    )

    assert evidence["status"] == "passed"
    assert evidence["disruption"]["exit_code"] == 0
    assert evidence["recovery"]["exit_code"] == 0
    assert evidence["disruption"]["output"] == "disrupt"
    assert evidence["recovery"]["output"] == "recover"


def test_fault_injection_reports_failed_recovery(monkeypatch):
    responses = iter([
        (0, "disrupt", 0.1),
        (2, "recover failed", 0.2),
    ])
    monkeypatch.setattr("scripts.fault_injection.run_command", lambda command, timeout: next(responses))

    evidence = execute(
        scenario="unit-test-failure",
        disrupt_command="disrupt",
        recover_command="recover",
        timeout=5,
        recovery_timeout=5,
    )

    assert evidence["status"] == "failed"
    assert evidence["recovery"]["exit_code"] == 2
