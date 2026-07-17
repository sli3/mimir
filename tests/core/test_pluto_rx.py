"""
tests/core/test_pluto_rx.py
Mimir RF Scanner — PlutoReceiver RX stream tests

Tests for core/device/pluto_rx.py
All tests use mocks — no hardware required.

MOCKING RULE — READ BEFORE ADDING TESTS
───────────────────────────────────────
SoapySDR enumeration results MUST be mocked with FakeSoapySDRKwargs, never
with a plain dict. See tests/core/soapy_doubles.py for why: a dict has .get()
and the real SoapySDRKwargs object does not, so a dict mock is more permissive
than the hardware. Dict mocks in this file previously certified an open()
that could not open the device.
"""

import logging
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from core.device.pluto_rx import PlutoReceiver
from core.legal.compliance_guard import HardwareTransmitError
from tests.core.soapy_doubles import FakeSoapySDRKwargs


class TestPlutoReceiver:
    def setup_method(self):
        self.mock_soapy = MagicMock()
        self.mock_soapy.SOAPY_SDR_RX = 1
        self.mock_soapy.SOAPY_SDR_CF32 = "CF32"
        sys.modules["SoapySDR"] = self.mock_soapy

        self.mock_device = MagicMock()
        self.mock_device.getGainMode.return_value = False
        self.mock_soapy.Device.return_value = self.mock_device

        self._default_enumerate = [
            FakeSoapySDRKwargs({"uri": "ip:pluto.local"}),
            FakeSoapySDRKwargs({"uri": "ip:pluto.local"}),
            FakeSoapySDRKwargs({"uri": "usb:3.30.5"}),
        ]
        self.mock_soapy.Device.enumerate.return_value = self._default_enumerate

    def teardown_method(self):
        if "SoapySDR" in sys.modules:
            del sys.modules["SoapySDR"]

    # ── AGC enforcement ─────────────────────────────────────────────────

    def test_agc_disabled_on_open(self):
        """open() calls setGainMode(SOAPY_SDR_RX, 0, False)."""
        receiver = PlutoReceiver()
        receiver.open()
        self.mock_device.setGainMode.assert_called_once_with(1, 0, False)

    def test_agc_still_on_raises_runtime_error(self):
        """getGainMode returns True after disable → RuntimeError."""
        self.mock_device.getGainMode.return_value = True
        receiver = PlutoReceiver()
        with pytest.raises(RuntimeError, match="AGC could not be disabled"):
            receiver.open()

    def test_agc_disabled_proceeds(self):
        """getGainMode returns False → open() succeeds."""
        receiver = PlutoReceiver()
        receiver.open()
        assert receiver.is_open

    # ── Receive direction — legal guard ────────────────────────────────

    def test_rx_direction_uses_soapy_constant_not_hardcoded(self):
        """Direction-taking calls must use SoapySDR's real SOAPY_SDR_RX.

        Every other test in this file sets the mock's SOAPY_SDR_RX to 1.
        If the implementation also hardcoded 1, both paths would agree in
        the mock and no test could detect the divergence — while on real
        hardware a mismatch would route every call to the wrong direction.
        The direction adjacent to receive is transmit, so this is a legal
        exposure on TX-capable hardware, not merely a functional bug.

        This test deliberately uses a different value (7) so it fails if
        the implementation ever reverts to a hardcoded constant.
        """
        self.mock_soapy.SOAPY_SDR_RX = 7

        receiver = PlutoReceiver()
        receiver.open()

        # open() itself must have used the real constant
        self.mock_device.setGainMode.assert_called_once_with(7, 0, False)
        self.mock_device.setBandwidth.assert_called_once_with(7, 0, 2_000_000)

        # ... and so must every post-open call
        self.mock_device.setGain.reset_mock()
        self.mock_device.setFrequency.reset_mock()
        self.mock_device.setSampleRate.reset_mock()

        receiver.set_gain(40.0)
        receiver.set_center_frequency(1_090_000_000.0)
        receiver.set_sample_rate(2_000_000.0)

        self.mock_device.setGain.assert_called_once_with(7, 0, 40.0)
        self.mock_device.setFrequency.assert_called_once_with(
            7, 0, 1_090_000_000.0
        )
        self.mock_device.setSampleRate.assert_called_once_with(
            7, 0, 2_000_000.0
        )

    # ── USB URI preference ──────────────────────────────────────────────

    def test_usb_uri_preferred_over_ip(self):
        """USB URI is selected even when it appears last in the list."""
        results = [
            FakeSoapySDRKwargs({"uri": "ip:pluto.local"}),
            FakeSoapySDRKwargs({"uri": "ip:pluto.local"}),
            FakeSoapySDRKwargs({"uri": "usb:3.37.5"}),
        ]
        self.mock_soapy.Device.enumerate.return_value = results
        receiver = PlutoReceiver()
        receiver.open()
        assert receiver._uri == "usb:3.37.5"
        self.mock_soapy.Device.assert_called_once_with(
            {"driver": "plutosdr", "uri": "usb:3.37.5"}
        )

    def test_no_usb_falls_back_to_first_with_warning(self, caplog):
        """Falls back to first result and logs a warning when no USB URI exists."""
        results = [
            FakeSoapySDRKwargs({"uri": "ip:pluto.local"}),
            FakeSoapySDRKwargs({"uri": "ip:pluto.local"}),
        ]
        self.mock_soapy.Device.enumerate.return_value = results
        receiver = PlutoReceiver()
        caplog.set_level(logging.WARNING, logger="core.device.pluto_rx")
        receiver.open()
        assert receiver._uri == "ip:pluto.local"
        assert "No USB ADALM-PLUTO found" in caplog.text

    def test_absent_uri_key_does_not_raise(self, caplog):
        """An enumeration entry with no "uri" key at all must not raise.

        Real SoapySDR kwargs do not all carry a "uri" key — a live HackRF One
        enumeration (captured 2026-07-17) has none. Whatever tolerates that
        absence must do so without an AttributeError or KeyError, falling back
        with a warning rather than crashing.
        """
        results = [
            FakeSoapySDRKwargs({"driver": "plutosdr", "label": "no uri here"}),
        ]
        self.mock_soapy.Device.enumerate.return_value = results
        receiver = PlutoReceiver()
        caplog.set_level(logging.WARNING, logger="core.device.pluto_rx")
        receiver.open()
        assert receiver._uri is None
        assert "No USB ADALM-PLUTO found" in caplog.text

    def test_empty_enumerate_raises(self):
        """RuntimeError raised when no devices are enumerated."""
        self.mock_soapy.Device.enumerate.return_value = []
        receiver = PlutoReceiver()
        with pytest.raises(RuntimeError, match="No ADALM-PLUTO device found"):
            receiver.open()

    # ── Bandwidth ────────────────────────────────────────────────────────

    def test_default_bandwidth_equals_sample_rate(self):
        """bandwidth_hz=None → setBandwidth called with sample_rate_hz."""
        receiver = PlutoReceiver(sample_rate_hz=2_000_000)
        receiver.open()
        self.mock_device.setBandwidth.assert_called_once_with(1, 0, 2_000_000)

    def test_explicit_bandwidth_used(self):
        """Explicit bandwidth_hz is passed to setBandwidth."""
        receiver = PlutoReceiver(sample_rate_hz=2_000_000, bandwidth_hz=1_500_000)
        receiver.open()
        self.mock_device.setBandwidth.assert_called_once_with(1, 0, 1_500_000)

    # ── Gain ────────────────────────────────────────────────────────────

    def test_set_gain_calls_set_gain(self):
        """set_gain calls setGain with the RX direction and value."""
        receiver = PlutoReceiver()
        receiver.open()
        self.mock_device.setGain.reset_mock()
        receiver.set_gain(40.0)
        self.mock_device.setGain.assert_called_once_with(1, 0, 40.0)

    def test_set_gain_below_zero_raises(self):
        """set_gain(-1) raises ValueError."""
        receiver = PlutoReceiver()
        with pytest.raises(ValueError, match="out of range"):
            receiver.set_gain(-1.0)

    def test_set_gain_above_74_5_raises(self):
        """set_gain(75.0) raises ValueError."""
        receiver = PlutoReceiver()
        with pytest.raises(ValueError, match="out of range"):
            receiver.set_gain(75.0)

    def test_init_rejects_out_of_range_gain(self):
        """Constructor validates gain_db against the same range as set_gain."""
        with pytest.raises(ValueError, match="out of range"):
            PlutoReceiver(gain_db=100.0)
        with pytest.raises(ValueError, match="out of range"):
            PlutoReceiver(gain_db=-1.0)
        valid = PlutoReceiver(gain_db=30.0)
        assert valid.gain_db == 30.0

    def test_no_lna_attribute(self):
        """Pluto has no LNA gain attribute."""
        receiver = PlutoReceiver()
        assert not hasattr(receiver, "lna_gain_db")

    def test_no_vga_attribute(self):
        """Pluto has no VGA gain attribute."""
        receiver = PlutoReceiver()
        assert not hasattr(receiver, "vga_gain_db")

    # ── TX blocking — legal ────────────────────────────────────────────

    def test_transmit_raises(self):
        """transmit raises HardwareTransmitError."""
        receiver = PlutoReceiver()
        with pytest.raises(HardwareTransmitError):
            receiver.transmit()

    def test_write_samples_raises(self):
        """write_samples raises HardwareTransmitError."""
        receiver = PlutoReceiver()
        with pytest.raises(HardwareTransmitError):
            receiver.write_samples()

    def test_set_tx_gain_raises(self):
        """set_tx_gain raises HardwareTransmitError."""
        receiver = PlutoReceiver()
        with pytest.raises(HardwareTransmitError):
            receiver.set_tx_gain()

    def test_set_tx_frequency_raises(self):
        """set_tx_frequency raises HardwareTransmitError."""
        receiver = PlutoReceiver()
        with pytest.raises(HardwareTransmitError):
            receiver.set_tx_frequency()

    def test_writeStream_raises(self):
        """writeStream raises HardwareTransmitError."""
        receiver = PlutoReceiver()
        with pytest.raises(HardwareTransmitError):
            receiver.writeStream()

    def test_setupTxStream_raises(self):
        """setupTxStream raises HardwareTransmitError."""
        receiver = PlutoReceiver()
        with pytest.raises(HardwareTransmitError):
            receiver.setupTxStream()

    def test_activateTxStream_raises(self):
        """activateTxStream raises HardwareTransmitError."""
        receiver = PlutoReceiver()
        with pytest.raises(HardwareTransmitError):
            receiver.activateTxStream()

    def test_soapysdr_tx_never_appears_in_source(self):
        """SOAPY_SDR_TX must not appear in the source file."""
        source_path = (
            Path(__file__).parent.parent.parent / "core" / "device" / "pluto_rx.py"
        )
        content = source_path.read_text(encoding="utf-8")
        assert "SOAPY_SDR_TX" not in content

    # ── Read samples ─────────────────────────────────────────────────────

    def test_read_samples_returns_complex64_of_requested_length(self):
        """read_samples returns a complex64 array of the requested length."""
        receiver = PlutoReceiver()
        receiver._is_open = True
        receiver._center_freq_hz = 1_090_000_000.0
        receiver._stream = MagicMock()
        receiver._device = MagicMock()
        num_samples = 131072
        receiver._device.readStream.return_value = MagicMock(ret=num_samples)

        samples = receiver.read_samples(num_samples)

        assert samples.shape == (num_samples,)
        assert samples.dtype == np.complex64

    def test_read_samples_resets_stream_on_timeout(self):
        """deactivateStream + activateStream called when readStream returns -4."""
        receiver = PlutoReceiver()
        receiver._is_open = True
        receiver._center_freq_hz = 1_090_000_000.0
        mock_stream = MagicMock()
        receiver._stream = mock_stream
        mock_device = MagicMock()
        receiver._device = mock_device

        timeout_result = MagicMock(ret=-4)
        good_result = MagicMock(ret=131072)
        mock_device.readStream.side_effect = [timeout_result, good_result]

        samples = receiver.read_samples(131072)

        mock_device.deactivateStream.assert_called_once_with(mock_stream)
        mock_device.activateStream.assert_called_once_with(mock_stream)
        assert len(samples) == 131072

    def test_read_samples_raises_after_failed_retry(self):
        """RuntimeError raised when both readStream attempts return -4."""
        receiver = PlutoReceiver()
        receiver._is_open = True
        receiver._center_freq_hz = 1_090_000_000.0
        receiver._stream = MagicMock()
        receiver._device = MagicMock()

        timeout_result = MagicMock(ret=-4)
        receiver._device.readStream.return_value = timeout_result

        with pytest.raises(RuntimeError, match="SoapySDR error code -4"):
            receiver.read_samples(131072)

    # ── Device info ──────────────────────────────────────────────────────

    def test_device_info_contains_driver_key(self):
        """device_info contains driver and hardware keys from SoapySDR."""
        self.mock_device.getDriverKey.return_value = "PlutoSDR"
        self.mock_device.getHardwareKey.return_value = "ADALM-PLUTO"
        receiver = PlutoReceiver()
        receiver.open()
        info = receiver.device_info()
        assert info["driver"] == "PlutoSDR"
        assert info["hardware"] == "ADALM-PLUTO"
        assert info["uri"] == "usb:3.30.5"

    def test_device_info_not_open_returns_status(self):
        """device_info returns status when not open."""
        receiver = PlutoReceiver()
        info = receiver.device_info()
        assert info == {"status": "not open"}

    # ── Context manager ──────────────────────────────────────────────────

    def test_context_manager_opens_and_closes(self):
        """PlutoReceiver can be used as a context manager."""
        with PlutoReceiver() as receiver:
            assert receiver.is_open
            assert isinstance(receiver._device, MagicMock)
        assert not receiver.is_open

    def test_open_partial_failure_does_not_leak_device(self):
        """If setupStream raises mid-open(), close() releases the device."""
        self.mock_device.setupStream.side_effect = RuntimeError("simulated")
        receiver = PlutoReceiver()
        with pytest.raises(RuntimeError, match="simulated"):
            receiver.open()
        # open() raised but the device handle was already acquired. A
        # subsequent close() must recover cleanly rather than no-op.
        receiver.close()
        assert receiver._device is None
        assert receiver._stream is None
        assert not receiver.is_open