import json
import logging
import time
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field

from loom.orchestrator.state import OrchestratorState

logger = logging.getLogger("loom.cli.recovery")


class RunRecord(BaseModel):
    run_id: str
    repo_path: str
    issue_description: str
    status: str = "running"
    failed_node: Optional[str] = None
    completed_nodes: List[str] = Field(default_factory=list)
    last_checkpoint: float = Field(default_factory=time.time)
    retry_count: int = 0
    max_retries: int = 3
    model_used: str = "claude-3-7-sonnet-20250219"
    fallback_models: List[str] = Field(default_factory=list)


class RecoveryManager:
    """Manages resumable runs, checkpoint recovery, and agent retry with model fallback."""

    RECORDS_DIR = Path.home() / ".loom" / "runs"
    MAX_RETRIES = 3
    FALLBACK_MODEL_MAP = {
        "claude-3-7-sonnet-20250219": "gpt-4o",
        "gpt-4o": "claude-3-7-sonnet-20250219",
        "gemini-3.1-pro-preview": "gpt-4o",
        "deepseek/deepseek-chat": "gpt-4o",
    }

    @classmethod
    def _ensure_dir(cls):
        cls.RECORDS_DIR.mkdir(parents=True, exist_ok=True)

    @classmethod
    def save_run(cls, record: RunRecord):
        cls._ensure_dir()
        path = cls.RECORDS_DIR / f"{record.run_id}.json"
        path.write_text(json.dumps(record.model_dump(), indent=2), encoding="utf-8")

    @classmethod
    def load_run(cls, run_id: str) -> Optional[RunRecord]:
        cls._ensure_dir()
        path = cls.RECORDS_DIR / f"{run_id}.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return RunRecord(**data)
        except Exception as e:
            logger.warning("Failed to load run record %s: %s", run_id, e)
            return None

    @classmethod
    def list_failed_runs(cls) -> List[RunRecord]:
        cls._ensure_dir()
        failed = []
        for f in cls.RECORDS_DIR.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                record = RunRecord(**data)
                if record.status in ("failed", "running", "interrupted"):
                    failed.append(record)
            except Exception:
                pass
        return sorted(failed, key=lambda r: r.last_checkpoint, reverse=True)

    @classmethod
    def can_resume(cls, run_id: str) -> bool:
        record = cls.load_run(run_id)
        if not record:
            return False
        if record.retry_count >= record.max_retries:
            return False

        checkpoint = OrchestratorState.load_checkpoint(run_id)
        return checkpoint is not None and record.status != "completed"

    @classmethod
    def get_resume_point(cls, run_id: str) -> Optional[str]:
        record = cls.load_run(run_id)
        if not record:
            return None

        checkpoint = OrchestratorState.load_checkpoint(run_id)
        if not checkpoint:
            return None

        all_nodes = ["onboarding", "reproduction", "patcher", "verifier", "reviewer"]
        for node in all_nodes:
            if node not in record.completed_nodes:
                return node

        return None

    @classmethod
    def mark_node_completed(cls, run_id: str, node_name: str):
        record = cls.load_run(run_id)
        if record:
            if node_name not in record.completed_nodes:
                record.completed_nodes.append(node_name)
            record.last_checkpoint = time.time()
            cls.save_run(record)

    @classmethod
    def mark_node_failed(cls, run_id: str, node_name: str):
        record = cls.load_run(run_id)
        if record:
            record.status = "failed"
            record.failed_node = node_name
            record.last_checkpoint = time.time()
            cls.save_run(record)

    @classmethod
    def mark_run_completed(cls, run_id: str, verification_passed: bool):
        record = cls.load_run(run_id)
        if record:
            record.status = "verified" if verification_passed else "failed"
            record.last_checkpoint = time.time()
            cls.save_run(record)

    @classmethod
    def get_fallback_model(cls, model: str) -> Optional[str]:
        return cls.FALLBACK_MODEL_MAP.get(model)

    @classmethod
    def should_retry_with_fallback(cls, run_id: str, node_name: str) -> Optional[str]:
        record = cls.load_run(run_id)
        if not record:
            return None

        record.retry_count += 1
        cls.save_run(record)

        if record.retry_count <= record.max_retries:
            fallback = cls.get_fallback_model(record.model_used)
            if fallback:
                record.fallback_models.append(fallback)
                record.model_used = fallback
                cls.save_run(record)
                return fallback

        return None
