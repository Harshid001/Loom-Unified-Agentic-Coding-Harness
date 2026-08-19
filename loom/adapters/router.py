import logging
import os
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Deque, Dict, List, Optional, Tuple

from loom.adapters.base import BaseModelAdapter
from loom.adapters.litellm_adapter import LiteLLMAdapter
from loom.business.path_policy import PatchApprovalPolicy

logger = logging.getLogger("loom.adapters.router")

DEFAULT_WEIGHTS = {"w1_cost": 0.25, "w2_latency": 0.15, "w3_success_rate": 0.35, "w4_capability": 0.25}
DEFAULT_SENSITIVE_GLOBS = [
    "**/auth/**",
    "**/billing/**",
    "**/migrations/**",
    "**/security/**",
    "**/secrets/**",
    "**/payment/**",
    "**/credentials/**",
    "*token*",
    "*secret*",
    "*password*",
    "*credential*",
]

PROVIDER_KEY_ENV_MAP: Dict[str, List[str]] = {

    "anthropic": ["ANTHROPIC_API_KEY"],
    "openai": ["OPENAI_API_KEY"],
    "deepseek": ["DEEPSEEK_API_KEY"],
    "gemini": ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
    "google": ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
    "openrouter": ["OPENROUTER_API_KEY"],
}


def set_runtime_api_key(provider: str, key: str) -> None:
    """Override environment variables at runtime for the given provider."""
    env_vars = PROVIDER_KEY_ENV_MAP.get(provider.lower().strip(), [f"{provider.upper().strip()}_API_KEY"])
    for var in env_vars:
        os.environ[var] = key

MODEL_PRICING: Dict[str, Dict[str, float]] = {
    "claude-3-7-sonnet-20250219": {"input": 3.00 / 1e6, "output": 15.00 / 1e6},
    "gpt-4o": {"input": 2.50 / 1e6, "output": 10.00 / 1e6},
    "gpt-4o-mini": {"input": 0.15 / 1e6, "output": 0.60 / 1e6},
    "gpt-4.5-preview": {"input": 75.00 / 1e6, "output": 150.00 / 1e6},
    "o3-mini": {"input": 1.10 / 1e6, "output": 4.40 / 1e6},
    "gemini-3-flash-preview": {"input": 0.15 / 1e6, "output": 0.60 / 1e6},
    "gemini-3-pro-preview": {"input": 1.25 / 1e6, "output": 5.00 / 1e6},
    "gemini-3.7-flash": {"input": 0.15 / 1e6, "output": 0.60 / 1e6},
    "gemini-3.5-flash": {"input": 0.15 / 1e6, "output": 0.60 / 1e6},
    "gemini-3.1-flash-lite": {"input": 0.075 / 1e6, "output": 0.30 / 1e6},
    "gemini-2.5-pro": {"input": 1.25 / 1e6, "output": 5.00 / 1e6},
    "gemini-2.5-flash": {"input": 0.15 / 1e6, "output": 0.60 / 1e6},
    "gemini-2.0-flash": {"input": 0.10 / 1e6, "output": 0.40 / 1e6},
    "gemini-2.0-flash-thinking-exp-01-21": {"input": 0.10 / 1e6, "output": 0.40 / 1e6},
    "gemini-2.0-pro-exp-02-05": {"input": 1.25 / 1e6, "output": 5.00 / 1e6},
    "gemini-2.0-flash-lite": {"input": 0.075 / 1e6, "output": 0.30 / 1e6},
    "deepseek-v4-pro": {"input": 0.27 / 1e6, "output": 1.10 / 1e6},
    "deepseek-v4": {"input": 0.27 / 1e6, "output": 1.10 / 1e6},
    "deepseek-chat": {"input": 0.27 / 1e6, "output": 1.10 / 1e6},
    "deepseek-reasoner": {"input": 0.55 / 1e6, "output": 2.19 / 1e6},
    "deepseek-v3": {"input": 0.27 / 1e6, "output": 1.10 / 1e6},
    "claude-3-opus-20240229": {"input": 15.00 / 1e6, "output": 75.00 / 1e6},
    "ollama/codellama": {"input": 0.0, "output": 0.0},
    "mock": {"input": 0.001 / 1e6, "output": 0.002 / 1e6},
}

CAPABILITY_MATRIX: Dict[str, Dict[str, Any]] = {
    "claude-3-7-sonnet-20250219": {"context_window": 200_000, "languages": ["*"], "strength": "reasoning"},
    "gpt-4o": {"context_window": 128_000, "languages": ["*"], "strength": "tool_calling"},
    "gpt-4o-mini": {"context_window": 128_000, "languages": ["*"], "strength": "cheap"},
    "gpt-4.5-preview": {"context_window": 128_000, "languages": ["*"], "strength": "frontier_reasoning"},
    "o3-mini": {"context_window": 200_000, "languages": ["*"], "strength": "coding_reasoning"},
    "gemini-3-flash-preview": {"context_window": 2_000_000, "languages": ["*"], "strength": "next_gen_intelligence"},
    "gemini-3-pro-preview": {"context_window": 2_000_000, "languages": ["*"], "strength": "next_gen_frontier_reasoning"},
    "gemini-3.7-flash": {"context_window": 2_000_000, "languages": ["*"], "strength": "next_gen_speed_reasoning"},
    "gemini-3.5-flash": {"context_window": 2_000_000, "languages": ["*"], "strength": "next_gen_speed"},
    "gemini-3.1-flash-lite": {"context_window": 2_000_000, "languages": ["*"], "strength": "ultra_fast_lightweight"},
    "gemini-2.5-pro": {"context_window": 2_000_000, "languages": ["*"], "strength": "deep_reasoning"},
    "gemini-2.5-flash": {"context_window": 2_000_000, "languages": ["*"], "strength": "fast_multimodal"},
    "gemini-2.0-flash": {"context_window": 1_000_000, "languages": ["*"], "strength": "fast"},
    "gemini-2.0-flash-thinking-exp-01-21": {"context_window": 1_000_000, "languages": ["*"], "strength": "thinking"},
    "gemini-2.0-pro-exp-02-05": {"context_window": 2_000_000, "languages": ["*"], "strength": "frontier_reasoning"},
    "gemini-2.0-flash-lite": {"context_window": 1_000_000, "languages": ["*"], "strength": "cheap"},
    "deepseek-v4-pro": {"context_window": 128_000, "languages": ["*"], "strength": "reasoning"},
    "deepseek-v4": {"context_window": 128_000, "languages": ["*"], "strength": "reasoning"},
    "deepseek-chat": {"context_window": 128_000, "languages": ["*"], "strength": "reasoning"},
    "deepseek-reasoner": {"context_window": 128_000, "languages": ["*"], "strength": "deep_reasoning"},
    "deepseek-v3": {"context_window": 128_000, "languages": ["*"], "strength": "cost_efficient"},
    "claude-3-opus-20240229": {"context_window": 200_000, "languages": ["*"], "strength": "deep_reasoning"},
    "ollama/codellama": {"context_window": 16_000, "languages": ["*"], "strength": "local"},
    "mock": {"context_window": 4_096, "languages": ["*"], "strength": "testing"},
}


class TaskType(str, Enum):
    ONBOARDING = "onboarding"
    REPRODUCTION = "reproduction"
    PLANNING = "planning"
    PATCHING = "patcher"
    VERIFYING = "verifier"
    REVIEWING = "reviewer"


class RouterEventType(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    TIMEOUT = "timeout"


@dataclass
class RouterEvent:
    model: str
    task_type: TaskType
    event_type: RouterEventType
    latency_ms: int
    timestamp: float = field(default_factory=time.time)


class ConsensusResult:
    def __init__(self, required_patches: int, agreed_model_ids: List[str], passed: bool):
        self.required_patches = required_patches
        self.agreed_model_ids = agreed_model_ids
        self.passed = passed

    def __bool__(self) -> bool:
        return self.passed

    def __repr__(self) -> str:
        return (
            f"ConsensusResult(required={self.required_patches}, "
            f"agreed={len(self.agreed_model_ids)}, passed={self.passed})"
        )


class ModelRouter:
    """Model router with weighted scoring, fallback cascade, and consensus verification."""

    EVENTS_WINDOW_SIZE = 200
    ERROR_RATE_WINDOW_SECONDS = 300
    ERROR_RATE_THRESHOLD = 0.10
    REQUEST_TIMEOUT_MS = 90_000

    def __init__(
        self,
        default_model: str = "claude-3-7-sonnet-20250219",
        mock_mode: bool = False,
        weights: Optional[Dict[str, float]] = None,
        sensitive_globs: Optional[List[str]] = None,
        policy: Optional[PatchApprovalPolicy] = None,
        auto_route: Optional[bool] = None,
    ):
        self.default_model = default_model
        self.mock_mode = mock_mode
        self.auto_route = (default_model.lower() == "auto") if auto_route is None else bool(auto_route)
        self.weights = weights or dict(DEFAULT_WEIGHTS)
        self.sensitive_globs = sensitive_globs or list(DEFAULT_SENSITIVE_GLOBS)
        self.policy = policy or PatchApprovalPolicy(
            sensitive_path_globs=self.sensitive_globs,
        )
        self.adapter = LiteLLMAdapter(mock_mode=mock_mode)

        self._eligible_models: List[str] = [
            "claude-3-7-sonnet-20250219",
            "gpt-4o",
            "gpt-4o-mini",
            "deepseek-v3",
        ]
        if default_model not in self._eligible_models and default_model not in ("auto", "mock"):
            self._eligible_models.append(default_model)
        self._events: Deque[RouterEvent] = deque(maxlen=self.EVENTS_WINDOW_SIZE)
        self._model_quota_headroom: Dict[str, int] = {}

        self.node_model_map: Dict[str, str] = {t.value: default_model for t in TaskType}

    @staticmethod
    def set_runtime_api_key(provider: str, key: str) -> None:
        """Override environment variables at runtime for the given provider."""
        set_runtime_api_key(provider, key)

    def persist_runtime_models(self, shared_data: Dict[str, Any]) -> None:
        """Persist model selector state into shared_data['_runtime_models']."""
        shared_data["_runtime_models"] = {
            "active_model": self.default_model,
            "eligible_models": list(self._eligible_models),
            "node_model_map": dict(self.node_model_map),
            "auto_route": self.auto_route,
        }

    def set_model(self, new_model: str, shared_data: Optional[Dict[str, Any]] = None) -> None:
        self.default_model = new_model
        if new_model.lower() == "auto":
            self.auto_route = True
        else:
            self.auto_route = False
            if new_model not in self._eligible_models and new_model != "mock":
                self._eligible_models.append(new_model)
        for key in self.node_model_map:
            self.node_model_map[key] = new_model
        if shared_data is not None:
            self.persist_runtime_models(shared_data)

    def set_eligible_models(self, models: List[str], shared_data: Optional[Dict[str, Any]] = None) -> None:
        self._eligible_models = list(models)
        if shared_data is not None:
            self.persist_runtime_models(shared_data)

    def set_quota_headroom(self, model: str, remaining_tokens: int) -> None:
        self._model_quota_headroom[model] = remaining_tokens

    def record_event(self, model: str, task_type: TaskType, event_type: RouterEventType, latency_ms: int) -> None:
        self._events.append(RouterEvent(model=model, task_type=task_type, event_type=event_type, latency_ms=latency_ms))

    def _provider_error_rate(self, model: str) -> float:
        now = time.time()
        recent = [
            e
            for e in self._events
            if e.model == model
            and e.event_type in (RouterEventType.FAILURE, RouterEventType.TIMEOUT)
            and (now - e.timestamp) <= self.ERROR_RATE_WINDOW_SECONDS
        ]
        total_recent = sum(
            1 for e in self._events if e.model == model and (now - e.timestamp) <= self.ERROR_RATE_WINDOW_SECONDS
        )
        if total_recent == 0:
            return 0.0
        return len(recent) / total_recent

    def _is_provider_unhealthy(self, model: str) -> bool:
        return self._provider_error_rate(model) > self.ERROR_RATE_THRESHOLD

    def _normalized_cost(self, model: str) -> float:
        max_price = (
            max(
                (MODEL_PRICING.get(m, {}).get("input", 0) + MODEL_PRICING.get(m, {}).get("output", 0))
                for m in self._eligible_models + [self.default_model]
            )
            or 1.0
        )
        pricing = MODEL_PRICING.get(model, {"input": 3e-6, "output": 15e-6})
        combined = pricing["input"] + pricing["output"]
        if max_price == 0:
            return 1.0
        return 1.0 - (combined / max_price)

    def _normalized_latency(self, model: str) -> float:
        now = time.time()
        successes = [
            e
            for e in self._events
            if e.model == model
            and e.event_type == RouterEventType.SUCCESS
            and (now - e.timestamp) <= self.ERROR_RATE_WINDOW_SECONDS
        ]
        if not successes:
            return 0.5
        avg_latency = sum(e.latency_ms for e in successes) / len(successes)
        return 1.0 / (1.0 + avg_latency / 1000.0)

    def _historical_success_rate(self, model: str, task_type: TaskType) -> float:
        now = time.time()
        thirty_days_ago = now - 30 * 86400
        relevant = [
            e for e in self._events if e.model == model and e.task_type == task_type and e.timestamp >= thirty_days_ago
        ]
        if not relevant:
            return 0.85
        successes = sum(1 for e in relevant if e.event_type == RouterEventType.SUCCESS)
        return successes / len(relevant)

    def _capability_match(self, model: str, task_type: TaskType) -> float:
        caps = CAPABILITY_MATRIX.get(model, {"context_window": 128_000})
        context: float = float(caps.get("context_window", 128_000))

        task_context_need = {
            TaskType.ONBOARDING: 64_000,
            TaskType.REPRODUCTION: 32_000,
            TaskType.PLANNING: 64_000,
            TaskType.PATCHING: 128_000,
            TaskType.VERIFYING: 32_000,
            TaskType.REVIEWING: 64_000,
        }.get(task_type, 64_000)

        context_score = min(1.0, context / max(task_context_need, 1))

        if caps.get("strength") == "deep_reasoning" and task_type in (TaskType.PATCHING, TaskType.PLANNING):
            context_score = min(1.0, context_score * 1.1)
        if caps.get("strength") == "cheap" and task_type == TaskType.PATCHING:
            context_score *= 0.85

        return context_score

    def score_model(self, model: str, task_type: TaskType) -> float:
        if self._is_provider_unhealthy(model):
            return 0.0

        headroom = self._model_quota_headroom.get(model, None)
        if headroom is not None and headroom <= 0:
            return 0.0

        w = self.weights
        return (
            w.get("w1_cost", 0.25) * self._normalized_cost(model)
            + w.get("w2_latency", 0.15) * self._normalized_latency(model)
            + w.get("w3_success_rate", 0.35) * self._historical_success_rate(model, task_type)
            + w.get("w4_capability", 0.25) * self._capability_match(model, task_type)
        )

    def rank_models(self, task_type: TaskType, excluded: Optional[List[str]] = None) -> List[Tuple[str, float]]:
        excluded_set = set(excluded or [])
        candidates = [m for m in self._eligible_models if m not in excluded_set]
        if not candidates:
            candidates = [self.default_model]

        scored = [(m, self.score_model(m, task_type)) for m in candidates]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored

    def select_model(
        self,
        task_type: TaskType,
        excluded: Optional[List[str]] = None,
    ) -> str:
        ranked = self.rank_models(task_type, excluded=excluded)
        for model, score in ranked:
            if score > 0:
                return model

        return self.default_model

    def build_fallback_cascade(self, task_type: TaskType) -> List[str]:
        ranked = self.rank_models(task_type)
        cascade = [m for m, s in ranked if s > 0]
        if not cascade:
            cascade = [self.default_model]
        return cascade[:3]

    def _normalize_task_type(self, task_node_name: str) -> Optional[TaskType]:
        if task_node_name in TaskType._value2member_map_:
            return TaskType(task_node_name)
        mapping = {
            "onboarding": TaskType.ONBOARDING,
            "reproduction": TaskType.REPRODUCTION,
            "reproduce": TaskType.REPRODUCTION,
            "planning": TaskType.PLANNING,
            "planner": TaskType.PLANNING,
            "patching": TaskType.PATCHING,
            "patcher": TaskType.PATCHING,
            "verifying": TaskType.VERIFYING,
            "verifier": TaskType.VERIFYING,
            "reviewing": TaskType.REVIEWING,
            "reviewer": TaskType.REVIEWING,
        }
        return mapping.get(task_node_name.lower())

    def resolve_model(self, task_node_name: str) -> str:
        if self.mock_mode:
            return "mock"

        # Explicit model configured (fixed / forced user selection)
        if not self.auto_route and self.default_model != "auto":
            return self.node_model_map.get(task_node_name, self.default_model)

        task_type = self._normalize_task_type(task_node_name)
        if task_type is None:
            return self.node_model_map.get(task_node_name, self.default_model)

        return self.select_model(task_type)

    def classify_patch_risk(
        self,
        diff_size: int,
        touched_files: List[str],
        prior_confidence: Optional[float] = None,
    ) -> bool:
        if self.sensitive_globs != self.policy.sensitive_path_globs:
            self.policy.sensitive_path_globs = list(self.sensitive_globs)
        return self.policy.classify_risk(diff_size, touched_files, prior_confidence)


    def _extract_patch_intent(self, patch_content: str) -> str:
        lines = patch_content.strip().split("\n")
        semantic_lines = [
            line
            for line in lines
            if (line.startswith("+") or line.startswith("-"))
            and not line.startswith("+++")
            and not line.startswith("---")
        ]
        normalized = "\n".join(line.strip("+- ") for line in semantic_lines[:20])
        return normalized[:500]

    def needs_consensus(
        self,
        patch_diff: str,
        touched_files: List[str],
        prior_confidence: Optional[float] = None,
        consensus_mode: str = "auto",
    ) -> bool:
        if consensus_mode == "always-on":
            return True
        if consensus_mode == "off":
            return False

        diff_line_count = len(patch_diff.strip().split("\n"))
        return self.classify_patch_risk(diff_line_count, touched_files, prior_confidence)

    async def verify_consensus(
        self,
        patch_contents: List[str],
        required_agreement: int = 2,
        generate_patch_fn: Optional[Callable[..., Any]] = None,
    ) -> ConsensusResult:
        if len(patch_contents) < required_agreement:
            return ConsensusResult(
                required_patches=required_agreement,
                agreed_model_ids=[],
                passed=False,
            )

        if len(patch_contents) < 2:
            return ConsensusResult(
                required_patches=required_agreement,
                agreed_model_ids=["primary"],
                passed=required_agreement <= 1,
            )

        intents = [self._extract_patch_intent(p) for p in patch_contents]
        agreement_groups: List[List[Tuple[int, str]]] = []

        for idx, intent in enumerate(intents):
            matched = False
            for group in agreement_groups:
                base = group[0][1]
                if self._intents_similar(base, intent):
                    group.append((idx, intent))
                    matched = True
                    break
            if not matched:
                agreement_groups.append([(idx, intent)])

        best_group = max(agreement_groups, key=len)
        model_ids = [patch_contents[i][:30] for i, _ in best_group]
        passed = len(best_group) >= required_agreement

        return ConsensusResult(
            required_patches=required_agreement,
            agreed_model_ids=model_ids,
            passed=passed,
        )

    def _intents_similar(self, intent_a: str, intent_b: str) -> bool:
        if not intent_a or not intent_b:
            return False
        words_a = set(intent_a.lower().split())
        words_b = set(intent_b.lower().split())
        if not words_a or not words_b:
            return False
        intersection = words_a & words_b
        union = words_a | words_b
        jaccard = len(intersection) / len(union)
        return jaccard >= 0.5

    def get_adapter(self, task_node_name: Optional[str] = None) -> BaseModelAdapter:
        return self.adapter

    def estimate_cost(self, model_name: str, prompt_tokens: int, completion_tokens: int) -> float:
        pricing = MODEL_PRICING.get(model_name, MODEL_PRICING["claude-3-7-sonnet-20250219"])
        return (prompt_tokens * pricing["input"]) + (completion_tokens * pricing["output"])
