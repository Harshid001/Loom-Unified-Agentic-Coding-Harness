"""Explicit application security composition."""

from __future__ import annotations

import hashlib
import logging
import os
import time
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from loom.api.hardening import APIHardeningMiddleware
from loom.api.late_hardening import (
    PrincipalCleanupMiddleware,
    WebhookSignatureMiddleware,
    install_terminal_webhook_normalizer,
    install_webhook_secret_encryption,
)
from loom.api.route_security_guards import install_route_security_guards
from loom.api.runtime_guards import install_runtime_guards
from loom.auth.runtime_principal import principal_from_headers
from loom.runtime.production_hardening import install as install_runtime_hardening

logger = logging.getLogger("loom.api")


def _production() -> bool:
    return os.getenv("LOOM_ENV", "").lower() in {"prod", "production"}


def create_app(
    *,
    title: str = "Loom Agentic Harness API",
    version: str = "1.0.0",
    docs_url: str | None = "/docs",
    redoc_url: str | None = "/redoc",
    rate_limit_per_minute: int | None = None,
) -> FastAPI:
    """Build and return a fully-hardened FastAPI application instance."""
    install_runtime_hardening()
    app = FastAPI(
        title=title,
        description="Unified Agentic Coding Harness API Server for orchestration, execution, and trace management.",
        version=version,
        docs_url=docs_url,
        redoc_url=redoc_url,
    )

    # Keep runtime guards and route guards on one authoritative credential resolver.
    import loom.api.runtime_guards as runtime_guards
    runtime_guards._principal_from_headers = principal_from_headers

    app.add_middleware(PrincipalCleanupMiddleware)
    install_runtime_guards(app)
    install_route_security_guards(app)
    app.add_middleware(APIHardeningMiddleware, max_body_bytes=10 * 1024 * 1024)
    app.add_middleware(WebhookSignatureMiddleware)

    raw_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
    allowed_origins = [o.strip() for o in raw_origins.split(",") if o.strip()]
    is_wildcard = "*" in allowed_origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=not is_wildcard,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def security_headers_middleware(request: Request, call_next: Any) -> Any:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Content-Security-Policy"] = "default-src 'self'"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

    @app.exception_handler(Exception)
    async def production_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled application error on %s %s", request.method, request.url.path)
        if _production():
            return JSONResponse(
                status_code=500,
                content={
                    "type": "about:blank",
                    "title": "Internal Server Error",
                    "status": 500,
                    "detail": "An unexpected internal error occurred.",
                },
            )
        return JSONResponse(status_code=500, content={"detail": str(exc)})

    default_limit = "1000" if os.getenv("LOOM_ENV", "development").lower() == "development" else "60"
    _rate_limit_requests = rate_limit_per_minute or int(os.getenv("RATE_LIMIT_PER_MINUTE", default_limit))
    _rate_limit_window = 60
    _rate_store: dict[str, list[float]] = {}

    @app.middleware("http")
    async def rate_limit_middleware(request: Request, call_next: Any) -> Any:
        if request.url.path.startswith("/api/"):
            credential = request.headers.get("x-api-key") or request.headers.get("authorization")
            if credential:
                client_key = "credential:" + hashlib.sha256(credential.encode()).hexdigest()
            else:
                client_key = "ip:" + (request.client.host if request.client else "127.0.0.1")
            now = time.time()
            timestamps = [ts for ts in _rate_store.get(client_key, []) if now - ts < _rate_limit_window]
            if len(timestamps) >= _rate_limit_requests:
                return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded. Too many requests."})
            timestamps.append(now)
            _rate_store[client_key] = timestamps
            if len(_rate_store) > 5000:
                stale = [key for key, tss in _rate_store.items() if not tss or now - tss[-1] > _rate_limit_window]
                for key in stale:
                    _rate_store.pop(key, None)
        return await call_next(request)

    install_terminal_webhook_normalizer()
    install_webhook_secret_encryption()

    _attach_routers(app)
    return app


def _attach_routers(app: FastAPI) -> None:
    from loom.scim.provisioning import scim_router
    app.include_router(scim_router)

    from loom.api.server import (
        router_auth,
        router_runs,
        router_webhooks,
        router_integrations,
        router_admin,
        router_health,
    )
    app.include_router(router_health)
    app.include_router(router_auth)
    app.include_router(router_runs)
    app.include_router(router_webhooks)
    app.include_router(router_integrations)
    app.include_router(router_admin)
