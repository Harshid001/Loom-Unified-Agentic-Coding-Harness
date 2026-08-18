"""Tests for loom.runtime.entrypoint."""
from __future__ import annotations

from unittest.mock import MagicMock, patch


def test_entrypoint_components_wiring():
    with (
        patch("loom.runtime.bootstrap.validate_production_environment") as mock_val,
        patch("loom.runtime.production_queue.install_production_queue") as mock_queue,
        patch("loom.runtime.health.install_distributed_health") as mock_health,
    ):
        mock_val()
        mock_queue(MagicMock())
        mock_health(MagicMock(), MagicMock())

        mock_val.assert_called_once()
        mock_queue.assert_called_once()
        mock_health.assert_called_once()
