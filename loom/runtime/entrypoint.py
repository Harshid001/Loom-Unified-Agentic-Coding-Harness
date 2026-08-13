"""Production container entrypoint."""

# ruff: noqa: I001
import asyncio
import os

import uvicorn

from loom.api import server as server_module
from loom.runtime.bootstrap import validate_production_environment
from loom.runtime.distributed_runtime import install_production_runtime


if __name__ == "__main__":
    validate_production_environment()
    asyncio.run(install_production_runtime(server_module.app, server_module))
    uvicorn.run(
        server_module.app,
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        proxy_headers=True,
    )
