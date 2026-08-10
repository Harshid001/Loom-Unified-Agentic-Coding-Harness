from typing import Any, Dict

from loom.orchestrator.agents.base_agent import BaseAgent
from loom.orchestrator.state import OrchestratorState
from loom.sandbox.local_process import LocalProcessSandbox
from loom.verification.runner import VerificationRunner


class VerifierAgent(BaseAgent):
    """Runs build and test verification suites to validate patch correctness."""

    async def execute(self, state: OrchestratorState) -> Dict[str, Any]:
        sandbox = LocalProcessSandbox(state.repo_path)
        runner = VerificationRunner(sandbox)

        test_frameworks = state.shared_data.get("repo_map", {}).get("test_frameworks", ["pytest"])
        test_cmds = []
        if state.shared_data.get("mock_mode"):
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

        res = runner.run_verification(test_commands=test_cmds)
        state.verification_passed = res.overall_success

        verifier_output = {
            "overall_success": res.overall_success,
            "build_passed": res.build_passed,
            "tests_passed": res.tests_passed,
            "failure_reason": res.failure_reason,
            "test_count": len(res.test_results)
        }
        state.shared_data["verification_output"] = verifier_output
        return verifier_output
