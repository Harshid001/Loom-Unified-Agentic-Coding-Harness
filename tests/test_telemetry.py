import json

from loom.business.usage_ledger import reset_usage_ledger
from loom.telemetry.ablation import AblationConfig, AblationHarness, AblationResult
from loom.telemetry.cost_tracker import CostTracker
from loom.telemetry.tracer import TelemetryTracer, TraceEvent


class TestCostTracker:
    def setup_method(self):
        reset_usage_ledger()

    def test_add_usage_accumulates_tokens(self):
        tracker = CostTracker(run_id="run_ct")
        tracker.add_usage("onboarding", 100, 50, 0.01)
        assert tracker.node_costs["onboarding"].prompt_tokens == 100
        assert tracker.node_costs["onboarding"].completion_tokens == 50
        assert tracker.node_costs["onboarding"].total_tokens == 150
        assert tracker.node_costs["onboarding"].cost_usd == 0.01

    def test_add_usage_multiple_calls_same_node(self):
        tracker = CostTracker(run_id="run_ct")
        tracker.add_usage("patcher", 200, 100, 0.02)
        tracker.add_usage("patcher", 300, 150, 0.03)
        assert tracker.node_costs["patcher"].prompt_tokens == 500
        assert tracker.node_costs["patcher"].completion_tokens == 250
        assert tracker.node_costs["patcher"].total_tokens == 750
        assert tracker.node_costs["patcher"].cost_usd == 0.05

    def test_add_usage_multiple_nodes(self):
        tracker = CostTracker(run_id="run_ct")
        tracker.add_usage("onboarding", 100, 50, 0.01)
        tracker.add_usage("patcher", 200, 100, 0.02)
        tracker.add_usage("verifier", 150, 75, 0.015)
        assert len(tracker.node_costs) == 3

    def test_add_usage_with_context_emits_ledger_event(self, tmp_path):
        from loom.business.usage_ledger import UsageLedger

        reset_usage_ledger()
        tracker = CostTracker(run_id="run_ctx", org_id="org_test")
        ledger = UsageLedger(storage_dir=str(tmp_path))
        import loom.business.usage_ledger as ul

        ul._ledger_instance = ledger

        tracker.add_usage_with_context(
            node_name="patcher",
            prompt_tokens=300,
            completion_tokens=150,
            cost_usd=0.03,
            model_id="claude-3",
            sandbox_tier="B",
            wall_clock_ms=5000,
            input_context="test context",
        )
        entries = ledger.get_entries_for_run("run_ctx")
        assert len(entries) == 1
        assert entries[0].model_id == "claude-3"
        assert entries[0].sandbox_tier == "B"
        assert entries[0].wall_clock_ms == 5000

    def test_add_usage_with_context_dedup(self, tmp_path):
        from loom.business.usage_ledger import UsageLedger

        reset_usage_ledger()
        tracker = CostTracker(run_id="run_dedup", org_id="org_test")
        ledger = UsageLedger(storage_dir=str(tmp_path))
        import loom.business.usage_ledger as ul

        ul._ledger_instance = ledger

        tracker.add_usage_with_context("step_a", 100, 50, 0.01, input_context="ctx_abc")
        tracker.add_usage_with_context("step_a", 100, 50, 0.01, input_context="ctx_abc")
        entries = ledger.get_entries_for_run("run_dedup")
        assert len(entries) == 2
        assert entries[0].attempt_number == 1
        assert entries[1].attempt_number == 2
        assert entries[0].dedup_key != entries[1].dedup_key

    def test_get_summary(self):
        tracker = CostTracker(run_id="run_s")
        tracker.add_usage("onboarding", 100, 50, 0.01)
        tracker.add_usage("patcher", 200, 100, 0.02)
        summary = tracker.get_summary()
        assert summary["run_id"] == "run_s"
        assert summary["total_prompt_tokens"] == 300
        assert summary["total_completion_tokens"] == 150
        assert summary["total_tokens"] == 450
        assert summary["total_cost_usd"] == 0.03
        assert "by_node" in summary
        assert len(summary["by_node"]) == 2

    def test_get_summary_empty(self):
        tracker = CostTracker(run_id="run_empty")
        summary = tracker.get_summary()
        assert summary["total_tokens"] == 0
        assert summary["total_cost_usd"] == 0.0

    def test_default_org_id(self):
        tracker = CostTracker(run_id="r")
        assert tracker.org_id == "default_org"


class TestAblationHarness:
    def test_get_ablation_matrix_has_four_configs(self):
        harness = AblationHarness()
        matrix = harness.get_ablation_matrix()
        assert len(matrix) == 4

    def test_matrix_includes_all_config_names(self):
        harness = AblationHarness()
        matrix = harness.get_ablation_matrix()
        names = {c["name"] for c in matrix}
        assert "baseline_naive" in names
        assert "loom_no_memory" in names
        assert "loom_no_context_ranking" in names
        assert "loom_full" in names

    def test_baseline_naive_has_all_disabled(self):
        harness = AblationHarness()
        cfg = harness.get_ablation_matrix()[0]
        assert cfg["config"]["memory_enabled"] is False
        assert cfg["config"]["context_ranking_enabled"] is False
        assert cfg["config"]["multi_agent_enabled"] is False
        assert cfg["config"]["verification_enabled"] is False

    def test_loom_full_has_all_enabled(self):
        harness = AblationHarness()
        cfg = harness.get_ablation_matrix()[3]
        assert cfg["config"]["memory_enabled"] is True
        assert cfg["config"]["context_ranking_enabled"] is True
        assert cfg["config"]["multi_agent_enabled"] is True
        assert cfg["config"]["verification_enabled"] is True

    def test_ablation_config_model(self):
        cfg = AblationConfig(memory_enabled=False, context_ranking_enabled=True, multi_agent_enabled=False)
        assert cfg.memory_enabled is False
        assert cfg.context_ranking_enabled is True
        assert cfg.multi_agent_enabled is False

    def test_ablation_result_model(self):
        result = AblationResult(
            config_name="test",
            config=AblationConfig(),
            success=True,
            total_cost_usd=0.05,
            total_tokens=1000,
            duration_seconds=12.5,
            verification_passed=True,
        )
        assert result.success is True
        assert result.total_cost_usd == 0.05


class TestTelemetryTracer:
    def test_log_event_buffers_in_memory(self, tmp_path):
        tracer = TelemetryTracer(run_id="run_t", log_dir=str(tmp_path))
        tracer.log_event("tool_call", "patcher", {"model": "claude"})
        assert len(tracer.events) == 1
        assert tracer.events[0].event_type == "tool_call"
        assert tracer.events[0].node_name == "patcher"
        assert tracer.events[0].data["model"] == "claude"

    def test_log_event_flushes_on_verification(self, tmp_path):
        tracer = TelemetryTracer(run_id="run_v", log_dir=str(tmp_path), batch_size=100)
        tracer.log_event("verification", "verifier", {"passed": True})
        trace_file = tmp_path / "trace_run_v.json"
        assert trace_file.exists()
        data = json.loads(trace_file.read_text())
        assert len(data) == 1
        assert data[0]["event_type"] == "verification"

    def test_log_event_flushes_on_batch_size(self, tmp_path):
        tracer = TelemetryTracer(run_id="run_b", log_dir=str(tmp_path), batch_size=3)
        for i in range(3):
            tracer.log_event("tool_call", f"agent_{i}")
        trace_file = tmp_path / "trace_run_b.json"
        assert trace_file.exists()
        data = json.loads(trace_file.read_text())
        assert len(data) == 3

    def test_log_event_flushes_on_error(self, tmp_path):
        tracer = TelemetryTracer(run_id="run_e", log_dir=str(tmp_path), batch_size=100)
        tracer.log_event("error", "patcher", {"msg": "fail"})
        trace_file = tmp_path / "trace_run_e.json"
        assert trace_file.exists()
        data = json.loads(trace_file.read_text())
        assert data[0]["event_type"] == "error"

    def test_log_event_flushes_on_completed(self, tmp_path):
        tracer = TelemetryTracer(run_id="run_c", log_dir=str(tmp_path), batch_size=100)
        tracer.log_event("completed", "pipeline")
        trace_file = tmp_path / "trace_run_c.json"
        assert trace_file.exists()

    def test_flush_to_disk_writes_all_events(self, tmp_path):
        tracer = TelemetryTracer(run_id="run_f", log_dir=str(tmp_path))
        for i in range(5):
            tracer.log_event("tool_call", f"agent_{i}")
        tracer.flush_to_disk()
        trace_file = tmp_path / "trace_run_f.json"
        data = json.loads(trace_file.read_text())
        assert len(data) == 5

    def test_close_flushes(self, tmp_path):
        tracer = TelemetryTracer(run_id="run_close", log_dir=str(tmp_path))
        tracer.log_event("tool_call", "onboarding")
        tracer.close()
        trace_file = tmp_path / "trace_run_close.json"
        assert trace_file.exists()

    def test_trace_event_timestamp_present(self):
        event = TraceEvent(run_id="r", event_type="test", node_name="n")
        assert event.timestamp > 0
        assert event.run_id == "r"

    def test_log_event_with_none_data(self, tmp_path):
        tracer = TelemetryTracer(run_id="run_n", log_dir=str(tmp_path))
        tracer.log_event("task_start", "onboarding")
        assert len(tracer.events) == 1
        assert tracer.events[0].data == {}

    def test_default_log_dir(self):
        tracer = TelemetryTracer(run_id="run_d")
        assert tracer.log_dir.exists()
        assert "traces" in str(tracer.log_dir)
        tracer.close()

    def test_run_complete_triggers_flush(self, tmp_path):
        tracer = TelemetryTracer(run_id="run_rc", log_dir=str(tmp_path), batch_size=100)
        tracer.log_event("run_complete", "pipeline")
        trace_file = tmp_path / "trace_run_rc.json"
        assert trace_file.exists()
