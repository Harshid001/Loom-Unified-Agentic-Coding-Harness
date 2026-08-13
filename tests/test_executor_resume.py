from loom.orchestrator.state import NodeStatus, OrchestratorState
from loom.runtime.executor import _resume_node


def test_resume_starts_at_first_incomplete_node():
    state = OrchestratorState(run_id="run_1", repo_path="/workspace/repo", issue_description="test")
    state.nodes["onboarding"] = NodeStatus(node_name="onboarding", status="completed")
    state.nodes["reproduction"] = NodeStatus(node_name="reproduction", status="completed")
    state.nodes["planner"] = NodeStatus(node_name="planner", status="failed")

    sequence = [("onboarding", object), ("reproduction", object), ("planner", object), ("patcher", object)]
    assert _resume_node(state, sequence) == "planner"


def test_resume_starts_first_node_when_checkpoint_has_no_nodes(tmp_path):
    state = OrchestratorState(run_id="run_2", repo_path="/workspace/repo", issue_description="test")
    sequence = [("onboarding", object), ("reproduction", object)]
    assert _resume_node(state, sequence) == "onboarding"
