import pytest

from loom.adapters.router import ModelRouter
from loom.orchestrator.agents.onboarding import OnboardingAgent
from loom.orchestrator.agents.patcher import PatcherAgent
from loom.orchestrator.agents.planner import PlannerAgent
from loom.orchestrator.agents.reproduction import ReproductionAgent
from loom.orchestrator.agents.reviewer import ReviewerAgent
from loom.orchestrator.agents.verifier import VerifierAgent
from loom.orchestrator.state import OrchestratorState
from loom.orchestrator.task_graph import RunStatus, TaskGraph
from loom.telemetry.cost_tracker import CostTracker
from loom.telemetry.tracer import TelemetryTracer


@pytest.fixture(autouse=True)
def mock_onboarding_and_reproduction(monkeypatch):
    async def fake_onboarding(self, state):
        state.shared_data["repo_map"] = {"files": ["app.py"]}
        state.shared_data["onboarding_summary"] = {"project_type": "python", "test_framework": "pytest"}
        return {"repo_map": state.shared_data["repo_map"], "summary": state.shared_data["onboarding_summary"]}

    async def fake_reproduction(self, state):
        state.reproduction_test = "def test_repro(): assert False"
        state.shared_data["reproduction_evidence"] = {"status": "reproduced"}
        return {"reproduction_test": state.reproduction_test, "status": "reproduced"}

    async def fake_planner(self, state):
        state.shared_data["plan"] = {"steps": ["Step 1", "Step 2"]}
        return {"plan": state.shared_data["plan"]}

    monkeypatch.setattr(OnboardingAgent, "execute", fake_onboarding)
    monkeypatch.setattr(ReproductionAgent, "execute", fake_reproduction)
    monkeypatch.setattr(PlannerAgent, "execute", fake_planner)


@pytest.mark.asyncio
async def test_high_risk_patch_halts_at_pending_approval(tmp_path, monkeypatch):
    run_id = "test_run_high_risk"
    state = OrchestratorState(run_id=run_id, repo_path=str(tmp_path), issue_description="Fix auth vulnerability")

    # High-risk: touches sensitive auth file
    async def fake_patcher(self, state):
        state.patch_diff = "--- a/src/auth/login.py\n+++ b/src/auth/login.py\n@@ -1 +1 @@\n-pass\n+validate()\n"
        state.snapshot_id = "snap_auth"
        state.shared_data["commit_gateway"] = {"allowed": True}
        return {"patch_diff": state.patch_diff, "snapshot_id": state.snapshot_id}

    verifier_called = False

    async def fake_verifier(self, state):
        nonlocal verifier_called
        verifier_called = True
        state.verification_passed = True
        state.shared_data["verification_decision"] = "auto_merge"
        state.shared_data["confidence_score"] = 0.99
        return {"overall_success": True}

    monkeypatch.setattr(PatcherAgent, "execute", fake_patcher)
    monkeypatch.setattr(VerifierAgent, "execute", fake_verifier)

    task_graph = TaskGraph(
        state,
        ModelRouter(mock_mode=True),
        TelemetryTracer(run_id=run_id, log_dir=str(tmp_path / "traces")),
        CostTracker(run_id=run_id),
    )

    final_state = await task_graph.run()

    # Must halt at PENDING_APPROVAL
    assert task_graph.run_status == RunStatus.PENDING_APPROVAL
    assert final_state.shared_data.get("approval_required") is True
    # Verifier and sandbox must NOT have been called
    assert verifier_called is False
    assert "verifier" not in final_state.nodes
    assert "reviewer" not in final_state.nodes

    # Now approve patch and resume from verifier
    state.shared_data["patch_approved"] = True
    task_graph.resume()
    resumed_state = await task_graph.run(resume_from="verifier")

    assert verifier_called is True
    assert resumed_state.verification_passed is True
    assert task_graph.run_status == RunStatus.MERGED
    assert "verifier" in resumed_state.nodes
    assert "reviewer" in resumed_state.nodes


@pytest.mark.asyncio
async def test_low_risk_patch_auto_proceeds_without_approval(tmp_path, monkeypatch):
    run_id = "test_run_low_risk"
    state = OrchestratorState(run_id=run_id, repo_path=str(tmp_path), issue_description="Fix typo in docs")

    # Low-risk: small diff, non-sensitive file
    async def fake_patcher(self, state):
        state.patch_diff = "--- a/docs/readme.txt\n+++ b/docs/readme.txt\n@@ -1 +1 @@\n-old\n+new\n"
        state.snapshot_id = "snap_docs"
        state.shared_data["commit_gateway"] = {"allowed": True}
        return {"patch_diff": state.patch_diff, "snapshot_id": state.snapshot_id}

    verifier_called = False

    async def fake_verifier(self, state):
        nonlocal verifier_called
        verifier_called = True
        state.verification_passed = True
        state.shared_data["verification_decision"] = "auto_merge"
        state.shared_data["confidence_score"] = 0.99
        return {"overall_success": True}

    async def fake_reviewer(self, state):
        state.shared_data["reviewer_report"] = {"approved": True}
        return {"report": "approved"}

    monkeypatch.setattr(PatcherAgent, "execute", fake_patcher)
    monkeypatch.setattr(VerifierAgent, "execute", fake_verifier)
    monkeypatch.setattr(ReviewerAgent, "execute", fake_reviewer)

    task_graph = TaskGraph(
        state,
        ModelRouter(mock_mode=True),
        TelemetryTracer(run_id=run_id, log_dir=str(tmp_path / "traces")),
        CostTracker(run_id=run_id),
    )

    final_state = await task_graph.run()

    # Low-risk patch should not pause
    assert task_graph.run_status == RunStatus.MERGED
    assert verifier_called is True
    assert "verifier" in final_state.nodes
    assert "reviewer" in final_state.nodes


@pytest.mark.asyncio
async def test_org_policy_requires_approval_even_for_low_risk(tmp_path, monkeypatch):
    run_id = "test_run_policy_approval"
    state = OrchestratorState(run_id=run_id, repo_path=str(tmp_path), issue_description="Minor fix")
    state.shared_data["require_patch_approval"] = True

    async def fake_patcher(self, state):
        state.patch_diff = "--- a/src/utils.py\n+++ b/src/utils.py\n@@ -1 +1 @@\n-1\n+2\n"
        state.snapshot_id = "snap_utils"
        state.shared_data["commit_gateway"] = {"allowed": True}
        return {"patch_diff": state.patch_diff, "snapshot_id": state.snapshot_id}

    verifier_called = False

    async def fake_verifier(self, state):
        nonlocal verifier_called
        verifier_called = True
        state.verification_passed = True
        return {"overall_success": True}

    monkeypatch.setattr(PatcherAgent, "execute", fake_patcher)
    monkeypatch.setattr(VerifierAgent, "execute", fake_verifier)

    task_graph = TaskGraph(
        state,
        ModelRouter(mock_mode=True),
        TelemetryTracer(run_id=run_id, log_dir=str(tmp_path / "traces")),
        CostTracker(run_id=run_id),
    )

    final_state = await task_graph.run()

    assert task_graph.run_status == RunStatus.PENDING_APPROVAL
    assert final_state.shared_data.get("approval_required") is True
    assert verifier_called is False
