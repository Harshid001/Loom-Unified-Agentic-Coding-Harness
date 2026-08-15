import argparse
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from scripts.load_slo_gate import Result, main, one_request, percentile, run


def test_percentile_calculations():
    assert percentile([], 0.95) == 0.0
    assert percentile([1.0], 0.50) == 1.0
    assert percentile([1.0], 0.95) == 1.0

    data = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    p50 = percentile(data, 0.50)
    p95 = percentile(data, 0.95)
    p99 = percentile(data, 0.99)
    assert 5.0 <= p50 <= 6.0
    assert p95 >= 9.0
    assert p99 == 10.0


@pytest.mark.asyncio
async def test_one_request_success():
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_client.post.return_value = mock_response

    res = await one_request(mock_client, "http://localhost:8000", "test-key", "/workspace", 1)
    assert res.status == 200
    assert res.latency >= 0.0
    assert res.error == ""


@pytest.mark.asyncio
async def test_one_request_exception():
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post.side_effect = httpx.ConnectError("Connection refused")

    res = await one_request(mock_client, "http://localhost:8000", "test-key", "/workspace", 1)
    assert res.status == 0
    assert "Connection refused" in res.error


@pytest.mark.asyncio
async def test_run_slo_gate_passed(tmp_path: Path):
    evidence_file = tmp_path / "evidence.json"
    args = argparse.Namespace(
        base_url="http://localhost:8000",
        api_key="secret",
        repo_path="/workspace",
        concurrency=2,
        requests=5,
        timeout=10.0,
        max_error_rate=0.05,
        max_p95=1.0,
        max_p99=2.0,
        min_throughput=0.1,
        evidence=evidence_file,
    )

    with patch("scripts.load_slo_gate.one_request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = Result(latency=0.05, status=200, error="")
        exit_code = await run(args)

    assert exit_code == 0
    assert evidence_file.exists()
    evidence = json.loads(evidence_file.read_text(encoding="utf-8"))
    assert evidence["status"] == "passed"
    assert evidence["requests"] == 5
    assert evidence["successes"] == 5
    assert evidence["failures"] == 0
    assert evidence["error_rate"] == 0.0


@pytest.mark.asyncio
async def test_run_slo_gate_failed_error_rate(tmp_path: Path):
    evidence_file = tmp_path / "evidence.json"
    args = argparse.Namespace(
        base_url="http://localhost:8000",
        api_key="secret",
        repo_path="/workspace",
        concurrency=2,
        requests=4,
        timeout=10.0,
        max_error_rate=0.01,
        max_p95=1.0,
        max_p99=2.0,
        min_throughput=0.1,
        evidence=evidence_file,
    )

    with patch("scripts.load_slo_gate.one_request", new_callable=AsyncMock) as mock_req:
        mock_req.side_effect = [
            Result(latency=0.05, status=200),
            Result(latency=0.05, status=500),
            Result(latency=0.05, status=200),
            Result(latency=0.05, status=200),
        ]
        exit_code = await run(args)

    assert exit_code == 1
    evidence = json.loads(evidence_file.read_text(encoding="utf-8"))
    assert evidence["status"] == "failed"
    assert any("error rate" in r for r in evidence["failure_reasons"])


@pytest.mark.asyncio
async def test_run_slo_gate_failed_latency_p95(tmp_path: Path):
    evidence_file = tmp_path / "evidence.json"
    args = argparse.Namespace(
        base_url="http://localhost:8000",
        api_key="secret",
        repo_path="/workspace",
        concurrency=2,
        requests=5,
        timeout=10.0,
        max_error_rate=0.1,
        max_p95=0.10,
        max_p99=2.0,
        min_throughput=0.1,
        evidence=evidence_file,
    )

    with patch("scripts.load_slo_gate.one_request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = Result(latency=0.50, status=200)
        exit_code = await run(args)

    assert exit_code == 1
    evidence = json.loads(evidence_file.read_text(encoding="utf-8"))
    assert evidence["status"] == "failed"
    assert any("p95" in r for r in evidence["failure_reasons"])


def test_main_cli_argument_validation(monkeypatch):
    monkeypatch.setattr("sys.argv", ["load_slo_gate.py", "--base-url", "http://localhost:8000", "--api-key", "k", "--repo-path", "/r", "--concurrency", "0"])
    with pytest.raises(SystemExit):
        main()

    monkeypatch.setattr("sys.argv", ["load_slo_gate.py", "--base-url", "http://localhost:8000", "--api-key", "k", "--repo-path", "/r", "--max-error-rate", "1.5"])
    with pytest.raises(SystemExit):
        main()
