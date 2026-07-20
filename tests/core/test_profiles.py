"""
tests/core/test_profiles.py
Mimir RF Scanner — Device Capability Profile Tests

Tests for core/device/profiles.py
Pure data tests — no hardware, no SoapySDR required.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from core.device.device_base import DeviceBase
from core.device.hackrf_rx import HackRFReceiver
from core.device.pluto_rx import PlutoReceiver
from core.device.profiles import DEVICE_PROFILES


class TestDeviceProfiles:
    """Tests for the DEVICE_PROFILES constant."""

    def test_driver_keys_exactly_hackrf_and_plutosdr(self):
        """Both expected driver keys are present, with no unexpected keys."""
        assert set(DEVICE_PROFILES.keys()) == {"hackrf", "plutosdr"}

    def test_hackrf_frequency_range(self):
        """HackRF One range is exactly 1 MHz to 6 GHz."""
        assert DEVICE_PROFILES["hackrf"]["min_freq_hz"] == 1_000_000
        assert DEVICE_PROFILES["hackrf"]["max_freq_hz"] == 6_000_000_000

    def test_pluto_frequency_range(self):
        """ADALM-PLUTO range is exactly 325 MHz to 3800 MHz (stock AD9363)."""
        assert DEVICE_PROFILES["plutosdr"]["min_freq_hz"] == 325_000_000
        assert DEVICE_PROFILES["plutosdr"]["max_freq_hz"] == 3_800_000_000

    def test_gain_models(self):
        """HackRF uses the split gain model; Pluto uses combined."""
        assert DEVICE_PROFILES["hackrf"]["gain_model"] == "split"
        assert DEVICE_PROFILES["plutosdr"]["gain_model"] == "combined"

    def test_wrapper_classes_are_the_real_classes(self):
        """wrapper_class values are the real receiver classes, not copies."""
        assert DEVICE_PROFILES["hackrf"]["wrapper_class"] is HackRFReceiver
        assert DEVICE_PROFILES["plutosdr"]["wrapper_class"] is PlutoReceiver

    def test_wrapper_classes_subclass_device_base(self):
        """Every wrapper_class is a DeviceBase subclass."""
        for key, profile in DEVICE_PROFILES.items():
            assert issubclass(profile["wrapper_class"], DeviceBase), (
                f"{key} wrapper_class is not a DeviceBase subclass"
            )
