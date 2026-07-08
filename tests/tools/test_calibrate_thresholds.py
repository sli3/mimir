"""
Tests for tools/calibrate_thresholds.py

Guard tests that verify CALIBRATION_TARGETS stays in sync with
BAND_PROFILES.
"""

import pytest

from dashboard.shared_state import BAND_PROFILES
from tools.calibrate_thresholds import CALIBRATION_TARGETS


LABEL_TO_KEY = {
    "FM_broadcast": "fm_broadcast",
    "Aviation_VHF": "aviation",
    "ACARS": "acars",
    "APRS": "aprs",
    "AIS": "ais",
    "ISM_LoRa": "ism",
    "ADS_B": "adsb",
    "noise_floor": "noise_floor",
}


def test_calibration_targets_match_band_profiles():
    for target in CALIBRATION_TARGETS:
        profile = BAND_PROFILES[LABEL_TO_KEY[target["label"]]]
        assert target["lna_gain_db"] == profile["lna_gain_db"]
        assert target["vga_gain_db"] == profile["vga_gain_db"]
        assert target["signal_threshold_db"] == profile["signal_threshold_db"]


def test_calibration_targets_adsb_only_uses_max_hold():
    """Only the ADS_B calibration target carries the psd_max_hold_db trace key."""
    for target in CALIBRATION_TARGETS:
        if target["label"] == "ADS_B":
            assert target.get("trace_key") == "psd_max_hold_db"
        else:
            assert "trace_key" not in target
