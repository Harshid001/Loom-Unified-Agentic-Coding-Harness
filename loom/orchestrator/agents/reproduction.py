import shlex
from typing import Any, Dict, Optional, cast

from loom.adapters.base import ModelRequest
from loom.orchestrator.agents.base_agent import BaseAgent
from loom.orchestrator.state import OrchestratorState
from loom.sandbox.factory import sandbox_for_state


class ReproductionAgent(BaseAgent):
    """Generates an issue reproduction test and executes it on base to record reproduction evidence."""

    async def execute(self, state: OrchestratorState) -> Dict[str, Any]:
        prompt = (
            f"Generate a reproduction test script for issue: {state.issue_description}\n"
            f"Repository info: {state.shared_data.get('onboarding_summary')}"
        )
        req = ModelRequest(model=self.model_name, messages=[{"role": "user", "content": prompt}])
        res = await self.adapter.generate(req)

        repro_script = res.content or "def test_reproduction(): pass"
        state.reproduction_test = repro_script
        usage_data = (
            res.usage.model_dump()
            if hasattr(res.usage, "model_dump")
            else {"prompt_tokens": 150, "completion_tokens": 50, "estimated_cost_usd": 0.0005}
        )

        mock_mode = bool(state.shared_data.get("mock_mode"))
        pre_cmds = []

        if mock_mode:
            pre_cmds = ["python -c \"import sys; sys.exit(1)\""]
            status = "reproduced"
            repro_output = "Mock reproduction failure observed on base"
        else:
            import ast
            from pathlib import Path

            is_code_block = "\n" in repro_script or "def " in repro_script or "import " in repro_script
            repro_file_created = False
            repro_file_path: Optional[Path] = None

            if repro_script.startswith("pytest") or repro_script.startswith("python ") or repro_script.startswith("npm"):
                cmd = repro_script
            elif is_code_block or repro_script.endswith(".py"):
                # Validate Python syntax before running
                try:
                    ast.parse(repro_script)
                    syntax_valid = True
                except SyntaxError as e:
                    syntax_valid = False
                    repro_output = f"Reproduction script contains Python syntax error: {e}"
                    status = "reproduction_failed"

                if syntax_valid:
                    # Write to a safe repro test file inside the repo to avoid shell quoting issues
                    try:
                        repro_file_path = Path(state.repo_path) / "test_loom_repro_case.py"
                        repro_file_path.write_text(repro_script, encoding="utf-8")
                        repro_file_created = True
                        cmd = "pytest test_loom_repro_case.py"
                    except Exception:
                        cmd = f"python -c {shlex.quote(repro_script)}"
                else:
                    cmd = ""
            else:
                cmd = "pytest"

            if cmd:
                pre_cmds = [cmd]
                try:
                    sandbox = sandbox_for_state(state)
                    run_res = await sandbox.arun_command(cmd)
                    repro_output = run_res.stdout + "\n" + run_res.stderr
                    # In verification-first: the bug must be demonstrated by test failing on base (non-zero exit)
                    # Check that the failure was an actual test failure / assertion error, not a broken command / syntax error
                    if run_res.exit_code != 0 and "SyntaxError" not in repro_output and run_res.exit_code != 127:
                        status = "reproduced"
                    else:
                        status = "reproduction_failed"
                except Exception as exc:
                    repro_output = str(exc)
                    status = "reproduction_failed"
                finally:
                    if repro_file_created and repro_file_path and repro_file_path.exists():
                        try:
                            repro_file_path.unlink()
                        except OSError:
                            pass
            else:
                pre_cmds = []


        state.shared_data["pre_patch_test_commands"] = pre_cmds
        evidence: Dict[str, Any] = {
            "test_script": repro_script,
            "status": status,
            "pre_patch_test_commands": pre_cmds,
            "reproduction_output": repro_output,
            "model_used": res.model,
            "cost_usd": res.usage.estimated_cost_usd,
            "_usage": usage_data,
        }
        state.shared_data["reproduction_evidence"] = evidence
        return cast(Dict[str, Any], state.shared_data["reproduction_evidence"])

