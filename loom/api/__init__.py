"""Loom API package.

PRD-016: The legacy sys.meta_path import hook has been removed.
All security composition is done explicitly in loom.api.app.create_app().

Public API:
    from loom.api.app import create_app
    from loom.api.server import app   # backward-compat uvicorn entry-point
"""

from loom.api.app import create_app

__all__ = ["create_app"]
