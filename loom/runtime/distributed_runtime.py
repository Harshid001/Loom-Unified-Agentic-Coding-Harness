"""Production runtime wiring for shared rate limits and cross-replica runs.

This module is only installed by the production entrypoint. Development and CLI
execution keep the existing in-process behavior unchanged.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Awaitable, Callable

from fastapi import FastAPI, HTTPException, Request
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

    original_control_run = server_module.control_run
    original_stream_run_events = server_module.stream_run_events

    # Wrap TaskGraph before any request creates a graph. The wrapper publishes
    # lifecycle events and listens for control commands on the Redis channel.
    import loom.orchestrator.task_graph as task_graph_module

    original_init = task_graph_module.TaskGraph.__init__
    original_run = task_graph_module.TaskGraph.run

    def wrapped_init(self: Any, *args: Any, **kwargs: Any) -> None:
        state = args[0] if args else kwargs.get("state")

        callback_names = (
            "on_step_start",
            "on_step_log",
            "on_step_complete",
            "on_step_fail",
        )
        existing_callbacks = {name: kwargs.get(name) for name in callback_names}

        def publish_event(event_type: str, step_name: str, data: dict[str, Any]) -> None:
            asyncio.create_task(
                coordinator.record_event(
                    state.run_id,
                    {
                        "type": event_type,
                        "timestamp": time.time(),
                        "run_id": state.run_id,
                        "step_name": step_name,
                        "data": data,
                    },
                )
            )

        def step_start(step_name: str, model_name: str) -> None:
            callback = existing_callbacks["on_step_start"]
            if callback:
                callback(step_name, model_name)
            publish_event("step_progress", step_name, {"status": "running", "model": model_name})

        def step_log(step_name: str, level: str, message: str) -> None:
            callback = existing_callbacks["on_step_log"]
            if callback:
                callback(step_name, level, message)
            publish_event("log_entry", step_name, {"level": level, "agent": step_name, "message": message})

        def step_complete(step_name: str, output: Any) -> None:
            callback = existing_callbacks["on_step_complete"]
            if callback:
                callback(step_name, output)
            metrics = output.get("_usage", {}) if isinstance(output, dict) else {}
            publish_event("step_progress", step_name, {"status": "completed", "metrics": metrics})

        def step_fail(step_name: str, error: str) -> None:
            callback = existing_callbacks["on_step_fail"]
            if callback:
                callback(step_name, error)
            publish_event("step_progress", step_name, {"status": "failed", "error": error})

        kwargs["on_step_start"] = step_start
        kwargs["on_step_log"] = step_log
        kwargs["on_step_complete"] = step_complete
        kwargs["on_step_fail"] = step_fail

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
        await coordinator.record_event(
            self.state.run_id,
            {
                "type": "status_change",
                "timestamp": time.time(),
                "run_id": self.state.run_id,
                "step_name": "pipeline",
                "data": {"status": status},
            },
        )
        return result

    # Mutate the existing class so server_module.TaskGraph references remain valid.
    task_graph_module.TaskGraph.__init__ = wrapped_init
    task_graph_module.TaskGraph.run = wrapped_run

    async def wrapped_stream(run_id: str):
        local_entry = server_module.ACTIVE_RUNS.get(run_id)
        if local_entry:
            return await original_stream_run_events(run_id)

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

        if not await coordinator.get_run(run_id):
            return JSONResponse(status_code=404, content={"detail": f"Run {run_id} not found"})
        return StreamingResponse(remote_generator(), media_type="text/event-stream")

    async def wrapped_control(req: Any):
        local_entry = server_module.ACTIVE_RUNS.get(req.run_id)
        if local_entry:
            return await original_control_run(req)
        run = await coordinator.get_run(req.run_id)
        if not run:
            raise HTTPException(status_code=404, detail=f"Run {req.run_id} not found")
        await coordinator.publish_control(
            req.run_id,
            req.action,
            {"model": req.model, "snapshot_id": req.snapshot_id},
        )
        return {"status": "accepted", "action": req.action.lower(), "run_id": req.run_id, "remote": True}

    def token_admin_block(*args: Any, **kwargs: Any):
        raise HTTPException(
            status_code=403,
            detail="Token administration is disabled in production; use the privileged control plane.",
        )

    # APIRoute caches its dependency callable, so update both endpoint and call.
    for route in app.routes:
        path = getattr(route, "path", None)
        if path in ("/api/v1/stream/{run_id}", "/api/stream/{run_id}"):
            route.endpoint = wrapped_stream
            if hasattr(route, "dependant"):
                route.dependant.call = wrapped_stream
        elif path in ("/api/v1/run/control", "/api/run/control"):
            route.endpoint = wrapped_control
            if hasattr(route, "dependant"):
                route.dependant.call = wrapped_control
        elif path in ("/api/v1/auth/tokens", "/api/auth/tokens", "/api/v1/auth/tokens/{token_id}", "/api/auth/tokens/{token_id}"):
            route.endpoint = token_admin_block
            if hasattr(route, "dependant"):
                route.dependant.call = token_admin_block

    app.state.distributed_installed = True
