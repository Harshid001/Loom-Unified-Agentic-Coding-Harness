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
    api_key: str = Field(..., description="Provider API key")


class DetectModelsResponse(BaseModel):
    models: List[str]
    valid: bool
    provider: str = ""
    detail: Optional[str] = None


CURATED_MODELS: Dict[str, List[str]] = {
    "anthropic": [
        "claude-3-5-sonnet-20241022",
        "claude-3-7-sonnet-20250219",
        "claude-3-5-haiku-20241022",
        "claude-3-opus-20240229",
    ],
    "openai": [
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-4-turbo",
        "o1",
        "o1-mini",
        "o3-mini",
    ],
    "deepseek": [
        "deepseek-chat",
        "deepseek-reasoner",
        "deepseek-v3",
        "deepseek/deepseek-chat",
    ],
    "gemini": [
        "gemini-3-flash-preview",
        "gemini-3-pro-preview",
        "gemini-3.7-flash",
        "gemini-3.5-flash",
        "gemini-3.1-flash-lite",
        "gemini-2.5-pro",
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
    ],
}


def normalize_provider(provider: str) -> str:
    p = provider.strip().lower()
    if p in {"google", "google_ai", "gemini"}:
        return "gemini"
    if p in {"claude", "anthropic"}:
        return "anthropic"
    return p


def get_provider_models(provider_norm: str) -> List[str]:
    curated = CURATED_MODELS.get(provider_norm, [])

    try:
        import litellm

        if hasattr(litellm, "get_model_list") and callable(litellm.get_model_list):
            raw = litellm.get_model_list()
            if isinstance(raw, list) and raw:
                filtered = [m for m in raw if provider_norm in str(m).lower()]
                if filtered:
                    return list(dict.fromkeys(curated + filtered))

        if hasattr(litellm, "models_by_provider") and isinstance(litellm.models_by_provider, dict):
            provider_key = provider_norm
            models = litellm.models_by_provider.get(provider_key, [])
            if not models and provider_norm == "gemini":
                models = litellm.models_by_provider.get("gemini", []) or litellm.models_by_provider.get("vertex_ai", [])

            clean = [
                m
                for m in models
                if isinstance(m, str)
                and not any(
                    skip in m.lower()
                    for skip in ["embed", "audio", "tts", "realtime", "image", "transcribe", "moderation"]
                )
            ]
            if clean:
                return list(dict.fromkeys(curated + clean[:25]))
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
            detail="Invalid API key format",
        )

    models = get_provider_models(provider_norm)
    if not models:
        models = [f"{provider_norm}-default"]

    # Temporarily store in memory dict
    _session_keys[provider_norm] = api_key
    _detected_models[provider_norm] = models

    # Update runtime environment variable
    set_runtime_api_key(provider_norm, api_key)

    logger.info("Successfully detected %d models for provider '%s'", len(models), provider_norm)
    return DetectModelsResponse(
        models=models,
        valid=True,
        provider=provider_norm,
        detail=f"Detected {len(models)} models for {provider_norm}",
    )
