"""Tests for SLA and System Health Status Monitor (spec §6)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from loom.api.app import create_app
from loom.telemetry.status import compute_sla_metrics, get_system_status, healthy_status


def test_healthy_status():
    status = healthy_status()
    assert status.healthy is True
    assert status.generated_at > 0


def test_get_system_status_snapshot():
    snapshot = get_system_status()
    assert snapshot.healthy is True
    assert snapshot.system_status in {"operational", "degraded", "outage"}
    assert "api" in snapshot.components
    assert "database" in snapshot.components
    assert "job_queue" in snapshot.components
    assert "sandbox_runner" in snapshot.components

    data = snapshot.to_dict()
    assert "generated_at" in data
    assert "sla_metrics" in data
    assert "solo" in data["sla_metrics"]
    assert "team" in data["sla_metrics"]
    assert "enterprise" in data["sla_metrics"]


def test_compute_sla_metrics():
    metrics = compute_sla_metrics()
    assert metrics["solo"].target_uptime_pct == 99.0
    assert metrics["team"].target_uptime_pct == 99.5
    assert metrics["enterprise"].target_uptime_pct == 99.9

    assert metrics["team"].target_p50_min == 4.0
    assert metrics["team"].target_p95_min == 12.0
    assert metrics["enterprise"].target_p50_min == 3.0
    assert metrics["enterprise"].target_p95_min == 8.0

    assert metrics["solo"].meeting_sla is True
    assert metrics["team"].meeting_sla is True
    assert metrics["enterprise"].meeting_sla is True


def test_system_status_endpoint():
    app = create_app()
    client = TestClient(app)

    res = client.get("/api/v1/system/status")
    assert res.status_code == 200
    data = res.json()
    assert data["healthy"] is True
    assert "components" in data
    assert "sla_metrics" in data

    res_compat = client.get("/status")
    assert res_compat.status_code == 200
    assert res_compat.json()["healthy"] is True
