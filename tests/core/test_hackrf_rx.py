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
    def test_read_samples_restarts_capture_on_overflow(
        self, caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Overflow logs the frequency and retries without resetting the stream."""
        receiver = HackRFReceiver()
        receiver._is_open = True
        receiver._center_freq_hz = 1_090_000_000.0
        mock_stream = MagicMock()
        receiver._stream = mock_stream
        mock_device = MagicMock()
        receiver._device = mock_device

        # A partial capture precedes overflow; retry must request the full buffer.
        good_result = MagicMock()
        good_result.ret = 131072
        overflow_result = MagicMock(ret=-4)
        mock_device.readStream.side_effect = [
            MagicMock(ret=16), overflow_result, good_result,
        ]

        samples = receiver.read_samples(131072)

        mock_device.deactivateStream.assert_not_called()
        mock_device.activateStream.assert_not_called()
        assert [call.args[2] for call in mock_device.readStream.call_args_list] == [
            131072, 131056, 131072,
        ]
        assert len(samples) == 131072
        assert "overflow at 1090.000 MHz" in caplog.text

    def test_read_samples_raises_after_second_overflow(self) -> None:
        """A repeated overflow raises with its code after exactly two reads."""
        receiver = HackRFReceiver()
        receiver._is_open = True
        receiver._center_freq_hz = 1_090_000_000.0
        receiver._stream = MagicMock()
        receiver._device = MagicMock()

        receiver._device.readStream.return_value = MagicMock(ret=-4)

        with pytest.raises(RuntimeError, match="SoapySDR error code -4"):
            receiver.read_samples(131072)
        assert receiver._device.readStream.call_count == 2
        receiver._device.deactivateStream.assert_not_called()
        receiver._device.activateStream.assert_not_called()

    def test_read_samples_timeout_raises_immediately(self) -> None:
        """Timeout -1 fails on the first read without touching the stream."""
        receiver = HackRFReceiver()
        receiver._is_open = True
        receiver._stream = MagicMock()
        receiver._device = MagicMock()
        receiver._device.readStream.return_value = MagicMock(ret=-1)

        with pytest.raises(RuntimeError, match="SoapySDR error code -1"):
            receiver.read_samples(131072)
        receiver._device.readStream.assert_called_once()
        receiver._device.deactivateStream.assert_not_called()
        receiver._device.activateStream.assert_not_called()


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
