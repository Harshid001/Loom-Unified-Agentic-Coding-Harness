import asyncio
import hashlib
import logging
import random
import time
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple, Type

from loom.adapters.router import ModelRouter
from loom.api.webhooks import WebhookEngine, WebhookEventType
from loom.business.models import (
    AgentStepRecord,
    PatchRecord,
    RunRecord,
    UsageEvent,
)
from loom.business.usage_ledger import get_usage_ledger
from loom.db.records_store import RunRecordStore, verification_stage_records
from loom.orchestrator.agents import (
    OnboardingAgent,
    PatcherAgent,
    PlannerAgent,
    ReproductionAgent,
    ReviewerAgent,
    VerifierAgent,
)
from loom.orchestrator.agents.base_agent import BaseAgent
from loom.orchestrator.state import NodeStatus, OrchestratorState
from loom.telemetry.cost_tracker import CostTracker
from loom.telemetry.tracer import TelemetryTracer
from loom.verification.bundle import EvidenceBundle, EvidenceBundler

logger = logging.getLogger("loom.orchestrator")


class RunStatus(str, Enum):
    QUEUED = "queued"
    ONBOARDING = "onboarding"
    REPRODUCING = "reproducing"
    PLANNING = "planning"
    PATCHING = "patching"
    VERIFYING = "verifying"
    EVIDENCE_REVIEW = "evidence_review"
    CONFLICT_RESOLUTION = "conflict_resolution"
    SECURITY_HOLD = "security_hold"
    MERGED = "merged"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


RETRY_BASE_SECONDS = 5.0
RETRY_FACTOR = 2.0
RETRY_MAX_SECONDS = 60.0
RETRY_MAX_ATTEMPTS = 2
RETRY_JITTER = 0.3


def _error_signature(exception: Exception) -> str:
    raw = f"{type(exception).__name__}:{str(exception)[:200]}"
    return hashlib.sha256(raw.encode()).hexdigest()


def compute_merge_decision(
    verification_passed: bool,
    confidence: float,
    threshold: float,
    verification_decision: str = "human_review",
    conflict_detected: bool = False,
) -> Dict[str, Any]:
    """Compute the merge decision (PRD §3.5). Conflicts and security holds never auto-merge.

    `actor` records who is responsible for the final merge decision (PRD §3.7):
    "agent" when auto-merged, "human" when review is required, "none" when the
    run was blocked or failed outright.
    """
    security_hold = verification_decision == "security_hold"
    can_auto_merge = verification_passed and not security_hold and not conflict_detected
    auto_merge = can_auto_merge and confidence >= threshold
    needs_human_review = (verification_passed and not auto_merge) or conflict_detected
    if auto_merge:
        actor = "agent"
    elif needs_human_review:
        actor = "human"
    else:
        actor = "none"
    return {
        "confidence_score": confidence,
        "auto_merge_threshold": threshold,
        "verification_decision": verification_decision,
        "security_hold": security_hold,
        "conflict_detected": conflict_detected,
        "auto_merge": auto_merge,
        "needs_human_review": needs_human_review,
        "actor": actor,
    }


class TaskGraph:
    NODE_SEQUENCE: List[Tuple[str, Type[BaseAgent]]] = [
        ("onboarding", OnboardingAgent),
        ("reproduction", ReproductionAgent),
        ("planner", PlannerAgent),
        ("patcher", PatcherAgent),
        ("verifier", VerifierAgent),
        ("reviewer", ReviewerAgent),
    ]

    STATUS_NODE_MAP: Dict[str, Optional[str]] = {
        "onboarding": RunStatus.ONBOARDING,
        "reproduction": RunStatus.REPRODUCING,
        "planner": RunStatus.PLANNING,
        "patcher": RunStatus.PATCHING,
        "verifier": RunStatus.VERIFYING,
        "reviewer": RunStatus.EVIDENCE_REVIEW,
    }

    def __init__(
        self,
        state: OrchestratorState,
        router: ModelRouter,
        tracer: TelemetryTracer,
        cost_tracker: CostTracker,
        advanced_model_map: Optional[Dict[str, str]] = None,
        on_step_start: Any = None,
        on_step_log: Any = None,
        on_step_complete: Any = None,
        on_step_fail: Any = None,
        max_retries: int = RETRY_MAX_ATTEMPTS,
        retry_base_seconds: float = RETRY_BASE_SECONDS,
        retry_factor: float = RETRY_FACTOR,
        retry_max_seconds: float = RETRY_MAX_SECONDS,
        webhook_engine: Optional[WebhookEngine] = None,
        evidence_bundler: Optional[EvidenceBundler] = None,
        records_store: Optional[RunRecordStore] = None,
    ):
        self.state = state
        self.router = router
        self.tracer = tracer
        self.cost_tracker = cost_tracker
        self.advanced_model_map = advanced_model_map or {}
        self.state.shared_data["mock_mode"] = self.router.mock_mode
        self.state.shared_data["_router"] = self.router
        self.on_step_start_cb = on_step_start
        self.on_step_log_cb = on_step_log
        self.on_step_complete_cb = on_step_complete
        self.on_step_fail_cb = on_step_fail

        self.webhook_engine = webhook_engine
        self.evidence_bundler = evidence_bundler
        self.records_store = records_store
        self._webhook_tasks: List["asyncio.Task[Any]"] = []
        self._model_sequence: List[str] = []
        self._step_records: Dict[str, AgentStepRecord] = {}

        self.is_paused: bool = False
        self.is_cancelled: bool = False
        self.step_mode: bool = False

        self.max_retries = max_retries
        self.retry_base = retry_base_seconds
        self.retry_factor = retry_factor
        self.retry_max = retry_max_seconds

        if not state.shared_data.get("run_status"):
            state.shared_data["run_status"] = RunStatus.QUEUED

    @property
    def run_status(self) -> RunStatus:
        raw = self.state.shared_data.get("run_status", RunStatus.QUEUED)
        if isinstance(raw, RunStatus):
            return raw
        return RunStatus(str(raw))

    @run_status.setter
    def run_status(self, value: RunStatus) -> None:
        self.state.shared_data["run_status"] = value

    def pause(self) -> None:
        self.is_paused = True
        logger.info(f"TaskGraph for run {self.state.run_id} paused")

    def resume(self) -> None:
        self.is_paused = False
        self.step_mode = False
        logger.info(f"TaskGraph for run {self.state.run_id} resumed")

    def step_over(self) -> None:
        self.is_paused = False
        self.step_mode = True
        logger.info(f"TaskGraph for run {self.state.run_id} step-over triggered")

    def cancel(self) -> None:
        self.is_cancelled = True
        self.is_paused = False
        logger.info(f"TaskGraph for run {self.state.run_id} cancelled")

    def rollback(self) -> None:
        self.run_status = RunStatus.ROLLED_BACK
        logger.info(f"TaskGraph for run {self.state.run_id} rolled back")

    def emit_log(self, step_name: str, level: str, message: str) -> None:
        if self.on_step_log_cb:
            try:
                self.on_step_log_cb(step_name, level, message)
            except Exception as err:
                logger.warning(f"Error in step log callback: {err}")

    def get_sequence(
        self,
        resume_from: Optional[str] = None,
        parallel_groups: Optional[List[List[Tuple[str, Type[BaseAgent]]]]] = None,
    ) -> List[Tuple[str, Type[BaseAgent]]]:
        if parallel_groups:
            return [(name, cls) for group in parallel_groups for name, cls in group]

        if resume_from:
            result = []
            found = False
            for name, cls in self.NODE_SEQUENCE:
                if name == resume_from:
                    found = True
                if found:
                    result.append((name, cls))
            return result

        return list(self.NODE_SEQUENCE)

    def resolve_model(self, node_name: str) -> str:
        if node_name in self.advanced_model_map:
            return self.advanced_model_map[node_name]
        return self.router.resolve_model(node_name)

    def _compute_backoff(self, attempt: int) -> float:
        delay = self.retry_base * (self.retry_factor**attempt)
        capped = min(delay, self.retry_max)
        jitter = capped * RETRY_JITTER * (random.random() * 2 - 1)
        return capped + jitter

    async def _execute_node_with_retry(
        self,
        node_name: str,
        agent_cls: Type[BaseAgent],
        model_name: str,
    ) -> bool:
        previous_errors: Set[str] = set()

        for attempt in range(self.max_retries + 1):
            attempt_number = attempt + 1
            adapter = self.router.get_adapter(node_name)
            agent = agent_cls(name=node_name, adapter=adapter, model_name=model_name)

            status = NodeStatus(
                node_name=node_name,
                status="running",
                started_at=time.time(),
            )
            self.state.nodes[node_name] = status
            self.state.current_node = node_name
            self.state.save_checkpoint()

            self.tracer.log_event(
                "task_start",
                node_name,
                {"model": model_name, "attempt": attempt_number},
            )
            self.emit_log(
                node_name,
                "info",
                f"Executing agent {node_name} (attempt {attempt_number}/{self.max_retries + 1}) using {model_name}...",
            )

            try:
                out = await agent.execute(self.state)
                status.status = "completed"
                status.completed_at = time.time()
                status.output = out
                self.tracer.log_event("task_completed", node_name, out)

                usage_info = out.get("_usage") if isinstance(out, dict) else None
                if usage_info:
                    p_tokens = usage_info.get("prompt_tokens", 150)
                    c_tokens = usage_info.get("completion_tokens", 50)
                    cost = usage_info.get("estimated_cost_usd", 0.0005)
                    sandbox_tier_val = self.state.shared_data.get("sandbox_tier", "A")
                    self.cost_tracker.add_usage(node_name, p_tokens, c_tokens, cost, model_id=model_name, sandbox_tier=str(sandbox_tier_val))
                else:
                    p_tokens = 150
                    c_tokens = 50
                    cost = 0.0005
                    sandbox_tier_val = self.state.shared_data.get("sandbox_tier", "A")
                    self.cost_tracker.add_usage(node_name, p_tokens, c_tokens, cost, model_id=model_name, sandbox_tier=str(sandbox_tier_val))

                try:
                    ledger = get_usage_ledger()
                    ledger.record(
                        UsageEvent(
                            run_id=self.state.run_id,
                            org_id=self.state.shared_data.get("org_id", "unknown"),
                            step_id=node_name,
                            attempt_number=attempt_number,
                            tokens_in=p_tokens,
                            tokens_out=c_tokens,
                            model_id=model_name,
                            sandbox_tier=self.state.shared_data.get("sandbox_tier", "A"),
                            wall_clock_ms=int((time.time() - status.started_at) * 1000) if status.started_at else 0,
                            cost_usd=cost,
                        )
                    )
                except Exception as ledger_err:
                    logger.warning("Failed to record usage event for step %s: %s", node_name, ledger_err)

                ctx_truncated = bool(out.get("context_truncated")) if isinstance(out, dict) else False
                self._record_step(
                    node_name=node_name,
                    model_name=model_name,
                    status_obj=status,
                    tokens_in=p_tokens,
                    tokens_out=c_tokens,
                    retry_count=attempt,
                    output_ref=out.get("summary", "") if isinstance(out, dict) else "",
                    context_truncated=ctx_truncated,
                )

                self.emit_log(node_name, "success", f"Agent {node_name} completed successfully")
                return True

            except Exception as e:
                err_sig = _error_signature(e)
                status.status = "failed"
                status.completed_at = time.time()
                status.error = str(e)
                self.tracer.log_event(
                    "task_failed",
                    node_name,
                    {"error": str(e), "attempt": attempt_number},
                )

                try:
                    ledger = get_usage_ledger()
                    ledger.record(
                        UsageEvent(
                            run_id=self.state.run_id,
                            org_id=self.state.shared_data.get("org_id", "unknown"),
                            step_id=node_name,
                            attempt_number=attempt_number,
                            tokens_in=0,
                            tokens_out=0,
                            model_id=model_name,
                            sandbox_tier=self.state.shared_data.get("sandbox_tier", "A"),
                            wall_clock_ms=int((time.time() - status.started_at) * 1000) if status.started_at else 0,
                            cost_usd=0.0,
                        )
                    )
                except Exception as ledger_err:
                    logger.warning("Failed to record failed usage event for step %s: %s", node_name, ledger_err)

                self._record_step(
                    node_name=node_name,
                    model_name=model_name,
                    status_obj=status,
                    tokens_in=0,
                    tokens_out=0,
                    retry_count=attempt,
                    status="failed",
                    context_truncated=False,
                )

                self.emit_log(node_name, "error", f"Agent {node_name} failed: {e}")

                if err_sig in previous_errors and attempt > 0:
                    logger.warning(
                        "Identical error signature %s on attempt %d for %s — escalating immediately",
                        err_sig[:12],
                        attempt_number,
                        node_name,
                    )
                    return False

                previous_errors.add(err_sig)

                if attempt >= self.max_retries:
                    logger.error(
                        "Task node %s exhausted all %d retries: %s",
                        node_name,
                        self.max_retries,
                        e,
                    )
                    return False

                delay = self._compute_backoff(attempt)
                logger.info(
                    "Retrying node %s in %.2fs (attempt %d of %d)",
                    node_name,
                    delay,
                    attempt_number,
                    self.max_retries,
                )
                await asyncio.sleep(delay)

        return False

    async def run(
        self,
        resume_from: Optional[str] = None,
        on_node_start: Any = None,
        on_node_complete: Any = None,
        on_node_error: Any = None,
    ) -> OrchestratorState:
        node_sequence = self.get_sequence(resume_from=resume_from)

        start_cb = on_node_start or self.on_step_start_cb
        complete_cb = on_node_complete or self.on_step_complete_cb
        error_cb = on_node_error or self.on_step_fail_cb

        self.run_status = RunStatus.QUEUED
        self._fire_webhook(WebhookEventType.RUN_QUEUED, {"status": RunStatus.QUEUED.value})

        for node_name, agent_cls in node_sequence:
            if self.is_cancelled:
                logger.info(f"Pipeline cancelled before executing {node_name}")
                break

            while self.is_paused and not self.is_cancelled:
                await asyncio.sleep(0.2)

            if self.is_cancelled:
                logger.info(f"Pipeline cancelled during pause before executing {node_name}")
                break

            new_status = self.STATUS_NODE_MAP.get(node_name)
            if new_status:
                self.run_status = RunStatus(new_status)

            model_name = self.resolve_model(node_name)
            if model_name not in self._model_sequence:
                self._model_sequence.append(model_name)

            if start_cb:
                try:
                    start_cb(node_name, model_name)
                except Exception as err:
                    logger.warning(f"Error in start_cb: {err}")

            success = await self._execute_node_with_retry(node_name, agent_cls, model_name)

            if success and node_name == "onboarding":
                repo_map = self.state.shared_data.get("repo_map")
                summary = self.state.shared_data.get("onboarding_summary", {})
                if not repo_map or not summary:
                    logger.warning(
                        "Run %s: onboarding guard failed — AST map or summary missing", self.state.run_id
                    )
                    self.run_status = RunStatus.FAILED
                    break

            if success and node_name == "reproduction":
                repro_evidence = self.state.shared_data.get("reproduction_evidence", {})
                if not self.state.reproduction_test or not repro_evidence:
                    logger.warning(
                        "Run %s: reproduction guard failed — reproduction test not synthesized",
                        self.state.run_id,
                    )
                    self.run_status = RunStatus.FAILED
                    break
                if repro_evidence.get("status") != "reproduced":
                    logger.warning(
                        "Run %s: reproduction guard — repro status is '%s', expected 'reproduced'",
                        self.state.run_id,
                        repro_evidence.get("status"),
                    )
                    self.run_status = RunStatus.FAILED
                    break

            if success and node_name == "patcher":
                self._record_patch()
                gateway_result = self.state.shared_data.get("commit_gateway", {})
                if not gateway_result.get("allowed", True):
                    self.run_status = RunStatus.SECURITY_HOLD
                    self.state.shared_data["security_hold_reason"] = gateway_result.get(
                        "reason", "commit gateway blocked patch"
                    )
                    self._fire_webhook(
                        WebhookEventType.RUN_SECURITY_HOLD,
                        {
                            "reason": self.state.shared_data["security_hold_reason"],
                            "blocked_paths": gateway_result.get("blocked_paths", []),
                        },
                    )
                    break

            if success and node_name == "verifier":
                self._record_verification_stages()

            if complete_cb and success:
                try:
                    status = self.state.nodes.get(node_name)
                    complete_cb(node_name, status.output if status else None)
                except Exception as err:
                    logger.warning(f"Error in complete_cb: {err}")

            if not success:
                self.run_status = RunStatus.FAILED
                if error_cb:
                    try:
                        should_continue = error_cb(node_name, "step failed after retries")
                        if not should_continue:
                            break
                    except Exception:
                        break
                else:
                    break

            self.state.save_checkpoint()

            if self.step_mode:
                self.is_paused = True
                self.step_mode = False

        confidence = float(self.state.shared_data.get("confidence_score", 0.0))
        try:
            threshold = float(self.state.shared_data.get("auto_merge_threshold", 0.95))
        except (TypeError, ValueError):
            threshold = 0.95
        verification_decision = str(self.state.shared_data.get("verification_decision", "human_review"))
        merge_decision = compute_merge_decision(
            verification_passed=self.state.verification_passed,
            confidence=confidence,
            threshold=threshold,
            verification_decision=verification_decision,
            conflict_detected=bool(self.state.shared_data.get("conflict_detected")),
        )
        self.state.shared_data["merge_decision"] = merge_decision

        # Final status is derived from the verification result and merge decision.
        # MERGED is impossible unless verification passed and auto-merge was selected.
        if self.run_status in (RunStatus.FAILED, RunStatus.ROLLED_BACK):
            pass
        elif merge_decision["security_hold"]:
            self.run_status = RunStatus.SECURITY_HOLD
        elif merge_decision["conflict_detected"]:
            self.run_status = RunStatus.CONFLICT_RESOLUTION
        elif not self.state.verification_passed:
            self.run_status = RunStatus.FAILED
        elif merge_decision["auto_merge"]:
            self.run_status = RunStatus.MERGED
        elif merge_decision["needs_human_review"]:
            self.run_status = RunStatus.EVIDENCE_REVIEW
        else:
            self.run_status = RunStatus.FAILED

        self._export_evidence_bundle()

        if self.run_status == RunStatus.SECURITY_HOLD:
            self._fire_webhook(WebhookEventType.RUN_SECURITY_HOLD, {"merge_decision": merge_decision})
        elif self.run_status == RunStatus.ROLLED_BACK:
            self._fire_webhook(WebhookEventType.RUN_ROLLED_BACK, {"merge_decision": merge_decision})
        elif self.run_status == RunStatus.CONFLICT_RESOLUTION:
            self._fire_webhook(
                WebhookEventType.RUN_FAILED,
                {"merge_decision": merge_decision, "reason": "merge_conflict", "conflict_detected": True},
            )
        elif self.run_status == RunStatus.FAILED:
            self._fire_webhook(WebhookEventType.RUN_FAILED, {"merge_decision": merge_decision})
        elif self.run_status == RunStatus.EVIDENCE_REVIEW:
            self._fire_webhook(
                WebhookEventType.RUN_FAILED,
                {"merge_decision": merge_decision, "reason": "human_review_required"},
            )
        else:
            self._fire_webhook(WebhookEventType.RUN_COMPLETED, {"merge_decision": merge_decision})

        self.state.shared_data["cost_report"] = self.cost_tracker.get_summary()
        self._record_run()
        self.state.save_checkpoint()

        if self._webhook_tasks:
            await asyncio.gather(*self._webhook_tasks, return_exceptions=True)
        return self.state

    def _fire_webhook(self, event_type: WebhookEventType, data: Dict[str, Any]) -> None:
        if self.webhook_engine is None:
            return
        org_id = self.state.shared_data.get("org_id")
        try:
            task = asyncio.create_task(self.webhook_engine.dispatch(event_type, self.state.run_id, data, org_id))
            self._webhook_tasks.append(task)
        except Exception as err:
            logger.warning("Failed to schedule webhook %s for run %s: %s", event_type.value, self.state.run_id, err)

    def _record_step(
        self,
        node_name: str,
        model_name: str,
        status_obj: NodeStatus,
        tokens_in: int,
        tokens_out: int,
        retry_count: int,
        status: str = "completed",
        output_ref: str = "",
        context_truncated: bool = False,
    ) -> None:
        if self.records_store is None:
            return
        now = time.time()
        duration_ms = int((now - status_obj.started_at) * 1000) if status_obj.started_at else 0
        step = self._step_records.get(node_name)
        if step is None:
            step = AgentStepRecord(
                run_id=self.state.run_id,
                agent_name=node_name,
                model_id=model_name,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                duration_ms=duration_ms,
                retry_count=retry_count,
                status=status,
                output_ref=output_ref,
                context_truncated=context_truncated,
                recorded_at=now,
            )
            self._step_records[node_name] = step
        else:
            step.tokens_in = tokens_in
            step.tokens_out = tokens_out
            step.duration_ms = duration_ms
            step.retry_count = retry_count
            step.status = status
            step.context_truncated = context_truncated
            if output_ref:
                step.output_ref = output_ref
        try:
            self.records_store.record_step(step)
        except Exception as err:
            logger.warning("Failed to record agent step %s for run %s: %s", node_name, self.state.run_id, err)

    def _record_patch(self) -> None:
        if self.records_store is None:
            return
        diff = self.state.patch_diff or ""
        touched = [line[4:].replace("\t", " ") for line in diff.splitlines() if line.startswith("+++ ")]
        touched = [t.split(" ")[0] for t in touched if "/dev/null" not in t]
        risk_flags: List[str] = []
        try:
            if self.router.classify_patch_risk(len(diff), touched):
                risk_flags.append("high_risk")
        except Exception as err:
            logger.debug("Patch risk classification failed for run %s: %s", self.state.run_id, err)
        patch_summary = self.state.shared_data.get("patch_summary")
        apply_status = patch_summary.get("apply_status") if isinstance(patch_summary, dict) else "applied"
        try:
            self.records_store.record_patch(
                PatchRecord(
                    run_id=self.state.run_id,
                    diff_hash=hashlib.sha256(diff.encode("utf-8")).hexdigest(),
                    diff_ref=self.state.snapshot_id or "",
                    files_touched=len(touched),
                    risk_flags=risk_flags,
                    apply_status=str(apply_status or "applied"),
                )
            )
        except Exception as err:
            logger.warning("Failed to record patch for run %s: %s", self.state.run_id, err)

    def _record_verification_stages(self) -> None:
        if self.records_store is None:
            return
        try:
            output = dict(self.state.shared_data.get("verification_output") or {})
            for record in verification_stage_records(self.state.run_id, output):
                self.records_store.record_verification(record)
        except Exception as err:
            logger.warning("Failed to record verification results for run %s: %s", self.state.run_id, err)

    def _record_run(self) -> None:
        if self.records_store is None:
            return
        try:
            cost_report = self.cost_tracker.get_summary()
            self.records_store.record_run(
                RunRecord(
                    run_id=self.state.run_id,
                    org_id=str(self.state.shared_data.get("org_id", "default")),
                    repo_id=self.state.repo_path,
                    issue_text=self.state.issue_description,
                    status=self.run_status.value if isinstance(self.run_status, RunStatus) else str(self.run_status),
                    sandbox_tier=str(self.state.shared_data.get("sandbox_tier", "A")),
                    model_sequence=list(self._model_sequence),
                    verification_passed=self.state.verification_passed,
                    confidence_score=float(self.state.shared_data.get("confidence_score", 0.0)),
                    merge_decision=dict(self.state.shared_data.get("merge_decision") or {}),
                    cost_usd=float(cost_report.get("total_cost_usd", 0.0)),
                    started_at=self.state.created_at,
                    completed_at=time.time(),
                )
            )
        except Exception as err:
            logger.warning("Failed to record run %s: %s", self.state.run_id, err)

    def _export_evidence_bundle(self) -> None:
        if self.evidence_bundler is None:
            return
        try:
            trace_events = [e.model_dump() for e in self.tracer.events]
            bundle = EvidenceBundle(
                run_id=self.state.run_id,
                verified_patch=self.state.patch_diff or "",
                verification_success=self.state.verification_passed,
                test_summary=dict(self.state.shared_data.get("verification_output") or {}),
                cost_report=dict(self.state.shared_data.get("cost_report") or self.cost_tracker.get_summary()),
                trace_events=trace_events,
                rollback_snapshot_id=self.state.snapshot_id,
                merge_decision=dict(self.state.shared_data.get("merge_decision") or {}),
            )
            entry = self.evidence_bundler.export_bundle(bundle)
            self.state.shared_data["evidence_bundle_chain_hash"] = entry.chain_hash
            self.state.shared_data["evidence_bundle_payload_hash"] = entry.payload_hash
            self.state.shared_data["evidence_exported"] = True
            self._fire_webhook(WebhookEventType.EVIDENCE_READY, {"chain_hash": entry.chain_hash})
        except Exception as err:
            logger.warning("Failed to export evidence bundle for run %s: %s", self.state.run_id, err)
