"""
tests/dashboard/test_shared_state.py
Mimir RF Scanner — Dashboard Shared State Tests

Tests for dashboard/shared_state.py constants.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from dashboard.shared_state import BAND_PROFILES, get_band_for_freq


class TestBandProfiles:
    """Tests for the BAND_PROFILES constant."""

    def test_fm_broadcast_lna_gain_is_calibrated(self):
        """fm_broadcast lna_gain_db must be 24 after calibration."""
        assert BAND_PROFILES["fm_broadcast"]["lna_gain_db"] == 24

    def test_fm_broadcast_vga_gain_is_calibrated(self):
        """fm_broadcast vga_gain_db must be 26 after calibration."""
        assert BAND_PROFILES["fm_broadcast"]["vga_gain_db"] == 26

    def test_aviation_gains_unchanged(self):
        """aviation gains must remain at their pre-calibration values."""
        assert BAND_PROFILES["aviation"]["lna_gain_db"] == 16
        assert BAND_PROFILES["aviation"]["vga_gain_db"] == 20

    def test_adsb_gains_unchanged(self):
        """adsb gains must remain at their pre-calibration values."""
        assert BAND_PROFILES["adsb"]["lna_gain_db"] == 24
        assert BAND_PROFILES["adsb"]["vga_gain_db"] == 24

    def test_all_entries_have_signal_threshold_db(self):
        """Every BAND_PROFILES entry must have a positive signal_threshold_db key."""
        for name, profile in BAND_PROFILES.items():
            assert "signal_threshold_db" in profile, f"{name} missing signal_threshold_db"
            assert isinstance(profile["signal_threshold_db"], (int, float)), f"{name} signal_threshold_db not numeric"
            assert profile["signal_threshold_db"] > 0, f"{name} signal_threshold_db not positive"


class TestGetBandForFreq:
    """Tests for the get_band_for_freq helper."""

    def test_known_freq_returns_profile(self):
        """get_band_for_freq returns a dict for a known center_freq_hz."""
        result = get_band_for_freq(98_000_000)
        assert result is not None
        assert result["signal_threshold_db"] == BAND_PROFILES["fm_broadcast"]["signal_threshold_db"]

    def test_unknown_freq_returns_none(self):
        """get_band_for_freq returns None for a frequency not in BAND_PROFILES."""
        result = get_band_for_freq(100_000_000)
        assert result is None

    def test_none_input_returns_none(self):
        """get_band_for_freq returns None when passed None."""
        result = get_band_for_freq(None)
        assert result is None

    def test_returns_copy_not_reference(self):
        """get_band_for_freq returns a copy — mutations do not affect BAND_PROFILES."""
        result = get_band_for_freq(98_000_000)
        result["signal_threshold_db"] = 999.0
        assert BAND_PROFILES["fm_broadcast"]["signal_threshold_db"] != 999.0
