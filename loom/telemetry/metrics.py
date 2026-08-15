"""PRD-026 — Production Observability & Metrics Registry.

Defines canonical Prometheus metric instruments for Loom:
  - loom_requests_total (Counter)
  - loom_request_duration_seconds (Histogram)
  - loom_active_runs (Gauge)
  - loom_run_duration_seconds (Histogram)
  - loom_sandbox_executions_total (Counter)
  - loom_model_token_usage_total (Counter)
  - loom_security_hold_events_total (Counter)

Gracefully falls back to dummy metrics if prometheus_client is not installed.
"""

from __future__ import annotations

from typing import Any

try:
    from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, Counter, Gauge, Histogram, generate_latest
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    CONTENT_TYPE_LATEST = "text/plain"

    def generate_latest(registry: Any = None) -> bytes:  # type: ignore[misc]
        return b"# prometheus_client not installed\n"

    class DummyMetric:
        def labels(self, **kwargs: Any) -> "DummyMetric":
            return self

        def inc(self, amount: float = 1) -> None:
            pass

        def dec(self, amount: float = 1) -> None:
            pass

        def set(self, value: float) -> None:
            pass

        def observe(self, amount: float) -> None:
            pass

    class DummyMetricFactory:
        def __call__(self, *args: Any, **kwargs: Any) -> DummyMetric:
            return DummyMetric()

    Counter = DummyMetricFactory()  # type: ignore
    Gauge = DummyMetricFactory()    # type: ignore
    Histogram = DummyMetricFactory()  # type: ignore
    REGISTRY = None  # type: ignore


def _safe_metric(metric_cls: Any, name: str, documentation: str, labelnames: list[str] | None = None) -> Any:
    if not PROMETHEUS_AVAILABLE or REGISTRY is None:
        return DummyMetricFactory()()
    try:
        if name in getattr(REGISTRY, "_names_to_collectors", {}):
            return REGISTRY._names_to_collectors[name]
        if labelnames:
            return metric_cls(name, documentation, labelnames)
        return metric_cls(name, documentation)
    except Exception:
        try:
            if name in getattr(REGISTRY, "_names_to_collectors", {}):
                return REGISTRY._names_to_collectors[name]
        except Exception:
            pass
        return DummyMetricFactory()()


# Canonical instruments
REQUEST_COUNT = _safe_metric(Counter, "loom_requests_total", "Total API HTTP requests", ["method", "endpoint", "status"])
REQUEST_LATENCY = _safe_metric(Histogram, "loom_request_duration_seconds", "HTTP request latency seconds", ["endpoint"])
ACTIVE_RUNS_GAUGE = _safe_metric(Gauge, "loom_active_runs", "Number of currently active runs in orchestrator")
RUN_LATENCY = _safe_metric(Histogram, "loom_run_duration_seconds", "Total end-to-end run execution duration")
SANDBOX_EXEC_COUNT = _safe_metric(Counter, "loom_sandbox_executions_total", "Total sandbox process executions", ["tier", "status"])
MODEL_TOKEN_COUNT = _safe_metric(Counter, "loom_model_token_usage_total", "Total LLM tokens consumed", ["model", "direction"])
SECURITY_HOLD_COUNT = _safe_metric(Counter, "loom_security_hold_events_total", "Total security hold events triggered")

