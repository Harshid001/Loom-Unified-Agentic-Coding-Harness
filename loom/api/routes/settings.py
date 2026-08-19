"""Model and harness settings endpoints."""

from __future__ import annotations

import logging
import os
from typing import Dict, List, Optional, cast

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from loom.adapters.router import set_runtime_api_key
from loom.api.dependencies import DashboardAuth
from loom.api.models import (
    get_detected_models,
    get_provider_models,
    get_session_keys,
    normalize_provider,
)

logger = logging.getLogger("loom.api.settings")

router_settings = APIRouter(tags=["settings"])

# In-memory default active model setting
_active_model: str = "claude-3-7-sonnet-20250219"


def get_current_active_model() -> str:
    """Return the globally configured active model."""
    return _active_model


def set_current_active_model(model: str) -> str:
    """Set the globally configured active model."""
    global _active_model
    _active_model = model
    return _active_model


class SetModelRequest(BaseModel):
    model: str = Field(..., description="The model ID to set as active (e.g. gpt-4o, claude-3-7-sonnet-20250219)")
    provider: Optional[str] = Field(default=None, description="Optional provider associated with the model")
    api_key: Optional[str] = Field(default=None, description="Optional API key override")


class ProviderStatus(BaseModel):
    configured: bool
    models: List[str]


class ModelConfigResponse(BaseModel):
    active_model: str
    available_models: List[str]
    providers: Dict[str, ProviderStatus]


class SetModelResponse(BaseModel):
    active_model: str
    status: str = "ok"
    detail: Optional[str] = None


@router_settings.get("/api/v1/settings/model", response_model=ModelConfigResponse)
@router_settings.get("/api/settings/model", response_model=ModelConfigResponse)
async def get_model_config(
    _auth: DashboardAuth = cast(DashboardAuth, None),
) -> ModelConfigResponse:
    session_keys = get_session_keys()
    detected_models = get_detected_models()

    provider_names = ["anthropic", "openai", "deepseek", "gemini"]
    providers: Dict[str, ProviderStatus] = {}
    all_models: List[str] = []

    for p in provider_names:
        env_configured = False
        if p == "anthropic" and os.getenv("ANTHROPIC_API_KEY"):
            env_configured = True
        elif p == "openai" and os.getenv("OPENAI_API_KEY"):
            env_configured = True
        elif p == "deepseek" and os.getenv("DEEPSEEK_API_KEY"):
            env_configured = True
        elif p == "gemini" and (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")):
            env_configured = True

        is_configured = env_configured or (p in session_keys)
        models = detected_models.get(p) or get_provider_models(p)
        providers[p] = ProviderStatus(configured=is_configured, models=models)
        all_models.extend(models)

    # Ensure unique and contains active model
    unique_models = list(dict.fromkeys([_active_model] + all_models))

    return ModelConfigResponse(
        active_model=_active_model,
        available_models=unique_models,
        providers=providers,
    )


@router_settings.put("/api/v1/settings/model", response_model=SetModelResponse)
@router_settings.put("/api/settings/model", response_model=SetModelResponse)
async def set_active_model_endpoint(
    req: SetModelRequest,
    _auth: DashboardAuth = cast(DashboardAuth, None),
) -> SetModelResponse:
    model_name = req.model.strip()
    if not model_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Model name must not be empty")

    if req.provider and req.api_key:
        provider_norm = normalize_provider(req.provider)
        set_runtime_api_key(provider_norm, req.api_key.strip())

    set_current_active_model(model_name)
    logger.info("Active model updated to '%s'", model_name)

    return SetModelResponse(
        active_model=model_name,
        status="ok",
        detail=f"Active model successfully set to {model_name}",
    )
