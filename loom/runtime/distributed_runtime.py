"""Production runtime wiring for shared rate limits and cross-replica runs.

This module is only installed by the production entrypoint. Development and CLI
execution keep the existing in-process behavior unchanged.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Awaitable, Callable

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

from loom.infra.distributed import RedisCoordinator, RedisRateLimiter, RunMetadata


async def install_production_runtime(app: FastAPI, server_module: Any) -> None:
    """Attach Redis-backed controls without changing existing API handler contracts."""
    coordinator = RedisCoordinator()
    if not coordinator.enabled:
        raise RuntimeError("Production runtime requires REDIS_URL")
    if not await coordinator.ping():
        raise RuntimeError("Production runtime cannot connect to REDIS_URL")

    limiter = RedisRateLimiter(coordinator)
    app.state.redis_coordinator = coordinator
    app.state.redis_rate_limiter = limiter

    @app.middleware("http")
    async def distributed_rate_limit_middleware(request: Request, call_next: Callable[..., Awaitable[Any]]):
        if request.url.path.startswith("/api/"):
            client_ip = request.client.host if request.client else "unknown"
            if not await limiter.allow(client_ip):
                return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded. Too many requests."})
        return await call_next(request)

    original_create_run = server_module.create_run
    original_control_run = server_module.control_run
    original_stream_run_events = server_module.stream_run_events

    # Wrap TaskGraph before any request creates a graph. The wrapper publishes
    # lifecycle events and listens for control commands on the Redis channel.
    import loom.orchestrator.task_graph as task_graph_module

    original_init = task_graph_module.TaskGraph.__init__
    original_run = task_graph_module.TaskGraph.run

    def wrapped_init(self: Any, *args: Any, **kwargs: Any) -> None:
        state = args[0] if args else kwargs.get("state")
        original_init(self, *args, **kwargs)
        run_id = state.run_id
        org_id = str(state.shared_data.get("org_id", "default"))
        sandbox_tier = str(state.shared_data.get("sandbox_tier", "A"))

        async def register() -> None:
            await coordinator.register_run(
                RunMetadata(
                    run_id=run_id,
                    org_id=org_id,
                    repo_path=state.repo_path,
                    status="queued",
                    sandbox_tier=sandbox_tier,
                    created_at=state.created_at,
                )
            )

        async def control_loop() -> None:
            async for message in coordinator.control_stream(run_id):
                action = str(message.get("action", "")).lower()
                payload = message.get("payload") or {}
                if action == "pause":
                    self.pause()
                elif action == "resume":
                    self.resume()
                elif action == "step":
                    self.step_over()
                elif action == "cancel":
                    self.cancel()
                elif action == "model_switch" and payload.get("model"):
                    self.router.set_model(str(payload["model"]))

        asyncio.create_task(register())
        asyncio.create_task(control_loop())

    async def wrapped_run(self: Any, *args: Any, **kwargs: Any):
        result = await original_run(self, *args, **kwargs)
        status = str(self.run_status.value if hasattr(self.run_status, "value") else self.run_status)
        await coordinator.update_run_status(self.state.run_id, status)
        return result

    task_graph_module.TaskGraph.__init__ = wrapped_init
    task_graph_module.TaskGraph.run = wrapped_run

    async def wrapped_stream(run_id: str):
        local_entry = server_module.ACTIVE_RUNS.get(run_id)
        if local_entry:
            response = await original_stream_run_events(run_id)
            return response

        async def remote_generator():
            for event in await coordinator.list_events(run_id):
                yield f"data: {json.dumps(event)}\n\n"

            pubsub = coordinator.client.pubsub()
            channel = f"loom:run:{run_id}:events"
            await pubsub.subscribe(channel)
            try:
                while True:
                    message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=15.0)
                    if message and message.get("type") == "message":
                        yield f"data: {message['data']}\n\n"
                    else:
                        yield ": keepalive\n\n"
            finally:
                await pubsub.unsubscribe(channel)
                await pubsub.aclose()

        return StreamingResponse(remote_generator(), media_type="text/event-stream")

    async def wrapped_control(req: Any):
        local_entry = server_module.ACTIVE_RUNS.get(req.run_id)
        if local_entry:
            return await original_control_run(req)
        run = await coordinator.get_run(req.run_id)
        if not run:
            raise server_module.HTTPException(status_code=404, detail=f"Run {req.run_id} not found")
        await coordinator.publish_control(
            req.run_id,
            req.action,
            {"model": req.model, "snapshot_id": req.snapshot_id},
        )
        return {"status": "accepted", "action": req.action.lower(), "run_id": req.run_id, "remote": True}

    # Replace registered endpoints rather than changing their route paths or
    # schemas. This keeps existing clients and OpenAPI contracts stable.
    for route in app.routes:
        if getattr(route, "path", None) in ("/api/v1/stream/{run_id}", "/api/stream/{run_id}"):
            route.endpoint = wrapped_stream
        elif getattr(route, "path", None) in ("/api/v1/run/control", "/api/run/control"):
            route.endpoint = wrapped_control
        elif getattr(route, "path", None) in ("/api/v1/run", "/api/run"):
            # Keep the original create_run endpoint object. TaskGraph wrapping
            # provides distributed registration/control without schema changes.
            route.endpoint = original_create_run

    app.state.distributed_installed = True
