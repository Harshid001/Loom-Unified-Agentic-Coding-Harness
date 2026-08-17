import asyncio
from dataclasses import dataclass, field
from typing import Any

from loom.business.audit_log import AuditLogger
from loom.business.models import AuditAction, Organization
from loom.business.path_policy import (
    PatchApprovalPolicy,
    evaluate_commit_gateway,
    extract_touched_paths,
    matches_sensitive_glob,
    sensitive_paths_in_patch,
)
from loom.orchestrator.agents.patcher import PatcherAgent
from loom.orchestrator.state import OrchestratorState


@dataclass
class FakeUsage:
    def model_dump(self) -> dict:
        return {"prompt_tokens": 1, "completion_tokens": 1, "estimated_cost_usd": 0.0}


@dataclass
class FakeResponse:
    content: str
    usage: FakeUsage = field(default_factory=FakeUsage)


class StubAdapter:
    def __init__(self, content: str):
        self._content = content

    async def generate(self, request: Any) -> FakeResponse:
        return FakeResponse(content=self._content)


def _diff(*paths: str) -> str:
    lines = ["--- a/app.py", "+++ b/app.py", "@@ -1 +1 @@", "-old", "+new"]
    for p in paths:
        lines += [f"--- a/{p}", f"+++ b/{p}", "@@ -1 +1 @@", f"-old {p}", f"+new {p}"]
    return "\n".join(lines)


def _org(**kwargs: Any) -> Organization:
    return Organization(id="org_gw", name="GW Org", **kwargs)


def _state(tmp_path: Any, issue: str = "sensitive path test") -> OrchestratorState:
    state = OrchestratorState(run_id="run_gw", repo_path=str(tmp_path), issue_description=issue)
    state.shared_data["org_id"] = "org_gw"
    return state


class TestExtraction:
    def test_extracts_touched_paths(self):
        diff = _diff("src/app.py")
        assert extract_touched_paths(diff) == ["app.py", "src/app.py"]

    def test_ignores_dev_null_and_absolutes(self):
        diff = "--- /dev/null\n+++ /dev/null\n--- a/x.py\n+++ /etc/passwd\n"
        assert extract_touched_paths(diff) == []

    def test_deduplicates_paths(self):
        assert extract_touched_paths("+++ b/app.py\n+++ b/app.py\n") == ["app.py"]


class TestGlobMatching:
    def test_default_globs_hit_common_sensitive_dirs(self):
        assert matches_sensitive_glob("loom/business/billing/core.py")
        assert matches_sensitive_glob("loom/api/auth/login.py")
        assert matches_sensitive_glob("db/migrations/0001.py")
        assert matches_sensitive_glob(".env")

    def test_plain_source_is_allowed(self):
        assert not matches_sensitive_glob("loom/business/models.py")
        assert not matches_sensitive_glob("src/app.js")

    def test_org_globs_override_defaults(self):
        org = _org(sensitive_path_globs=["**/secret/**"])
        assert sensitive_paths_in_patch(_diff("secret/key.py"), org) == ["secret/key.py"]
        assert sensitive_paths_in_patch(_diff("billing/core.py"), org) == []


class TestCommitGateway:
    def test_clean_patch_allowed(self):
        decision = evaluate_commit_gateway(_diff("app.py"))
        assert decision.allowed is True
        assert decision.status == "allowed"
        assert decision.blocked_paths == []

    def test_sensitive_patch_blocked_by_default(self):
        org = _org()
        decision = evaluate_commit_gateway(_diff("loom/business/billing/invoice.py"), org)
        assert decision.allowed is False
        assert decision.status == "security_hold"
        assert decision.blocked_paths == ["loom/business/billing/invoice.py"]
        assert "billing" in decision.reason

    def test_audit_only_policy_allows_but_flags(self):
        decision = evaluate_commit_gateway(_diff("loom/api/auth/routes.py"), allow_with_audit=True)
        assert decision.allowed is True
        assert decision.status == "audit_only"
        assert decision.blocked_paths == ["loom/api/auth/routes.py"]

    def test_default_globs_used_without_org(self):
        decision = evaluate_commit_gateway(_diff(".env"))
        assert decision.allowed is False
        assert decision.blocked_paths == [".env"]


class TestPatcherIntegration:
    def test_sensitive_patch_never_reaches_git_apply(self, tmp_path, monkeypatch):
        sensitive_diff = _diff("loom/business/billing/invoice.py")
        agent = PatcherAgent(name="patcher", adapter=StubAdapter(sensitive_diff))
        state = _state(tmp_path)
        state.shared_data["_org"] = _org()

        result = asyncio.run(agent.execute(state))

        assert result["apply_status"] == "blocked_sensitive_path"
        assert result["blocked_paths"] == ["loom/business/billing/invoice.py"]
        assert state.shared_data["security_hold_reason"] is not None
        assert state.shared_data["commit_gateway"]["status"] == "security_hold"
        assert not (tmp_path / ".loom_patch.diff").exists()

    def test_clean_patch_proceeds_to_apply(self, tmp_path):
        agent = PatcherAgent(name="patcher", adapter=StubAdapter(_diff("app.py")))
        state = _state(tmp_path)

        result = asyncio.run(agent.execute(state))

        assert result["apply_status"] in ("applied", "invalid_patch", "conflict", "error")
        assert state.shared_data["commit_gateway"]["allowed"] is True
        assert state.shared_data["commit_gateway"]["blocked_paths"] == []

    def test_denial_writes_audit_entry(self, tmp_path, monkeypatch):
        audit = AuditLogger(storage_dir=str(tmp_path / "audit"))
        monkeypatch.setattr("loom.orchestrator.agents.patcher.get_audit_logger", lambda: audit)

        agent = PatcherAgent(name="patcher", adapter=StubAdapter(_diff("loom/business/billing/invoice.py")))
        state = _state(tmp_path)
        state.shared_data["_org"] = _org()

        asyncio.run(agent.execute(state))

        entries = audit.get_entries(org_id="org_gw", action=AuditAction.PATCH_SENSITIVE_BLOCKED)
        assert len(entries) == 1
        assert entries[0].target == "run_gw"


class TestPatchApprovalPolicy:
    def test_default_policy_classification(self):
        policy = PatchApprovalPolicy()
        assert not policy.classify_risk(diff_size=50, touched_files=["src/utils.py"], prior_confidence=0.9)
        assert policy.classify_risk(diff_size=200, touched_files=["src/utils.py"], prior_confidence=0.9)
        assert policy.classify_risk(diff_size=50, touched_files=["src/auth/login.ts"], prior_confidence=0.9)
        assert policy.classify_risk(diff_size=50, touched_files=["src/utils.py"], prior_confidence=0.4)

    def test_enterprise_default_policy_strictness(self):
        policy = PatchApprovalPolicy.enterprise_default()
        assert policy.require_human_signoff is True
        assert policy.max_autonomous_diff_lines == 75
        assert policy.min_autonomous_confidence == 0.85
        # Diff of 80 lines is high risk under enterprise policy
        assert policy.classify_risk(diff_size=80, touched_files=["src/utils.py"], prior_confidence=0.95)
        # Confidence of 0.80 is high risk under enterprise policy (min is 0.85)
        assert policy.classify_risk(diff_size=20, touched_files=["src/utils.py"], prior_confidence=0.80)
