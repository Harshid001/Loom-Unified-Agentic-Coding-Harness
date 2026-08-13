"""Production container entrypoint."""

import os

import uvicorn

from loom.runtime.bootstrap import validate_production_environment


if __name__ == "__main__":
    validate_production_environment()
    uvicorn.run(
        "loom.api.server:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        proxy_headers=True,
    )
