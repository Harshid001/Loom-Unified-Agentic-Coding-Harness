"""API package bootstrap.

The server module is legacy-heavy and intentionally kept stable; this package installs
a narrow import-time hook that applies the centralized production hardening layer
immediately after ``loom.api.server`` finishes defining its routes.
"""

from __future__ import annotations

import importlib.abc
import importlib.machinery
import sys
from types import ModuleType


class _ServerLoader(importlib.abc.Loader):
    def __init__(self, wrapped: importlib.abc.Loader):
        self._wrapped = wrapped

    def create_module(self, spec):
        create = getattr(self._wrapped, "create_module", None)
        return create(spec) if create else None

    def exec_module(self, module: ModuleType) -> None:
        self._wrapped.exec_module(module)
        from loom.api.hardening import harden_server_module

        harden_server_module(module)
        for finder in list(sys.meta_path):
            if isinstance(finder, _ServerFinder):
                try:
                    sys.meta_path.remove(finder)
                except ValueError:
                    pass


class _ServerFinder(importlib.abc.MetaPathFinder):
    TARGET = "loom.api.server"

    def find_spec(self, fullname, path=None, target=None):
        if fullname != self.TARGET:
            return None
        spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        if spec is None or spec.loader is None:
            return spec
        spec.loader = _ServerLoader(spec.loader)
        return spec


if not any(isinstance(finder, _ServerFinder) for finder in sys.meta_path):
    sys.meta_path.insert(0, _ServerFinder())
