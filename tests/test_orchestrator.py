import httpx
import pytest

from loom.adapters.router import ModelRouter
from loom.api.webhooks import WebhookEngine, WebhookEventType, WebhookSubscription
from loom.orchestrator.agents.verifier import VerifierAgent
from loom.orchestrator.state import OrchestratorState
from loom.orchestrator.task_graph import RunStatus, TaskGraph, compute_merge_decision
from loom.telemetry.cost_tracker import CostTracker
from loom.telemetry.tracer import TelemetryTracer
from loom.verification.bundle import EvidenceBundler


class FakeAsyncClient:
    def __init__(self):
        self.calls = []

    async def post(self, url, content=None, headers=None, timeout=None):
        self.calls.append({"url": url, "content": content, "headers": headers})
        return httpx.Response(200, text="ok")

    async def aclose(self):
        pass


class TestComputeMergeDecision:
    def test_auto_merge_above_threshold(self):
        decision = compute_merge_decision(
            verification_passed=True,
            confidence=0.96,
            threshold=0.95,
            verification_decision="auto_merge",
        )
        assert decision["auto_merge"] is True
        assert decision["needs_human_review"] is False
        assert decision["security_hold"] is False
        assert decision["actor"] == "agent"

    def test_human_review_below_threshold(self):
        decision = compute_merge_decision(verification_passed=True, confidence=0.90, threshold=0.95)
        assert decision["auto_merge"] is False
        assert decision["needs_human_review"] is True
        assert decision["actor"] == "human"

    def test_security_hold_never_auto_merges(self):
        decision = compute_merge_decision(
            verification_passed=True,
            confidence=1.0,
            threshold=0.85,
            verification_decision="security_hold",
        )
        assert decision["security_hold"] is True
        assert decision["auto_merge"] is False
        assert decision["needs_human_review"] is True
        assert decision["actor"] == "human"

    def test_unverified_never_auto_merges(self):
        decision = compute_merge_decision(verification_passed=False, confidence=0.99, threshold=0.85)
        assert decision["auto_merge"] is False
        assert decision["actor"] == "none"

    def test_conflict_never_auto_merges_even_at_full_confidence(self):
        decision = compute_merge_decision(
            verification_passed=True,
            confidence=1.0,
            threshold=0.85,
            conflict_detected=True,
        )
        assert decision["conflict_detected"] is True
        assert decision["auto_merge"] is False
        assert decision["needs_human_review"] is True
        assert decision["actor"] == "human"


def test_planner_node_in_sequence_between_reproduction_and_patcher():
    names = [name for name, _ in TaskGraph.NODE_SEQUENCE]
    assert names.index("planner") > names.index("reproduction")
    assert names.index("planner") < names.index("patcher")
    assert TaskGraph.STATUS_NODE_MAP["planner"] == RunStatus.PLANNING


@pytest.mark.asyncio
async def test_task_graph_execution(tmp_path):
    run_id = "test_run_001"
    state = OrchestratorState(run_id=run_id, repo_path=str(tmp_path), issue_description="Fix null pointer exception")
    router = ModelRouter(mock_mode=True)
    tracer = TelemetryTracer(run_id=run_id, log_dir=str(tmp_path / "traces"))
    cost_tracker = CostTracker(run_id=run_id)

    task_graph = TaskGraph(state, router, tracer, cost_tracker)
    final_state = await task_graph.run()

    assert "onboarding" in final_state.nodes
    assert final_state.nodes["onboarding"].status == "completed"
    assert "reproduction" in final_state.nodes
    assert "planner" in final_state.nodes
    assert final_state.nodes["planner"].status == "completed"
    assert final_state.shared_data.get("plan") is not None
    assert "patcher" in final_state.nodes
    assert "verifier" in final_state.nodes
    assert "reviewer" in final_state.nodes
    assert final_state.shared_data.get("reviewer_report") is not None


@pytest.mark.asyncio
async def test_task_graph_records_merge_decision(tmp_path):
    run_id = "test_run_002"
    state = OrchestratorState(run_id=run_id, repo_path=str(tmp_path), issue_description="Fix null pointer exception")
    router = ModelRouter(mock_mode=True)
    tracer = TelemetryTracer(run_id=run_id, log_dir=str(tmp_path / "traces"))
    cost_tracker = CostTracker(run_id=run_id)

    task_graph = TaskGraph(state, router, tracer, cost_tracker)
    final_state = await task_graph.run()

    decision = final_state.shared_data.get("merge_decision")
    assert decision is not None
    assert "confidence_score" in decision
    assert "auto_merge_threshold" in decision
    assert decision["auto_merge"] is False
    assert decision["needs_human_review"] is True
    assert final_state.shared_data.get("confidence_score") is not None
    assert final_state.shared_data.get("verification_decision") in (
        "auto_merge",
        "human_review",
        "reject_repro_missing",
        "reject_regression",
        "reject_build_failure",
        "security_hold",
    )


@pytest.mark.asyncio
async def test_task_graph_dispatches_lifecycle_webhooks(tmp_path, monkeypatch):
    run_id = "test_run_003"
    state = OrchestratorState(run_id=run_id, repo_path=str(tmp_path), issue_description="Fix null pointer exception")
    state.shared_data["org_id"] = "org_webhook"
    state.shared_data["mock_mode"] = True

    engine = WebhookEngine(storage_dir=str(tmp_path / "webhooks"))
    engine._http = FakeAsyncClient()
    engine.register(
        WebhookSubscription(
            id="sub_lifecycle",
            org_id="org_webhook",
            url="https://example.com/hook",
            events={
                WebhookEventType.RUN_QUEUED,
                WebhookEventType.RUN_COMPLETED,
                WebhookEventType.EVIDENCE_READY,
            },
            max_retries=1,
            retry_backoff_base_seconds=0.01,
        )
    )

    async def fake_verifier_execute(self, state):
        state.verification_passed = True
        state.shared_data["verification_decision"] = "auto_merge"
        state.shared_data["confidence_score"] = 1.0
        return {"overall_success": True, "decision": "auto_merge"}

    monkeypatch.setattr(VerifierAgent, "execute", fake_verifier_execute)

    bundler = EvidenceBundler(output_dir=str(tmp_path / "evidence"))
    task_graph = TaskGraph(
        state,
        ModelRouter(mock_mode=True),
        TelemetryTracer(run_id=run_id, log_dir=str(tmp_path / "traces")),
        CostTracker(run_id=run_id),
        webhook_engine=engine,
        evidence_bundler=bundler,
    )
    await task_graph.run()

    assert state.shared_data["evidence_exported"] is True
    assert state.shared_data["evidence_bundle_chain_hash"]
    assert (tmp_path / "evidence" / f"evidence_{run_id}.json").exists()

    delivered = engine.get_subscriptions("org_webhook")[0]
    assert delivered.active
    event_names = set()
    for client_call in engine._http.calls:
        import json as _json

        event_names.add(_json.loads(client_call["content"]).get("event"))
    assert WebhookEventType.RUN_QUEUED in event_names
    assert WebhookEventType.RUN_COMPLETED in event_names
    assert WebhookEventType.EVIDENCE_READY in event_names


@pytest.mark.asyncio
async def test_task_graph_security_hold_state(tmp_path, monkeypatch):
    run_id = "test_run_004"
    state = OrchestratorState(run_id=run_id, repo_path=str(tmp_path), issue_description="Fix null pointer exception")
    state.shared_data["repo_map"] = {"files": []}
    state.shared_data["onboarding_summary"] = {"files": []}
    state.reproduction_test = "pytest tests/test_repro.py"
    state.shared_data["reproduction_evidence"] = {"status": "reproduced"}

    async def fake_verifier_execute(self, state):
        state.verification_passed = True
        state.shared_data["verification_decision"] = "security_hold"
        state.shared_data["confidence_score"] = 1.0
        return {"overall_success": True, "decision": "security_hold"}

    monkeypatch.setattr(VerifierAgent, "execute", fake_verifier_execute)

    task_graph = TaskGraph(
        state,
        ModelRouter(mock_mode=True),
        TelemetryTracer(run_id=run_id, log_dir=str(tmp_path / "traces")),
        CostTracker(run_id=run_id),
    )
    final_state = await task_graph.run()

    assert task_graph.run_status == RunStatus.SECURITY_HOLD
    decision = final_state.shared_data["merge_decision"]
    assert decision["security_hold"] is True
    assert decision["auto_merge"] is False


@pytest.mark.asyncio
async def test_task_graph_conflict_resolution_state(tmp_path, monkeypatch):
    from loom.orchestrator.agents.patcher import PatcherAgent

    run_id = "test_run_conflict"
    state = OrchestratorState(run_id=run_id, repo_path=str(tmp_path), issue_description="Fix null pointer exception")

    async def fake_patcher_execute(self, state):
        state.patch_diff = "--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-old\n+new\n"
        state.snapshot_id = "snap_conflict"
        state.shared_data["conflict_detected"] = True
        return {"patch_diff": state.patch_diff, "snapshot_id": "snap_conflict", "conflict_detected": True}

    async def fake_verifier_execute(self, state):
        state.verification_passed = True
        state.shared_data["verification_decision"] = "auto_merge"
        state.shared_data["confidence_score"] = 1.0
        return {"overall_success": True, "decision": "auto_merge"}

    monkeypatch.setattr(PatcherAgent, "execute", fake_patcher_execute)
    monkeypatch.setattr(VerifierAgent, "execute", fake_verifier_execute)

    task_graph = TaskGraph(
        state,
        ModelRouter(mock_mode=True),
        TelemetryTracer(run_id=run_id, log_dir=str(tmp_path / "traces")),
        CostTracker(run_id=run_id),
    )
    final_state = await task_graph.run()

    assert task_graph.run_status == RunStatus.CONFLICT_RESOLUTION
    decision = final_state.shared_data["merge_decision"]
    assert decision["conflict_detected"] is True
    assert decision["auto_merge"] is False
    assert decision["actor"] == "human"


@pytest.mark.asyncio
async def test_evidence_bundle_contains_merge_decision(tmp_path):
    run_id = "test_run_bundle"
    state = OrchestratorState(run_id=run_id, repo_path=str(tmp_path), issue_description="Fix null pointer exception")

    bundler = EvidenceBundler(output_dir=str(tmp_path / "evidence"))
    task_graph = TaskGraph(
        state,
        ModelRouter(mock_mode=True),
        TelemetryTracer(run_id=run_id, log_dir=str(tmp_path / "traces")),
        CostTracker(run_id=run_id),
        evidence_bundler=bundler,
    )
    await task_graph.run()

    import json as _json

    bundle_data = _json.loads((tmp_path / "evidence" / f"evidence_{run_id}.json").read_text(encoding="utf-8"))
    assert "merge_decision" in bundle_data
    assert "actor" in bundle_data["merge_decision"]



@pytest.mark.asyncio
async def test_task_graph_commit_gateway_security_hold(tmp_path, monkeypatch):
    from loom.orchestrator.agents.onboarding import OnboardingAgent
    from loom.orchestrator.agents.patcher import PatcherAgent
    from loom.orchestrator.agents.reproduction import ReproductionAgent

    run_id = "test_run_gateway_block"
    state = OrchestratorState(run_id=run_id, repo_path=str(tmp_path), issue_description="Fix auth bypass")
    state.shared_data["org_id"] = "org_gateway_test"
    state.shared_data["mock_mode"] = True

    async def fake_onboarding(self, state):
        state.shared_data["repo_map"] = {"files": []}
        state.shared_data["onboarding_summary"] = {"summary": "ok"}
        return {"summary": "ok"}

    async def fake_reproduction(self, state):
        state.reproduction_test = "def test_repro(): pass"
        state.shared_data["reproduction_evidence"] = {"status": "reproduced"}
        return {"status": "reproduced"}

    async def fake_patcher_gateway_block(self, state):
        state.patch_diff = "--- a/auth/login.py\n+++ b/auth/login.py\n@@ -1,3 +1,3 @@\n-old\n+new\n"
        state.snapshot_id = "snap_gateway_block"
        state.shared_data["commit_gateway"] = {
            "allowed": False,
            "status": "security_hold",
            "blocked_paths": ["auth/login.py"],
            "reason": "Sensitive paths blocked by commit gateway: auth/login.py",
        }
        state.shared_data["security_hold_reason"] = "Sensitive paths blocked by commit gateway: auth/login.py"
        return {"patch_diff": state.patch_diff, "snapshot_id": "snap_gateway_block", "summary": "blocked"}

    monkeypatch.setattr(OnboardingAgent, "execute", fake_onboarding)
    monkeypatch.setattr(ReproductionAgent, "execute", fake_reproduction)
    monkeypatch.setattr(PatcherAgent, "execute", fake_patcher_gateway_block)

    task_graph = TaskGraph(
        state,
        ModelRouter(mock_mode=True),
        TelemetryTracer(run_id=run_id, log_dir=str(tmp_path / "traces")),
        CostTracker(run_id=run_id),
    )
    final_state = await task_graph.run()

    assert task_graph.run_status == RunStatus.SECURITY_HOLD
    assert final_state.shared_data["commit_gateway"]["allowed"] is False
    assert final_state.shared_data["security_hold_reason"] is not None
    assert "onboarding" in final_state.nodes
    assert "reproduction" in final_state.nodes
    assert "planner" in final_state.nodes
    assert "patcher" in final_state.nodes
    assert "verifier" not in final_state.nodes


@pytest.mark.asyncio
async def test_task_graph_clean_patch_proceeds_past_patcher(tmp_path, monkeypatch):
    from loom.orchestrator.agents.patcher import PatcherAgent

    run_id = "test_run_clean_patch"
    state = OrchestratorState(run_id=run_id, repo_path=str(tmp_path), issue_description="Fix typo in readme")

    async def fake_patcher_clean(self, state):
        state.patch_diff = "--- a/README.md\n+++ b/README.md\n@@ -1 +1 @@\n-Hello\n+Hello World\n"
        state.snapshot_id = "snap_clean"
        state.shared_data["commit_gateway"] = {"allowed": True, "status": "allowed", "blocked_paths": [], "reason": ""}
        return {"patch_diff": state.patch_diff, "snapshot_id": "snap_clean", "summary": "applied"}

    monkeypatch.setattr(PatcherAgent, "execute", fake_patcher_clean)

    task_graph = TaskGraph(
        state,
        ModelRouter(mock_mode=True),
        TelemetryTracer(run_id=run_id, log_dir=str(tmp_path / "traces")),
        CostTracker(run_id=run_id),
    )
    final_state = await task_graph.run()

    assert task_graph.run_status != RunStatus.SECURITY_HOLD
    assert final_state.shared_data["commit_gateway"]["allowed"] is True
    assert "verifier" in final_state.nodes
    assert "reviewer" in final_state.nodes



@pytest.mark.asyncio
async def test_dag_guard_onboarding_requires_repo_map(tmp_path, monkeypatch):
    from loom.orchestrator.agents.onboarding import OnboardingAgent

    run_id = "test_dag_guard_onboarding"
    state = OrchestratorState(run_id=run_id, repo_path=str(tmp_path), issue_description="Fix thing")

    async def fake_onboarding(self, state):
        return {"total_files": 0}

    monkeypatch.setattr(OnboardingAgent, "execute", fake_onboarding)

    task_graph = TaskGraph(
        state,
        ModelRouter(mock_mode=True),
        TelemetryTracer(run_id=run_id, log_dir=str(tmp_path / "traces")),
        CostTracker(run_id=run_id),
    )
    final_state = await task_graph.run()

    assert task_graph.run_status == RunStatus.FAILED
    assert "reproduction" not in final_state.nodes


@pytest.mark.asyncio
async def test_dag_guard_reproduction_requires_synthesized_test(tmp_path, monkeypatch):
    from loom.orchestrator.agents.reproduction import ReproductionAgent

    run_id = "test_dag_guard_repro"
    state = OrchestratorState(run_id=run_id, repo_path=str(tmp_path), issue_description="Fix thing")

    async def fake_reproduction(self, state):
        state.reproduction_test = ""
        return {}

    monkeypatch.setattr(ReproductionAgent, "execute", fake_reproduction)

    task_graph = TaskGraph(
        state,
        ModelRouter(mock_mode=True),
        TelemetryTracer(run_id=run_id, log_dir=str(tmp_path / "traces")),
        CostTracker(run_id=run_id),
    )
    final_state = await task_graph.run()

    assert task_graph.run_status == RunStatus.FAILED
    assert "planner" not in final_state.nodes
