import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class NodeStatus(BaseModel):
    node_name: str
    status: str = "pending"
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    output: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    attempt_count: int = 0
    error_signatures: list[str] = Field(default_factory=list)


class OnboardingSummary(BaseModel):
    summary: str
    build_systems: list[str] = Field(default_factory=list)
    test_frameworks: list[str] = Field(default_factory=list)
    total_files: int = 0


class ReproductionEvidence(BaseModel):
    test_script: str
    status: str
    model_used: Optional[str] = None
    cost_usd: float = 0.0


class PatchSummary(BaseModel):
    patch_diff: str
    snapshot_id: str
    summary: str


class ReviewerReport(BaseModel):
    verdict: str
    comments: list[str] = Field(default_factory=list)
    quality_score: float = 1.0


class CostReport(BaseModel):
    run_id: str
    total_cost_usd: float = 0.0


class OrchestratorState(BaseModel):
    run_id: str
    repo_path: str
    issue_description: str
    current_node: Optional[str] = None
    nodes: Dict[str, NodeStatus] = Field(default_factory=dict)
    shared_data: Dict[str, Any] = Field(default_factory=dict)
    reproduction_test: Optional[str] = None
    patch_diff: Optional[str] = None
    verification_passed: bool = False
    snapshot_id: Optional[str] = None
    created_at: float = Field(default_factory=time.time)

    def set_agent_data(self, key: str, data: BaseModel | Dict[str, Any]):
        if isinstance(data, BaseModel):
            self.shared_data[key] = data.model_dump()
        else:
            self.shared_data[key] = data

    def save_checkpoint(self, checkpoint_dir: Optional[str] = None):
        if not checkpoint_dir:
            checkpoint_dir = str(Path.home() / ".loom" / "checkpoints")
        path = Path(checkpoint_dir)
        path.mkdir(parents=True, exist_ok=True)
        file_path = path / f"checkpoint_{self.run_id}.json"
        file_path.write_text(json.dumps(self.model_dump(), indent=2), encoding="utf-8")

    @classmethod
    def load_checkpoint(cls, run_id: str, checkpoint_dir: Optional[str] = None) -> Optional["OrchestratorState"]:
        if not checkpoint_dir:
            checkpoint_dir = str(Path.home() / ".loom" / "checkpoints")
        file_path = Path(checkpoint_dir) / f"checkpoint_{run_id}.json"
        if not file_path.exists():
            return None
        data = json.loads(file_path.read_text(encoding="utf-8"))
        return cls(**data)
