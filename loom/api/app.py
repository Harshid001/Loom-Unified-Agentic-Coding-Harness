"""PRD-016 — Explicit Application Security Composition.

create_app() is the single entry point for building the Loom FastAPI application.
All middleware and routers are composed here explicitly.  No sys.meta_path hooks,
no runtime route mutation, no module-level side effects.

Security composition order (outermost → innermost):
  1. APIHardeningMiddleware     — body-size limit + public-surface policy
  2. WebhookSignatureMiddleware — raw-body caching + HMAC/token verification
  3. CORSMiddleware             — origin allowlist
  4. security_headers_middleware — response headers (inline @middleware)
  5. rate_limit_middleware       — per-IP sliding window (inline @middleware)
  6. routers                    — each route declares its own Depends chain
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from loom.api.hardening import APIHardeningMiddleware
from loom.api.late_hardening import WebhookSignatureMiddleware

logger = logging.getLogger("loom.api")


def create_app(
    *,
    title: str = "Loom Agentic Harness API",
    version: str = "1.0.0",
    docs_url: str | None = "/docs",
    redoc_url: str | None = "/redoc",
    rate_limit_per_minute: int | None = None,
) -> FastAPI:
    """Build and return a fully-hardened FastAPI application instance.

    This function is idempotent: calling it multiple times produces independent
    application instances, which makes it safe to use in tests.
    """
    app = FastAPI(
        title=title,
        description="Unified Agentic Coding Harness API Server for orchestration, execution, and trace management.",
        version=version,
        docs_url=docs_url,
        redoc_url=redoc_url,
    )

    # ------------------------------------------------------------------ #
    # 1. Request-size + public-surface policy (outermost ASGI layer)      #
    # ------------------------------------------------------------------ #
    app.add_middleware(APIHardeningMiddleware, max_body_bytes=10 * 1024 * 1024)

    # ------------------------------------------------------------------ #
    # 2. Webhook signature validation (raw-body caching + HMAC)           #
    # ------------------------------------------------------------------ #
    app.add_middleware(WebhookSignatureMiddleware)

    # ------------------------------------------------------------------ #
    # 3. CORS                                                             #
    # ------------------------------------------------------------------ #
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

    # ------------------------------------------------------------------ #
    # 4. Security response headers                                        #
    # ------------------------------------------------------------------ #
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

    # ------------------------------------------------------------------ #
    # 5. Per-IP sliding-window rate limiting                              #
    # ------------------------------------------------------------------ #
    default_limit = "1000" if os.getenv("LOOM_ENV", "development").lower() == "development" else "60"
    _rate_limit_requests = rate_limit_per_minute or int(os.getenv("RATE_LIMIT_PER_MINUTE", default_limit))
    _rate_limit_window = 60  # seconds
    _rate_store: dict[str, list[float]] = {}

    @app.middleware("http")
    async def rate_limit_middleware(request: Request, call_next: Any) -> Any:
        if request.url.path.startswith("/api/"):
            client_ip = request.client.host if request.client else "127.0.0.1"
            now = time.time()
            timestamps = [ts for ts in _rate_store.get(client_ip, []) if now - ts < _rate_limit_window]
            if len(timestamps) >= _rate_limit_requests:
                return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded. Too many requests."})
            timestamps.append(now)
            _rate_store[client_ip] = timestamps

            # Bounded store cleanup
            if len(_rate_store) > 5000:
                stale = [ip for ip, tss in _rate_store.items() if not tss or (now - tss[-1] > _rate_limit_window)]
                for ip in stale:
                    _rate_store.pop(ip, None)

        return await call_next(request)

    # ------------------------------------------------------------------ #
    # 6. Routers                                                          #
    # ------------------------------------------------------------------ #
    _attach_routers(app)

    return app


def _attach_routers(app: FastAPI) -> None:
    """Attach all API routers to the application.

    Routers are imported here (not at module level) to avoid circular imports
    and to keep create_app() self-contained.
    """
    # SCIM provisioning router (self-contained)
    from loom.scim.provisioning import scim_router
    app.include_router(scim_router)

    # Main API routes (runs, evidence, streaming, control, CI, integrations)
    from loom.api.server import (
        router_admin,
        router_auth,
        router_health,
        router_integrations,
        router_runs,
        router_webhooks,
    )
    app.include_router(router_health)         # /healthz, /metrics — no auth
    app.include_router(router_auth)           # /api/v1/auth/tokens
    app.include_router(router_runs)           # /api/v1/run, /stream, /runs/*
    app.include_router(router_webhooks)       # outbound webhook management
    app.include_router(router_integrations)   # GitHub, GitLab, Slack
    app.include_router(router_admin)          # entitlements, orgs
