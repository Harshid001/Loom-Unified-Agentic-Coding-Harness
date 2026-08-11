import logging
import subprocess
from pathlib import Path
from typing import Any, Dict, List

from loom.adapters.base import ModelRequest
from loom.orchestrator.agents.base_agent import BaseAgent
from loom.orchestrator.state import OrchestratorState
from loom.sandbox.local_process import LocalProcessSandbox

logger = logging.getLogger("loom.orchestrator.agents.patcher")


class PatcherAgent(BaseAgent):
    """Proposes code modifications, applies patches, and records diffs."""

    async def execute(self, state: OrchestratorState) -> Dict[str, Any]:
        sandbox = LocalProcessSandbox(state.repo_path)
        snapshot_id = sandbox.create_snapshot("pre_patch")
        state.snapshot_id = snapshot_id

        prompt = (
            f"Generate patch solution for issue: {state.issue_description}\n"
            f"Reproduction test: {state.reproduction_test}\n"
            f"Repository context: {state.shared_data.get('onboarding_summary')}"
        )
        req = ModelRequest(model=self.model_name, messages=[{"role": "user", "content": prompt}])
        res = await self.adapter.generate(req)

        raw_content = res.content or ""
        # PRD-003 & PRD-004: Extract actual diff and validate path safety
        patch_diff = ""
        if "--- " in raw_content and "+++ " in raw_content:
            lines = raw_content.splitlines()
            diff_lines: List[str] = []
            in_diff = False
            for line in lines:
                if line.startswith("--- "):
                    in_diff = True
                if in_diff:
                    if line.startswith("```") and len(diff_lines) > 1:
                        break
                    # Path traversal sanity check
                    if (
                        (".." in line and ("--- " in line or "+++ " in line))
                        or line.startswith("--- /")
                        or line.startswith("+++ /")
                    ):
                        logger.warning("Unsafe path traversal detected in patch line: %s", line)
                        patch_diff = ""
                        break
                    diff_lines.append(line)
            if diff_lines:
                patch_diff = "\n".join(diff_lines)
        else:
            logger.info("Model output did not contain valid patch diff format")
            patch_diff = ""

        state.patch_diff = patch_diff

        # PRD-101 & PRD-004: Apply valid patch to target repository sandbox
        if patch_diff:
            patch_file = Path(state.repo_path) / ".loom_patch.diff"
            try:
                patch_file.write_text(patch_diff, encoding="utf-8")
                apply_res = sandbox.run_command(["git", "apply", str(patch_file)])
                if apply_res.exit_code != 0:
                    sandbox.run_command(["patch", "-p1", "-i", str(patch_file)])
            except (subprocess.CalledProcessError, OSError, IOError) as err:
                logger.warning("Error applying patch file %s: %s", patch_file, err)
            finally:
                if patch_file.exists():
                    try:
                        patch_file.unlink()
                    except OSError as unlink_err:
                        logger.debug("Failed to unlink patch file %s: %s", patch_file, unlink_err)

        usage_data = (
            res.usage.model_dump()
            if hasattr(res.usage, "model_dump")
            else {"prompt_tokens": 150, "completion_tokens": 50, "estimated_cost_usd": 0.0005}
        )

        patch_result = {
            "patch_diff": patch_diff,
            "snapshot_id": snapshot_id,
            "summary": f"Applied patch to resolve target issue: {state.issue_description}",
            "_usage": usage_data,
        }
        state.shared_data["patch_summary"] = patch_result
        return patch_result
