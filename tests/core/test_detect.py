"""
tests/core/test_detect.py
Mimir RF Scanner — SDR Detection Layer Tests

Tests for core/device/detect.py
All tests use mocks — no hardware required.

MOCKING RULE — READ BEFORE ADDING TESTS
───────────────────────────────────────
SoapySDR enumeration results MUST be mocked with FakeSoapySDRKwargs, never
with a plain dict. See tests/core/soapy_doubles.py for why: a dict has .get()
and the real SoapySDRKwargs object does not, so a dict mock is more permissive
than the hardware and certifies code that crashes on first contact.
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
from tests.core.soapy_doubles import FakeSoapySDRKwargs


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
            FakeSoapySDRKwargs({"driver": "rtlsdr", "serial": "00000001"}),
            FakeSoapySDRKwargs({"driver": "hackrf", "serial": "abc123"}),
        ]
        assert enumerate_devices() == ["hackrf"]

    def test_enumerate_handles_real_hackrf_kwargs_shape(self):
        """Enumeration works against the exact kwargs shape a real HackRF One
        returns, captured live from hardware on 2026-07-17.

        Note the absence of a "uri" key — that key is Pluto-specific. Any code
        reading it must tolerate its absence rather than raise.
        """
        self.mock_soapy.Device.enumerate.return_value = [
            FakeSoapySDRKwargs(
                {
                    "device": "HackRF One",
                    "driver": "hackrf",
                    "label": "HackRF One #0 a74461c838896b9f",
                    "part_id": "a000cb3c00564755",
                    "serial": "0000000000000000a74461c838896b9f",
                    "version": "2026.01.3",
                }
            ),
        ]
        assert enumerate_devices() == ["hackrf"]

    def test_enumerate_deduplicates_repeated_drivers(self):
        """Two entries for the same driver yield one key, not two."""
        self.mock_soapy.Device.enumerate.return_value = [
            FakeSoapySDRKwargs({"driver": "hackrf", "serial": "aaa"}),
            FakeSoapySDRKwargs({"driver": "hackrf", "serial": "bbb"}),
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
            FakeSoapySDRKwargs({"driver": "plutosdr"}),
            FakeSoapySDRKwargs({"driver": "hackrf"}),
        ]
        device = detect_device()
        assert device.driver == "hackrf"
        assert device.wrapper_class is HackRFReceiver

    def test_no_preference_picks_pluto_when_only_pluto_present(self):
        """detect_device(None) picks Pluto when it is the only device."""
        self.mock_soapy.Device.enumerate.return_value = [
            FakeSoapySDRKwargs({"driver": "plutosdr"}),
        ]
        device = detect_device()
        assert device.driver == "plutosdr"
        assert device.wrapper_class is PlutoReceiver

    def test_preferred_pluto_selected_when_both_present(self):
        """An explicit preference for Pluto wins even when HackRF is present."""
        self.mock_soapy.Device.enumerate.return_value = [
            FakeSoapySDRKwargs({"driver": "hackrf"}),
            FakeSoapySDRKwargs({"driver": "plutosdr"}),
        ]
        device = detect_device("plutosdr")
        assert device.driver == "plutosdr"
        assert device.wrapper_class is PlutoReceiver

    def test_preferred_pluto_missing_raises_naming_requested_and_found(self):
        """Requesting Pluto when only HackRF is present raises RuntimeError
        naming both what was asked for and what was actually found."""
        self.mock_soapy.Device.enumerate.return_value = [
            FakeSoapySDRKwargs({"driver": "hackrf"}),
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
            FakeSoapySDRKwargs({"driver": "hackrf"}),
        ]
        mock_class = MagicMock()
        with patch.dict(DEVICE_PROFILES["hackrf"], {"wrapper_class": mock_class}):
            device = detect_device()
        assert device.wrapper_class is mock_class
        mock_class.assert_not_called()


class TestSoapySDRKwargsDouble:
    """Guards the double itself.

    If FakeSoapySDRKwargs ever grows a .get() method, every test that uses it
    silently reverts to proving nothing — the double would once again be more
    permissive than the hardware. These tests fail loudly if that happens.
    """

    def test_double_has_no_get_method(self):
        """The absence of .get() is the entire purpose of this class."""
        kwargs = FakeSoapySDRKwargs({"driver": "hackrf"})
        assert not hasattr(kwargs, "get")

    def test_double_converts_via_dict(self):
        """dict() must convert it, exactly as it converts the real object."""
        kwargs = FakeSoapySDRKwargs({"driver": "hackrf", "serial": "abc123"})
        assert dict(kwargs) == {"driver": "hackrf", "serial": "abc123"}

    def test_double_matches_real_hardware_shape(self):
        """Mirrors the actual HackRF One enumeration output captured live
        from hardware on 2026-07-17."""
        kwargs = FakeSoapySDRKwargs(
            {
                "device": "HackRF One",
                "driver": "hackrf",
                "label": "HackRF One #0 a74461c838896b9f",
                "part_id": "a000cb3c00564755",
                "serial": "0000000000000000a74461c838896b9f",
                "version": "2026.01.3",
            }
        )
        assert dict(kwargs)["driver"] == "hackrf"
        assert not hasattr(kwargs, "get")

    def test_double_supports_indexing_and_has_key(self):
        """The real object supports [] and has_key(); the double must too."""
        kwargs = FakeSoapySDRKwargs({"driver": "plutosdr", "uri": "usb:3.30.5"})
        assert kwargs["uri"] == "usb:3.30.5"
        assert kwargs.has_key("driver")
        assert not kwargs.has_key("nonexistent")