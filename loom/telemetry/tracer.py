import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger("loom.telemetry")


class TraceEvent(BaseModel):
    timestamp: float = Field(default_factory=time.time)
    run_id: str
    event_type: str  # "task_start", "tool_call", "context_retrieval", "patch_applied", "verification", "error"
    node_name: str
    data: Dict[str, Any] = Field(default_factory=dict)


class TelemetryTracer:
    """OpenTelemetry-compatible event tracer recording plan revisions, tool calls, and verification steps."""

    def __init__(
        self, run_id: str, log_dir: Optional[str] = None, otlp_endpoint: Optional[str] = None, batch_size: int = 5
    ):
        self.run_id = run_id
        if not log_dir:
            log_dir = str(Path.home() / ".loom" / "traces")
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.events: List[TraceEvent] = []
        self.batch_size = batch_size
        self._unflushed_count = 0

        self.otlp_endpoint = otlp_endpoint or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
        self.otel_tracer = None
        if self.otlp_endpoint:
            self._init_otlp_exporter()

    def _init_otlp_exporter(self):
        try:
            from opentelemetry import trace
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor

            provider = TracerProvider()
            processor = BatchSpanProcessor(OTLPSpanExporter(endpoint=self.otlp_endpoint))
            provider.add_span_processor(processor)
            trace.set_tracer_provider(provider)
            self.otel_tracer = trace.get_tracer("loom.telemetry")
        except Exception as e:
            logger.info(f"OTLP Exporter not loaded: {e}. Falling back to file-based JSON tracing.")

    def log_event(self, event_type: str, node_name: str, data: Optional[Dict[str, Any]] = None):
        event = TraceEvent(run_id=self.run_id, event_type=event_type, node_name=node_name, data=data or {})
        self.events.append(event)
        self._unflushed_count += 1

        # Batch flush to disk when buffer limit reached or critical lifecycle event occurs
        if self._unflushed_count >= self.batch_size or event_type in (
            "verification",
            "error",
            "completed",
            "run_complete",
        ):
            self.flush_to_disk()

        if self.otel_tracer:
            try:
                with self.otel_tracer.start_as_current_span(f"{event_type}:{node_name}") as span:
                    span.set_attribute("loom.run_id", self.run_id)
                    span.set_attribute("loom.node_name", node_name)
                    span.set_attribute("loom.event_type", event_type)
                    if data:
                        span.set_attribute("loom.data", json.dumps(data))
            except Exception as e:
                logger.warning(f"Failed to export OpenTelemetry span: {e}")

    def flush_to_disk(self):
        file_path = self.log_dir / f"trace_{self.run_id}.json"
        events_json = [e.model_dump() for e in self.events]
        file_path.write_text(json.dumps(events_json, indent=2), encoding="utf-8")
        self._unflushed_count = 0

    def close(self):
        """Ensure all buffered trace events are written on shutdown."""
        self.flush_to_disk()
