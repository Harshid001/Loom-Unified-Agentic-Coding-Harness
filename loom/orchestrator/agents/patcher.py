import logging
import shlex
import subprocess
from pathlib import Path
from typing import Any, Dict, List

from loom.adapters.base import ModelRequest
from loom.adapters.router import TaskType
from loom.business.audit_log import get_audit_logger
from loom.business.models import AuditAction
from loom.business.path_policy import evaluate_commit_gateway
from loom.context.sanitizer import PromptSanitizer
from loom.orchestrator.agents.base_agent import BaseAgent
from loom.orchestrator.state import OrchestratorState
from loom.sandbox.factory import sandbox_for_state

logger = logging.getLogger("loom.orchestrator.agents.patcher")


class PatcherAgent(BaseAgent):
    """Proposes code modifications, applies patches, and records diffs."""

    async def execute(self, state: OrchestratorState) -> Dict[str, Any]:
        sandbox = sandbox_for_state(state)
        snapshot_id = sandbox.create_snapshot("pre_patch")
        state.snapshot_id = snapshot_id

        sanitizer = PromptSanitizer()
        plan_record = state.shared_data.get("plan")
        plan_text = plan_record.get("plan") if isinstance(plan_record, dict) else ""
        sanitized_issue = sanitizer.wrap_untrusted_content(state.issue_description, "issue_description")
        sanitized_repro = sanitizer.wrap_untrusted_content(state.reproduction_test or "", "reproduction_test")
        prompt = (
            f"Generate patch solution for issue:\n{sanitized_issue}\n"
            f"Reproduction test:\n{sanitized_repro}\n"
            f"Fix plan: {plan_text}\n"
            f"Repository context: {state.shared_data.get('onboarding_summary')}"
        )
        req = ModelRequest(model=self.model_name, messages=[{"role": "user", "content": prompt}])
        res = await self.adapter.generate(req)

        raw_content = res.content or ""
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

        state.patch_diff = patch_diff

        org = state.shared_data.get("_org")
        gateway = evaluate_commit_gateway(patch_diff, org=org)
        state.shared_data["commit_gateway"] = {
            "allowed": gateway.allowed,
            "status": gateway.status,
            "blocked_paths": gateway.blocked_paths,
            "reason": gateway.reason,
        }
        if not gateway.allowed:
            logger.warning(
                "Run %s blocked by commit gateway (security_hold): %s",
                state.run_id,
                gateway.reason,
            )
            state.shared_data["security_hold_reason"] = gateway.reason
            self._record_gateway_denial(state, gateway.reason)
            patch_result = {
                "patch_diff": patch_diff,
                "snapshot_id": snapshot_id,
                "apply_status": "blocked_sensitive_path",
                "conflict_detected": False,
                "summary": f"Patch blocked by commit gateway: {gateway.reason}",
                "blocked_paths": gateway.blocked_paths,
            }
            state.shared_data["patch_summary"] = patch_result
            return patch_result

        router = state.shared_data.get("__router")
        if router is not None and patch_diff:
            touched: list[str] = list(gateway.blocked_paths) if not gateway.allowed else []
            if not touched:
                touched = [
                    line[4:].replace("\t", " ").split(" ")[0]
                    for line in patch_diff.splitlines()
                    if line.startswith("+++ ") and "/dev/null" not in line
                ]
            prior_confidence = float(state.shared_data.get("confidence_score", 0.5))
            consensus_mode = "auto"
            if router.needs_consensus(patch_diff, touched, prior_confidence, consensus_mode):
                logger.info(
                    "Run %s: patch classified as high-risk, running consensus verification (2-of-3)",
                    state.run_id,
                )
                fallback_models = router.build_fallback_cascade(TaskType.PATCHING)
                secondary_models = [m for m in fallback_models if m != self.model_name][:2]
                secondary_patches = [patch_diff]
                for sec_model in secondary_models:
                    try:
                        sec_adapter = router.get_adapter("patcher")
                        sec_req = ModelRequest(
                            model=sec_model,
                            messages=[{"role": "user", "content": prompt}],
                        )
                        sec_res = await sec_adapter.generate(sec_req)
                        sec_content = sec_res.content or ""
                        if "--- " in sec_content and "+++ " in sec_content:
                            sec_diff: list[str] = []
                            in_diff = False
                            for line in sec_content.splitlines():
                                if line.startswith("--- "):
                                    in_diff = True
                                if in_diff:
                                    if line.startswith("```") and len(sec_diff) > 1:
                                        break
                                    sec_diff.append(line)
                            if sec_diff:
                                secondary_patches.append("\n".join(sec_diff))
                    except Exception as consensus_err:
                        logger.warning(
                            "Consensus secondary model %s failed for run %s: %s",
                            sec_model,
                            state.run_id,
                            consensus_err,
                        )
                consensus_result = await router.verify_consensus(
                    secondary_patches, required_agreement=2
                )
                state.shared_data["consensus_result"] = {
                    "required": consensus_result.required_patches,
                    "agreed_count": len(consensus_result.agreed_model_ids),
                    "passed": consensus_result.passed,
                    "agreed_model_ids": consensus_result.agreed_model_ids,
                }
                if not consensus_result.passed:
                    logger.warning(
                        "Run %s: consensus verification failed (%d of %d agreed)",
                        state.run_id,
                        len(consensus_result.agreed_model_ids),
                        consensus_result.required_patches,
                    )
                    state.shared_data["security_hold_reason"] = (
                        f"Consensus verification failed: "
                        f"{len(consensus_result.agreed_model_ids)} of "
                        f"{consensus_result.required_patches} models agreed on patch intent"
                    )
                    patch_result = {
                        "patch_diff": patch_diff,
                        "snapshot_id": snapshot_id,
                        "apply_status": "blocked_consensus_failed",
                        "conflict_detected": False,
                        "summary": f"Patch blocked by consensus verification: {state.shared_data['security_hold_reason']}",
                        "consensus_failed": True,
                    }
                    state.shared_data["patch_summary"] = patch_result
                    state.shared_data["commit_gateway"] = {
                        "allowed": False,
                        "status": "security_hold",
                        "blocked_paths": gateway.blocked_paths,
                        "reason": state.shared_data["security_hold_reason"],
                    }
                    return patch_result

        apply_status = "invalid_patch"
        conflict_detected = False
        if patch_diff:
            patch_file = Path(state.repo_path) / ".loom_patch.diff"
            try:
                patch_file.write_text(patch_diff, encoding="utf-8")
                apply_res = await sandbox.arun_command(f"git apply {shlex.quote(str(patch_file))}")
                if apply_res.exit_code == 0:
                    apply_status = "applied"
                else:
                    fallback_res = await sandbox.arun_command(f"patch -p1 -i {shlex.quote(str(patch_file))}")
                    if fallback_res.exit_code == 0:
                        apply_status = "applied_via_fallback"
                    else:
                        apply_status = "conflict"
                        conflict_detected = True
                        logger.warning(
                            "Patch conflict for run %s: git apply (exit %s) and patch fallback (exit %s) both failed",
                            state.run_id,
                            apply_res.exit_code,
                            fallback_res.exit_code,
                        )
            except (subprocess.CalledProcessError, OSError, IOError) as err:
                logger.warning("Error applying patch file %s: %s", patch_file, err)
                apply_status = "error"
            finally:
                if patch_file.exists():
                    try:
                        patch_file.unlink()
                    except OSError as unlink_err:
                        logger.debug("Failed to unlink patch file %s: %s", patch_file, unlink_err)

        state.shared_data["conflict_detected"] = conflict_detected

        usage_data = (
            res.usage.model_dump()
            if hasattr(res.usage, "model_dump")
            else {"prompt_tokens": 150, "completion_tokens": 50, "estimated_cost_usd": 0.0005}
        )

        patch_result = {
            "patch_diff": patch_diff,
            "snapshot_id": snapshot_id,
            "apply_status": apply_status,
            "conflict_detected": conflict_detected,
            "summary": f"Applied patch to resolve target issue: {state.issue_description}",
            "_usage": usage_data,
        }
        state.shared_data["patch_summary"] = patch_result
        return patch_result

    def _record_gateway_denial(self, state: OrchestratorState, reason: str) -> None:
        try:
            get_audit_logger().record(
                org_id=str(state.shared_data.get("org_id", "default")),
                action=AuditAction.PATCH_SENSITIVE_BLOCKED,
                actor_id=f"agent:{self.name}",
                target=state.run_id,
                metadata={"reason": reason, "patch_hash": state.snapshot_id or ""},
            )
        except Exception as err:
            logger.warning("Failed to record commit-gateway denial for run %s: %s", state.run_id, err)
