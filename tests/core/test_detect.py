"""
tests/core/test_detect.py
Mimir RF Scanner — SDR Detection Layer Tests

Tests for core/device/detect.py
All tests use mocks — no hardware required.
"""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from core.device.detect import detect_device, enumerate_devices
from core.device.hackrf_rx import HackRFReceiver
from core.device.pluto_rx import PlutoReceiver
from core.device.profiles import DEVICE_PROFILES


class TestDetect:
    def setup_method(self):
        self.mock_soapy = MagicMock()
        sys.modules["SoapySDR"] = self.mock_soapy

    def teardown_method(self):
        if "SoapySDR" in sys.modules:
            del sys.modules["SoapySDR"]

    # ── enumerate_devices ─────────────────────────────────────────────

    def test_enumerate_returns_empty_when_nothing_found(self):
        """Empty SoapySDR enumeration yields an empty driver list."""
        self.mock_soapy.Device.enumerate.return_value = []
        assert enumerate_devices() == []

    def test_enumerate_ignores_drivers_not_in_device_profiles(self):
        """An unsupported driver (e.g. an rtl-sdr dongle) is ignored
        silently, not treated as an error; supported drivers pass through."""
        self.mock_soapy.Device.enumerate.return_value = [
            {"driver": "rtlsdr", "serial": "00000001"},
            {"driver": "hackrf", "serial": "abc123"},
        ]
        assert enumerate_devices() == ["hackrf"]

    def test_import_failure_raises_runtime_error(self):
        """Missing SoapySDR bindings raise RuntimeError with the install hint."""
        with patch.dict(sys.modules, {"SoapySDR": None}):
            with pytest.raises(
                RuntimeError, match="SoapySDR Python bindings not found"
            ):
                enumerate_devices()
            with pytest.raises(
                RuntimeError, match="SoapySDR Python bindings not found"
            ):
                detect_device()

    # ── detect_device ─────────────────────────────────────────────────

    def test_no_preference_prefers_hackrf_when_both_present(self):
        """detect_device(None) picks HackRF when both devices are present —
        HackRF is the calibrated default (Pluto is uncalibrated until
        Phase 39)."""
        self.mock_soapy.Device.enumerate.return_value = [
            {"driver": "plutosdr"},
            {"driver": "hackrf"},
        ]
        device = detect_device()
        assert device.driver == "hackrf"
        assert device.wrapper_class is HackRFReceiver

    def test_no_preference_picks_pluto_when_only_pluto_present(self):
        """detect_device(None) picks Pluto when it is the only device."""
        self.mock_soapy.Device.enumerate.return_value = [
            {"driver": "plutosdr"},
        ]
        device = detect_device()
        assert device.driver == "plutosdr"
        assert device.wrapper_class is PlutoReceiver

    def test_preferred_pluto_selected_when_both_present(self):
        """An explicit preference for Pluto wins even when HackRF is present."""
        self.mock_soapy.Device.enumerate.return_value = [
            {"driver": "hackrf"},
            {"driver": "plutosdr"},
        ]
        device = detect_device("plutosdr")
        assert device.driver == "plutosdr"
        assert device.wrapper_class is PlutoReceiver

    def test_preferred_pluto_missing_raises_naming_requested_and_found(self):
        """Requesting Pluto when only HackRF is present raises RuntimeError
        naming both what was asked for and what was actually found."""
        self.mock_soapy.Device.enumerate.return_value = [
            {"driver": "hackrf"},
        ]
        with pytest.raises(RuntimeError) as exc_info:
            detect_device("plutosdr")
        message = str(exc_info.value)
        assert "plutosdr" in message
        assert "hackrf" in message

    def test_no_devices_present_raises(self):
        """detect_device raises RuntimeError when nothing is present."""
        self.mock_soapy.Device.enumerate.return_value = []
        with pytest.raises(RuntimeError, match="No supported SDR device found"):
            detect_device()

    def test_wrapper_class_is_never_instantiated(self):
        """detect_device returns the class object itself and never creates
        an instance — detection must not open hardware."""
        self.mock_soapy.Device.enumerate.return_value = [
            {"driver": "hackrf"},
        ]
        mock_class = MagicMock()
        with patch.dict(DEVICE_PROFILES["hackrf"], {"wrapper_class": mock_class}):
            device = detect_device()
        assert device.wrapper_class is mock_class
        mock_class.assert_not_called()
