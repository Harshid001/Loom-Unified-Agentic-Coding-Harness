import pytest

from scripts.recovery_probe import execute, probe_until_healthy, validate_guard


def test_recovery_probe_requires_staging():
    with pytest.raises(RuntimeError, match="only when LOOM_ENV=staging"):
        validate_guard(environment="production", enabled=True, confirmed=True)


def test_recovery_probe_requires_enablement():
    with pytest.raises(RuntimeError, match="FAULT_INJECTION_ENABLED"):
        validate_guard(environment="staging", enabled=False, confirmed=True)


def test_recovery_probe_requires_explicit_confirmation():
    with pytest.raises(RuntimeError, match="--confirm-staging"):
        validate_guard(environment="staging", enabled=True, confirmed=False)


def test_probe_until_healthy_retries_until_success(monkeypatch):
    responses = iter([(1, "not ready", 0.01), (0, "ready", 0.01)])
    monkeypatch.setattr(
        "scripts.recovery_probe.run_command",
        lambda command, timeout: next(responses),
    )
    healthy, code, output, duration, attempts = probe_until_healthy(
        "health",
        timeout=2,
        interval=0.01,
    )

    assert healthy is True
    assert code == 0
    assert output == "ready"
    assert duration >= 0
    assert attempts == 2


def test_recovery_probe_requires_health_success(monkeypatch):
    calls = {"count": 0}

    def fake_run_command(command, timeout):
        calls["count"] += 1
        if calls["count"] == 1:
            return 0, "disrupted", 0.01
        if calls["count"] == 2:
            return 0, "restarted", 0.01
        return 1, "still unhealthy", 0.01

    monkeypatch.setattr("scripts.recovery_probe.run_command", fake_run_command)
    monkeypatch.setattr("scripts.recovery_probe.time.sleep", lambda _: None)

    evidence = execute(
        scenario="redis-outage",
        disrupt_command="stop redis",
        recover_command="start redis",
        health_command="redis health",
        disruption_timeout=5,
        recovery_timeout=5,
        health_timeout=0.01,
        health_interval=0.001,
    )

    assert evidence["status"] == "failed"
    assert evidence["recovery"]["exit_code"] == 0
    assert evidence["health_probe"]["passed"] is False
    assert calls["count"] >= 3


def test_recovery_probe_passes_only_after_health_recovers(monkeypatch):
    responses = iter(
        [
            (0, "disrupted", 0.01),
            (0, "restarted", 0.01),
            (0, "healthy", 0.01),
        ]
    )
    monkeypatch.setattr(
        "scripts.recovery_probe.run_command",
        lambda command, timeout: next(responses),
    )

    evidence = execute(
        scenario="api-restart",
        disrupt_command="restart api",
        recover_command="confirm api process",
        health_command="curl /health/ready",
        disruption_timeout=5,
        recovery_timeout=5,
        health_timeout=5,
        health_interval=0.01,
    )

    assert evidence["status"] == "passed"
    assert evidence["health_probe"]["passed"] is True
    assert evidence["health_probe"]["attempts"] == 1
