"""Model discovery and validation endpoints."""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, cast

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from loom.adapters.router import set_runtime_api_key
from loom.api.dependencies import DashboardAuth

logger = logging.getLogger("loom.api.models")

router_models = APIRouter(tags=["models"])

# In-memory dictionary for temporarily storing provider API keys per session
_session_keys: Dict[str, str] = {}
_detected_models: Dict[str, List[str]] = {}


def get_session_keys() -> Dict[str, str]:
    """Return a copy of currently stored session keys."""
    return dict(_session_keys)


def get_detected_models() -> Dict[str, List[str]]:
    """Return currently detected models grouped by provider."""
    return dict(_detected_models)


def clear_session_keys() -> None:
    """Clear temporary in-memory session keys."""
    _session_keys.clear()
    _detected_models.clear()


class DetectModelsRequest(BaseModel):
    provider: str = Field(..., description="Provider name: anthropic, openai, deepseek, gemini")
    api_key: str = Field(..., min_length=1)


class DetectModelsResponse(BaseModel):
    models: List[str]
    valid: bool
    provider: str
    detail: Optional[str] = None


def normalize_provider(provider: str) -> str:
    value = provider.strip().lower()
    aliases = {
        "google": "gemini",
        "google-gemini": "gemini",
        "gemini": "gemini",
        "claude": "anthropic",
        "anthropic": "anthropic",
        "openai": "openai",
        "deepseek": "deepseek",
    }
    return aliases.get(value, value)


def get_provider_models(provider: str) -> List[str]:
    provider = normalize_provider(provider)
    curated = {
        "anthropic": [
            "claude-3-5-sonnet-20241022",
            "claude-3-5-haiku-20241022",
            "claude-3-opus-20240229",
        ],
        "openai": [
            "gpt-4o",
            "gpt-4o-mini",
            "o3-mini",
        ],
        "deepseek": [
            "deepseek-chat",
            "deepseek-reasoner",
        ],
        "gemini": [
            "gemini-2.5-pro",
            "gemini-2.5-flash",
            "gemini-2.0-flash",
        ],
    }.get(provider, [])

    try:
        import litellm

        model_list = getattr(litellm, "model_list", [])
        if model_list:
            for item in model_list:
                if isinstance(item, dict):
                    model_name = item.get("model_name") or item.get("model")
                    if isinstance(model_name, str):
                        if model_name.lower().startswith(provider) or provider in model_name.lower():
                            if model_name not in curated:
                                curated.append(model_name)
    except Exception as exc:
        logger.debug("LiteLLM model retrieval exception: %s", exc)

    return curated


def validate_key_format(provider_norm: str, key: str) -> bool:
    if not key or not isinstance(key, str):
        return False
    stripped = key.strip()
    if len(stripped) < 6:
        return False
    if " " in stripped:
        return False
    return True


@router_models.post("/api/v1/models/detect", response_model=DetectModelsResponse)
@router_models.post("/api/models/detect", response_model=DetectModelsResponse)
async def detect_models(
    req: DetectModelsRequest,
    _auth: DashboardAuth = cast(DashboardAuth, None),
) -> DetectModelsResponse:
    provider_norm = normalize_provider(req.provider)
    if not provider_norm:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Provider name is required")

    api_key = req.api_key.strip()
    if not api_key:
        return DetectModelsResponse(
            models=[],
            valid=False,
            provider=provider_norm,
            detail="API key must not be empty",
        )

    if not validate_key_format(provider_norm, api_key):
        return DetectModelsResponse(
            models=[],
            valid=False,
            provider=provider_norm,
            detail="API key format is invalid",
        )

    models = get_provider_models(provider_norm)
    _session_keys[provider_norm] = api_key
    _detected_models[provider_norm] = models
    set_runtime_api_key(provider_norm, api_key)

    return DetectModelsResponse(
        models=models,
        valid=True,
        provider=provider_norm,
        detail="Provider API key accepted",
    )
