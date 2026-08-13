import asyncio

from loom.adapters.router import ModelRouter
from loom.orchestrator.state import OrchestratorState
from loom.orchestrator.task_graph import RunStatus, TaskGraph, compute_merge_decision
from loom.telemetry.cost_tracker import CostTracker
from loom.telemetry.tracer import TelemetryTracer


def _graph(run_id: str) -> TaskGraph:
    state = OrchestratorState(run_id=run_id, repo_path="/tmp/repo", issue_description="verification test")
    graph = TaskGraph(
        state,
        ModelRouter(default_model="gpt-4o", mock_mode=True),
        TelemetryTracer(run_id=run_id),
        CostTracker(run_id=run_id),
    )
    graph.get_sequence = lambda resume_from=None: []
    return graph


def test_failed_verification_is_never_merged():
    graph = _graph("run_failed_verification")
    graph.state.verification_passed = False
    final_state = asyncio.run(graph.run())

    assert final_state.shared_data["merge_decision"]["auto_merge"] is False
    assert final_state.shared_data["run_status"] == RunStatus.FAILED


def test_verified_but_low_confidence_requires_evidence_review():
    graph = _graph("run_human_review")
    graph.state.verification_passed = True
    graph.state.shared_data["confidence_score"] = 0.80
    graph.state.shared_data["auto_merge_threshold"] = 0.95
    final_state = asyncio.run(graph.run())

    assert final_state.shared_data["merge_decision"]["auto_merge"] is False
    assert final_state.shared_data["merge_decision"]["needs_human_review"] is True
    assert final_state.shared_data["run_status"] == RunStatus.EVIDENCE_REVIEW


def test_only_verified_auto_merge_can_be_merged():
    graph = _graph("run_auto_merge")
    graph.state.verification_passed = True
    graph.state.shared_data["confidence_score"] = 0.99
    graph.state.shared_data["auto_merge_threshold"] = 0.95
    final_state = asyncio.run(graph.run())

    assert final_state.shared_data["merge_decision"]["auto_merge"] is True
    assert final_state.shared_data["run_status"] == RunStatus.MERGED


def test_merge_decision_false_verification_is_never_auto_merge():
    decision = compute_merge_decision(
        verification_passed=False,
        confidence=1.0,
        threshold=0.0,
    )
    assert decision["auto_merge"] is False
    assert decision["actor"] == "none"
