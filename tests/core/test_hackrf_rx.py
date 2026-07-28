"""
tests/core/test_hackrf_rx.py
Mimir RF Scanner — HackRFReceiver RX stream tests

Tests for core/device/hackrf_rx.py
All tests use mocks — no hardware required.
"""

import os
import sys
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from core.device.hackrf_rx import HackRFReceiver
from tests.core.soapy_doubles import FakeSoapySDRKwargs


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


class TestHackRFRetuneSettle:
    """Phase 44: the retune settle must run while the stream is STOPPED.

    The PLL settling transient must never be captured into the ring buffer,
    so time.sleep() must run between setFrequency and activateStream (in
    set_center_frequency) and between setupStream and activateStream (in
    open()). All tests pass retune_settle_sec=0.0 except the one test that
    verifies the default, so the suite does not burn real wall-clock time.
    """

    @staticmethod
    def _open_receiver(**kwargs):
        """A receiver wired as if open(), without touching SoapySDR."""
        receiver = HackRFReceiver(**kwargs)
        receiver._is_open = True
        receiver._center_freq_hz = 98_000_000.0
        receiver._stream = MagicMock()
        receiver._device = MagicMock()
        return receiver

    def test_set_center_frequency_settles_before_activate_stream(self):
        """T1: sleep must precede activateStream on a retune (ordering)."""
        receiver = self._open_receiver(retune_settle_sec=0.0)
        manager = MagicMock()
        manager.attach_mock(receiver._device.activateStream, "activateStream")
        with patch("core.device.hackrf_rx.time.sleep") as mock_sleep:
            manager.attach_mock(mock_sleep, "sleep")
            receiver.set_center_frequency(109_000_000.0)
        calls = [c[0] for c in manager.mock_calls]
        sleep_idx = calls.index("sleep")
        activate_idx = calls.index("activateStream")
        assert sleep_idx < activate_idx, (
            f"sleep must precede activateStream, "
            f"got sleep={sleep_idx}, activate={activate_idx}"
        )

    def test_set_center_frequency_sleeps_exactly_once(self):
        """T2: the settle sleep must not be duplicated in the method."""
        receiver = self._open_receiver(retune_settle_sec=0.0)
        with patch("core.device.hackrf_rx.time.sleep") as mock_sleep:
            receiver.set_center_frequency(109_000_000.0)
        assert mock_sleep.call_count == 1

    def test_open_settles_before_activate_stream(self):
        """T3: open() must sleep between setupStream and activateStream."""
        mock_soapy = MagicMock()
        mock_soapy.SOAPY_SDR_RX = 1
        mock_soapy.SOAPY_SDR_CF32 = "CF32"
        mock_device = MagicMock()
        mock_soapy.Device.return_value = mock_device
        mock_soapy.Device.enumerate.return_value = [
            FakeSoapySDRKwargs({"driver": "hackrf", "serial": "0000"})
        ]
        sys.modules["SoapySDR"] = mock_soapy
        try:
            receiver = HackRFReceiver(retune_settle_sec=0.0)
            manager = MagicMock()
            manager.attach_mock(mock_device.activateStream, "activateStream")
            with patch("core.device.hackrf_rx.time.sleep") as mock_sleep:
                manager.attach_mock(mock_sleep, "sleep")
                receiver.open()
            calls = [c[0] for c in manager.mock_calls]
            sleep_idx = calls.index("sleep")
            activate_idx = calls.index("activateStream")
            assert sleep_idx < activate_idx, (
                f"sleep must precede activateStream in open(), "
                f"got sleep={sleep_idx}, activate={activate_idx}"
            )
        finally:
            if "SoapySDR" in sys.modules:
                del sys.modules["SoapySDR"]

    def test_retune_settle_sec_defaults_to_quarter_second(self):
        """T4: the constructor default must be 0.25 (behaviour-neutral)."""
        receiver = HackRFReceiver()
        assert receiver._retune_settle_sec == 0.25

    def test_retune_settle_sec_is_honoured(self):
        """T5: a passed retune_settle_sec value is what time.sleep receives."""
        receiver = self._open_receiver(retune_settle_sec=0.0)
        with patch("core.device.hackrf_rx.time.sleep") as mock_sleep:
            receiver.set_center_frequency(109_000_000.0)
        mock_sleep.assert_called_once_with(0.0)
