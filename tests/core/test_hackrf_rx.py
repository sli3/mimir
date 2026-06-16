"""
tests/core/test_hackrf_rx.py
Mimir RF Scanner — HackRFReceiver RX stream tests

Tests for core/device/hackrf_rx.py
All tests use mocks — no hardware required.
"""

import os
import sys
from unittest.mock import MagicMock

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from core.device.hackrf_rx import HackRFReceiver


class TestHackRFReceiver:
    def test_read_samples_resets_stream_on_timeout(self):
        """deactivateStream + activateStream called when readStream returns -4."""
        receiver = HackRFReceiver()
        receiver._is_open = True
        receiver._center_freq_hz = 1_090_000_000.0
        mock_stream = MagicMock()
        receiver._stream = mock_stream
        mock_device = MagicMock()
        receiver._device = mock_device

        # First readStream call returns -4 (timeout); second returns samples
        good_result = MagicMock()
        good_result.ret = 131072
        timeout_result = MagicMock()
        timeout_result.ret = -4
        mock_device.readStream.side_effect = [timeout_result, good_result]

        samples = receiver.read_samples(131072)

        # Stream must be reset between attempts
        mock_device.deactivateStream.assert_called_once_with(mock_stream)
        mock_device.activateStream.assert_called_once_with(mock_stream)
        # Retry must succeed — no RuntimeError raised
        assert len(samples) == 131072

    def test_read_samples_raises_after_failed_retry(self):
        """RuntimeError raised when both readStream attempts return -4."""
        receiver = HackRFReceiver()
        receiver._is_open = True
        receiver._center_freq_hz = 1_090_000_000.0
        receiver._stream = MagicMock()
        receiver._device = MagicMock()

        timeout_result = MagicMock()
        timeout_result.ret = -4
        receiver._device.readStream.return_value = timeout_result

        with pytest.raises(RuntimeError, match="SoapySDR error code -4"):
            receiver.read_samples(131072)
