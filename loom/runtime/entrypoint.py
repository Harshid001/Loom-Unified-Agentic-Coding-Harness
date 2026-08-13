"""Production container entrypoint."""

# ruff: noqa: I001
import asyncio
import os

import uvicorn

from loom.api import server as server_module
from loom.runtime.bootstrap import validate_production_environment
from loom.runtime.distributed_runtime import install_production_runtime
from loom.runtime.health import install_distributed_health
from loom.runtime.production_queue import install_production_queue


if __name__ == "__main__":
    validate_production_environment()
    asyncio.run(install_production_runtime(server_module.app, server_module))
    install_production_queue(server_module.app)
    install_distributed_health(server_module.app, server_module.verify_api_key)
    uvicorn.run(
        server_module.app,
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        proxy_headers=True,
    )
