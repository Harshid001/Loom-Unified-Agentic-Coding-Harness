"""Route introspection helpers and sub-route modules."""

from __future__ import annotations

from typing import Any, Iterator


def iter_routes(app: Any) -> Iterator[Any]:
    """Yield every route object registered on ``app``.

    starlette >= 1.1 wraps routers attached via ``include_router`` in
    ``_IncludedRouter`` objects instead of flattening their routes into
    ``app.routes``. Traverse those wrappers so callers can introspect the
    full route table regardless of the installed starlette version.
    """
    stack = list(getattr(app, "routes", []))
    while stack:
        route = stack.pop()
        if type(route).__name__ == "_IncludedRouter":
            inner = getattr(getattr(route, "original_router", None), "routes", [])
            stack.extend(reversed(inner))
        else:
            yield route
