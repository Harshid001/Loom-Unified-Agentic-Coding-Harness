import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from loom.auth.context import get_effective_principal, in_request_auth_context


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
        import os

        if not checkpoint_dir:
            checkpoint_dir = str(Path.home() / ".loom" / "checkpoints")
        path = Path(checkpoint_dir)
        path.mkdir(parents=True, exist_ok=True)
        file_path = path / f"checkpoint_{self.run_id}.json"
        sig_path = path / f"checkpoint_{self.run_id}.sig"

        sensitive_keys = {
            "_org",
            "stripe_customer_id",
            "stripe_subscription_id",
            "stripe_account_id",
            "secret",
            "password",
            "api_key",
            "token",
        }

        def _sanitize(obj: Any) -> Any:
            if isinstance(obj, dict):
                return {
                    k: _sanitize(v)
                    for k, v in obj.items()
                    if not k.startswith("__") and k.lower() not in sensitive_keys
                }
            if isinstance(obj, list):
                return [_sanitize(v) for v in obj]
            try:
                json.dumps(obj)
                return obj
            except (TypeError, ValueError):
                return str(obj)

        data = _sanitize(self.model_dump())
        raw_text = json.dumps(data, indent=2, sort_keys=True)
        raw_bytes = raw_text.encode("utf-8")

        tmp_file = path / f"checkpoint_{self.run_id}.json.tmp"
        tmp_file.write_bytes(raw_bytes)

        key = (
            os.getenv("LOOM_CHECKPOINT_HMAC_KEY")
            or os.getenv("LOOM_EVIDENCE_HMAC_KEY")
            or os.getenv("LOOM_API_KEY")
        )
        if key:
            import hashlib
            import hmac

            sig = hmac.new(key.encode("utf-8"), raw_bytes, hashlib.sha256).hexdigest()
            tmp_sig = path / f"checkpoint_{self.run_id}.sig.tmp"
            tmp_sig.write_text(sig, encoding="utf-8")
            tmp_sig.replace(sig_path)

        tmp_file.replace(file_path)

    @classmethod
    def load_checkpoint(cls, run_id: str, checkpoint_dir: Optional[str] = None) -> Optional["OrchestratorState"]:
        import os
        import secrets

        if not checkpoint_dir:
            checkpoint_dir = str(Path.home() / ".loom" / "checkpoints")
        path = Path(checkpoint_dir)
        file_path = path / f"checkpoint_{run_id}.json"
        sig_path = path / f"checkpoint_{run_id}.sig"
        if not file_path.exists():
            return None

        raw_bytes = file_path.read_bytes()
        key = (
            os.getenv("LOOM_CHECKPOINT_HMAC_KEY")
            or os.getenv("LOOM_EVIDENCE_HMAC_KEY")
            or os.getenv("LOOM_API_KEY")
        )
        is_prod = os.getenv("LOOM_ENV", "").lower() in ("prod", "production")

        if key:
            if not sig_path.exists():
                if is_prod:
                    raise PermissionError(f"Unsigned checkpoint rejected in production posture for run {run_id}")
            else:
                import hashlib
                import hmac

                sig = sig_path.read_text(encoding="utf-8").strip()
                expected = hmac.new(key.encode("utf-8"), raw_bytes, hashlib.sha256).hexdigest()
                if not secrets.compare_digest(sig, expected):
                    raise PermissionError(f"Checkpoint HMAC signature mismatch for run {run_id}")

        data = json.loads(raw_bytes.decode("utf-8"))
        if in_request_auth_context():
            principal = get_effective_principal()
            state_org = data.get("shared_data", {}).get("org_id")
            if state_org is not None and state_org != principal.org_id:
                # Hide cross-tenant resources as not-found rather than revealing
                # whether the run exists.
                return None
        return cls(**data)
