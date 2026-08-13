import hashlib

import pytest

from loom.business.models import (
    AgentStepRecord,
    PatchRecord,
    RunRecord,
    VerificationResultRecord,
)
from loom.db.records_store import (
    RunRecordStore,
    get_run_record_store,
    reset_run_record_store,
    verification_stage_records,
)


@pytest.fixture
def store(tmp_path):
    reset_run_record_store()
    return get_run_record_store(str(tmp_path / "records.db"))


def test_run_record_upsert_and_query(store):
    run = RunRecord(run_id="run_1", org_id="org_a", issue_text="fix bug", status="queued")
    store.record_run(run)

    loaded = store.get_run("run_1")
    assert loaded is not None
    assert loaded.status == "queued"

    run.status = "merged"
    run.verification_passed = True
    run.confidence_score = 0.97
    run.merge_decision = {"auto_merge": True, "actor": "agent"}
    store.record_run(run)

    updated = store.get_run("run_1")
    assert updated.status == "merged"
    assert updated.verification_passed is True
    assert updated.confidence_score == 0.97
    assert updated.merge_decision["actor"] == "agent"

    assert len(store.list_runs(org_id="org_a")) == 1
    assert len(store.list_runs(org_id="other")) == 0


def test_step_record_upsert_keeps_one_row_per_node(store):
    step = AgentStepRecord(run_id="run_2", agent_name="patcher", model_id="mock", tokens_in=100, tokens_out=50)
    store.record_step(step)

    step.tokens_in = 300
    step.retry_count = 2
    step.status = "completed"
    store.record_step(step)

    steps = store.get_steps("run_2")
    assert len(steps) == 1
    assert steps[0].retry_count == 2
    assert steps[0].tokens_in == 300


def test_patch_and_verification_records(store):
    diff = "--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-old\n+new\n"
    store.record_patch(
        PatchRecord(
            run_id="run_3",
            diff_hash=hashlib.sha256(diff.encode()).hexdigest(),
            diff_ref="snap_1",
            files_touched=1,
            risk_flags=["high_risk"],
            apply_status="applied",
        )
    )
    patches = store.get_patches("run_3")
    assert len(patches) == 1
    assert patches[0].risk_flags == ["high_risk"]
    assert patches[0].apply_status == "applied"
    assert len(store.get_patches("run_zz")) == 0

    store.record_verification(VerificationResultRecord(run_id="run_3", stage="sast", status="passed"))
    verifications = store.get_verifications("run_3")
    assert len(verifications) == 1
    assert verifications[0].stage == "sast"


def test_verification_stage_records_mapping():
    output = {
        "build_passed": True,
        "tests_passed": False,
        "repro_flip_confirmed": False,
        "sast_severity": "clean",
        "sast_findings": [],
        "decision": "reject_regression",
    }
    records = verification_stage_records("run_4", output)
    assert [r.stage for r in records] == ["build", "test", "repro", "sast", "lint"]
    assert records[0].status == "passed"
    assert records[1].status == "failed"
    assert records[3].status == "passed"

    blocked = verification_stage_records("run_4", {**output, "sast_severity": "critical"})
    assert blocked[3].status == "failed"
    assert blocked[3].details["severity"] == "critical"

    assert verification_stage_records("run_4", None)[0].status == "failed"


@pytest.mark.asyncio
async def test_task_graph_writes_records(tmp_path):
    from loom.adapters.router import ModelRouter
    from loom.orchestrator.state import OrchestratorState
    from loom.orchestrator.task_graph import TaskGraph
    from loom.telemetry.cost_tracker import CostTracker
    from loom.telemetry.tracer import TelemetryTracer

    reset_run_record_store()
    records_db = str(tmp_path / "graph-records.db")
    records_store = RunRecordStore(db_path=records_db)

    run_id = "run_graph_records"
    state = OrchestratorState(run_id=run_id, repo_path=str(tmp_path), issue_description="fix null pointer")
    state.shared_data["org_id"] = "org_graph"
    task_graph = TaskGraph(
        state,
        ModelRouter(mock_mode=True),
        TelemetryTracer(run_id=run_id, log_dir=str(tmp_path / "traces")),
        CostTracker(run_id=run_id),
        records_store=records_store,
    )
    await task_graph.run()

    run = records_store.get_run(run_id)
    assert run is not None
    assert run.org_id == "org_graph"
    assert run.status == "evidence_review"
    assert run.model_sequence and run.model_sequence[0] == "mock"
    assert run.cost_usd > 0

    steps = records_store.get_steps(run_id)
    assert len(steps) >= 5
    names = {s.agent_name for s in steps}
    assert {"onboarding", "reproduction", "planner", "patcher", "verifier", "reviewer"} <= names
    completed = [s for s in steps if s.agent_name == "planner"][0]
    assert completed.status == "completed"
    assert completed.tokens_in > 0

    patches = records_store.get_patches(run_id)
    assert len(patches) == 1
    assert patches[0].apply_status in ("applied", "invalid_patch", "conflict", "error")

    verifications = records_store.get_verifications(run_id)
    assert {v.stage for v in verifications} == {"build", "test", "repro", "sast", "lint"}
