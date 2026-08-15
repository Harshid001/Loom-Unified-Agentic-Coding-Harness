from typing import Any, Dict

from loom.orchestrator.agents.base_agent import BaseAgent
from loom.orchestrator.state import OrchestratorState
from loom.sandbox.command_policy import CommandPolicyError, validate_verification_commands
from loom.sandbox.factory import sandbox_for_state
from loom.verification.runner import VerificationRunner


class VerifierAgent(BaseAgent):
    """Runs the verification-first pipeline inside the selected sandbox tier."""

    async def execute(self, state: OrchestratorState) -> Dict[str, Any]:
        sandbox = sandbox_for_state(state)
        threshold = float(state.shared_data.get("auto_merge_threshold", 0.95))
        runner = VerificationRunner(sandbox, auto_merge_threshold=threshold)

        test_frameworks = state.shared_data.get("repo_map", {}).get("test_frameworks", ["pytest"])
        test_cmds = []
        mock_mode = bool(state.shared_data.get("mock_mode"))
        if mock_mode:
            test_cmds.append("python -c \"print('Mock verification test passed')\"")
        elif state.reproduction_test and (
            state.reproduction_test.startswith("pytest")
            or state.reproduction_test.startswith("python")
            or state.reproduction_test.startswith("npm")
        ):
            test_cmds.append(state.reproduction_test)

        if not test_cmds:
            for tf in test_frameworks:
                if "pytest" in tf:
                    test_cmds.append("pytest")
                elif "npm" in tf or "jest" in tf:
                    test_cmds.append("npm test")

        if not test_cmds:
            test_cmds = ["pytest"]

        if not mock_mode:
            try:
                validate_verification_commands(test_cmds)
            except CommandPolicyError as exc:
                state.verification_passed = False
                state.shared_data["confidence_score"] = 0.0
                state.shared_data["verification_decision"] = "security_hold"
                state.shared_data["verification_output"] = {
                    "overall_success": False,
                    "build_passed": False,
                    "tests_passed": False,
                    "failure_reason": f"Verification command blocked by sandbox policy: {exc}",
                    "test_count": 0,
                    "sast_severity": "critical",
                    "sast_findings": [],
                    "repro_flip_confirmed": False,
                    "confidence_score": 0.0,
                    "decision": "security_hold",
                }
                return state.shared_data["verification_output"]

        pre_patch_cmds = state.shared_data.get("pre_patch_test_commands")
        if not pre_patch_cmds:
            if mock_mode:
                pre_patch_cmds = ["python -c \"import sys; sys.exit(1)\""]
            elif state.reproduction_test and (
                state.reproduction_test.startswith("pytest")
                or state.reproduction_test.startswith("python")
                or state.reproduction_test.startswith("npm")
            ):
                pre_patch_cmds = [state.reproduction_test]
            else:
                pre_patch_cmds = test_cmds

        res, _repro = await runner.full_verification_pipeline_async(
            test_commands=test_cmds,
            repro_script=state.reproduction_test or "",
            pre_patch_test_commands=pre_patch_cmds,
            post_patch_test_commands=test_cmds,
            diff_text=state.patch_diff or "",
        )

        state.verification_passed = res.overall_success

        state.shared_data["confidence_score"] = res.confidence_score
        state.shared_data["verification_decision"] = res.decision.value
        state.shared_data["sast_findings"] = [f.model_dump() for f in res.sast_findings]
        state.shared_data["sast_severity"] = res.sast_severity.value

        verifier_output = {
            "overall_success": res.overall_success,
            "build_passed": res.build_passed,
            "tests_passed": res.tests_passed,
            "failure_reason": res.failure_reason,
            "test_count": len(res.test_results),
            "sast_severity": res.sast_severity.value,
            "sast_findings": [f.model_dump() for f in res.sast_findings],
            "repro_flip_confirmed": res.repro_flip_confirmed,
            "confidence_score": res.confidence_score,
            "decision": res.decision.value,
        }
        state.shared_data["verification_output"] = verifier_output
        return verifier_output
