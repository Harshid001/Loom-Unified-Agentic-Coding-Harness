"""Production container entrypoint."""

# ruff: noqa: I001
import asyncio
import logging
import os

import uvicorn

from loom.api import server as server_module
from loom.api.dependencies import verify_api_key
from loom.runtime.bootstrap import validate_production_environment
from loom.runtime.distributed_runtime import install_production_runtime
from loom.runtime.health import install_distributed_health
from loom.runtime.production_queue import install_production_queue

logger = logging.getLogger("loom.runtime.entrypoint")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        validate_production_environment()
    except Exception as exc:
        logger.warning("Production environment validation skipped / relaxed: %s", exc)

    try:
        asyncio.run(install_production_runtime(server_module.app, server_module))
        install_production_queue(server_module.app)
        install_distributed_health(server_module.app, verify_api_key)
    except Exception as exc:
        logger.warning("Clustered production extensions not installed (running standalone): %s", exc)

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    logger.info("Starting Loom API server on %s:%d", host, port)
    uvicorn.run(
        server_module.app,
        host=host,
        port=port,
        proxy_headers=True,
    )
