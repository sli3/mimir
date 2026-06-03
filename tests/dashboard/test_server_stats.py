import sys
import os
import time
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from dashboard.server import _compute_hackrf_status


class TestComputeHackrfStatus:
    def test_disconnected_when_device_is_none(self):
        with patch("dashboard.server._device_ref", None):
            assert _compute_hackrf_status() == "DISCONNECTED"

    def test_disconnected_when_device_not_open(self):
        mock_device = MagicMock()
        mock_device.is_open = False
        with patch("dashboard.server._device_ref", mock_device):
            assert _compute_hackrf_status() == "DISCONNECTED"

    def test_not_responding_when_recent_hw_error(self):
        mock_device = MagicMock()
        mock_device.is_open = True
        with (
            patch("dashboard.server._device_ref", mock_device),
            patch("dashboard.server._last_hw_error_time", time.time()),
            patch("dashboard.server.time.time", return_value=time.time() + 5.0),
        ):
            assert _compute_hackrf_status() == "NOT_RESPONDING"

    def test_connected_when_no_recent_hw_error(self):
        mock_device = MagicMock()
        mock_device.is_open = True
        with (
            patch("dashboard.server._device_ref", mock_device),
            patch("dashboard.server._last_hw_error_time", time.time() - 60.0),
            patch("dashboard.server.time.time", return_value=time.time()),
        ):
            assert _compute_hackrf_status() == "CONNECTED"

    def test_not_responding_transitions_to_connected_after_30s(self):
        mock_device = MagicMock()
        mock_device.is_open = True
        error_time = 1000.0
        with (
            patch("dashboard.server._device_ref", mock_device),
            patch("dashboard.server._last_hw_error_time", error_time),
            patch("dashboard.server.time.time", return_value=error_time + 29.0),
        ):
            assert _compute_hackrf_status() == "NOT_RESPONDING"
        with (
            patch("dashboard.server._device_ref", mock_device),
            patch("dashboard.server._last_hw_error_time", error_time),
            patch("dashboard.server.time.time", return_value=error_time + 31.0),
        ):
            assert _compute_hackrf_status() == "CONNECTED"
