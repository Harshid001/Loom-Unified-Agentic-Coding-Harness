import os
from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel, Field


class RoutingRule(BaseModel):
    agent_name: str
    model: str
    priority: int = 0
    max_budget_usd: Optional[float] = None
    condition: Optional[str] = None


class RoutingProfile(BaseModel):
    name: str
    description: str = ""
    rules: List[RoutingRule] = Field(default_factory=list)


class CostOptimizedRouter:
    """Advanced model router with per-agent model selection, cost optimization, and routing profiles."""

    PRESETS: Dict[str, RoutingProfile] = {
        "balanced": RoutingProfile(
            name="balanced",
            description="Balanced cost and quality — Claude for complex tasks, GPT-4o for simple ones",
            rules=[
                RoutingRule(agent_name="onboarding", model="gpt-4o", priority=1),
                RoutingRule(agent_name="reproduction", model="gpt-4o", priority=1),
                RoutingRule(agent_name="patcher", model="claude-3-5-sonnet-20241022", priority=2),
                RoutingRule(agent_name="verifier", model="gpt-4o", priority=1),
                RoutingRule(agent_name="reviewer", model="claude-3-5-sonnet-20241022", priority=2),
            ],
        ),
        "minimal_cost": RoutingProfile(
            name="minimal_cost",
            description="Lowest cost — routes everything to cheapest available model",
            rules=[
                RoutingRule(agent_name="*", model="gpt-4o", priority=0),
            ],
        ),
        "max_quality": RoutingProfile(
            name="max_quality",
            description="Maximum quality — routes everything to Claude 3.5 Sonnet",
            rules=[
                RoutingRule(agent_name="*", model="claude-3-5-sonnet-20241022", priority=3),
            ],
        ),
        "hybrid": RoutingProfile(
            name="hybrid",
            description="Claude for patching+review, Gemini for onboarding+repro, GPT-4o for verification",
            rules=[
                RoutingRule(agent_name="onboarding", model="gemini-1.5-pro", priority=1),
                RoutingRule(agent_name="reproduction", model="gemini-1.5-pro", priority=1),
                RoutingRule(agent_name="patcher", model="claude-3-5-sonnet-20241022", priority=2),
                RoutingRule(agent_name="verifier", model="gpt-4o", priority=1),
                RoutingRule(agent_name="reviewer", model="claude-3-5-sonnet-20241022", priority=2),
            ],
        ),
    }

    MODEL_COSTS = {
        "claude-3-5-sonnet-20241022": {"input": 0.000003, "output": 0.000015},
        "gpt-4o": {"input": 0.0000025, "output": 0.00001},
        "gemini-1.5-pro": {"input": 0.00000125, "output": 0.000005},
        "deepseek/deepseek-chat": {"input": 0.00000014, "output": 0.00000028},
    }

    def __init__(self, default_model: str = "claude-3-5-sonnet-20241022", profile: str = "balanced"):
        self.default_model = default_model
        self.profile = self.PRESETS.get(profile, self.PRESETS["balanced"])
        self._custom_rules: Dict[str, List[RoutingRule]] = {}
        self._parse_custom_rules()

    def _parse_custom_rules(self):
        for name, profile in self.PRESETS.items():
            for rule in profile.rules:
                if rule.agent_name == "*":
                    continue
                self._custom_rules.setdefault(name, []).append(rule)

    def resolve_model(self, agent_name: str, task_complexity: str = "medium") -> str:
        for rule in self.profile.rules:
            if rule.agent_name == agent_name:
                return rule.model
            if rule.agent_name == "*":
                return rule.model
        return self.default_model

    def estimate_cost(
        self, agent_name: str, estimated_input_tokens: int = 500, estimated_output_tokens: int = 1000
    ) -> Tuple[str, float]:
        model = self.resolve_model(agent_name)
        rates = self.MODEL_COSTS.get(model, {"input": 0.000003, "output": 0.000015})
        cost = (estimated_input_tokens * rates["input"]) + (estimated_output_tokens * rates["output"])
        return model, round(cost, 6)

    def get_routing_table(self) -> List[Tuple[str, str, float]]:
        table = []
        for agent in ["onboarding", "reproduction", "patcher", "verifier", "reviewer"]:
            model, cost = self.estimate_cost(agent)
            table.append((agent, model, cost))
        return table

    @classmethod
    def list_profiles(cls) -> List[str]:
        return list(cls.PRESETS.keys())

    @classmethod
    def get_profile(cls, name: str) -> Optional[RoutingProfile]:
        return cls.PRESETS.get(name)

    def set_profile(self, name: str):
        if name in self.PRESETS:
            self.profile = self.PRESETS[name]

    def add_custom_rule(self, agent_name: str, model: str, priority: int = 0):
        self.profile.rules.append(RoutingRule(agent_name=agent_name, model=model, priority=priority))

    @classmethod
    def available_models(cls) -> List[str]:
        models = list(cls.MODEL_COSTS.keys())
        env_models = []
        for env_var in ["ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "DEEPSEEK_API_KEY"]:
            if os.getenv(env_var):
                if "ANTHROPIC" in env_var:
                    env_models.append("claude-3-5-sonnet-20241022")
                elif "OPENAI" in env_var:
                    env_models.append("gpt-4o")
                elif "GEMINI" in env_var:
                    env_models.append("gemini-1.5-pro")
                elif "DEEPSEEK" in env_var:
                    env_models.append("deepseek/deepseek-chat")
        return list(dict.fromkeys(env_models or models))
