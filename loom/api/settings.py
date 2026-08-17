"""Re-export settings route definitions."""

from __future__ import annotations

from loom.api.routes.settings import (
    ModelConfigResponse,
    ProviderStatus,
    SetModelRequest,
    SetModelResponse,
    get_current_active_model,
    get_model_config,
    router_settings,
    set_active_model_endpoint,
    set_current_active_model,
)

__all__ = [
    "router_settings",
    "SetModelRequest",
    "SetModelResponse",
    "ModelConfigResponse",
    "ProviderStatus",
    "get_model_config",
    "set_active_model_endpoint",
    "get_current_active_model",
    "set_current_active_model",
]
