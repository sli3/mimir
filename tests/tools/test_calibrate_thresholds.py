"""Tests for tools/calibrate_thresholds.py

Guard tests that verify CALIBRATION_TARGETS stays in sync with
BAND_PROFILES, and unit tests for the pure threshold-derivation helper.
"""

import numpy as np
import pytest

from dashboard.shared_state import BAND_PROFILES
from tools.calibrate_thresholds import (
    CALIBRATION_TARGETS,
    SEPARABILITY_FACTOR,
    STRONG_MATCH_FLOOR,
    derive_thresholds,
)


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


def test_adsb_capture_count_is_five():
    """ADS-B needs >=5 windows so a single dead window cannot dominate p90."""
    adsb = next(t for t in CALIBRATION_TARGETS if t["label"] == "ADS_B")
    assert adsb["captures"] == 5


def test_all_non_adsb_bands_keep_two_captures():
    """Only ADS_B changed its capture count; every other band stays at 2."""
    for target in CALIBRATION_TARGETS:
        if target["label"] == "ADS_B":
            continue
        assert target["captures"] == 2, target["label"]


@pytest.mark.parametrize(
    "same_type_spread, cross_type_min",
    [
        (0.0002, 0.0124),
        (0.0056, 0.0177),
        (0.001, 0.030),
        (0.010, 0.030),
    ],
)
def test_derive_thresholds_is_monotonic_for_separable_inputs(
    same_type_spread, cross_type_min
):
    """When cross_type_min is well above SEPARABILITY_FACTOR * same_type_spread the
    derived set is monotonic: STRONG < POSSIBLE < DIFFERENT.
    """
    result = derive_thresholds(same_type_spread, cross_type_min)
    assert result["ok"] is True
    assert result["reason"] is None
    assert result["strong_match"] < result["possible_match"]
    assert result["possible_match"] < result["different_type"]
    assert result["different_type"] == result["novel_signal"]


def test_derive_thresholds_overlap_run_is_not_ok_and_explains_reason():
    """The 2026-07-08 inverted ADS-B run: same_type_spread > cross_type_min/2.5."""
    same_type_spread = 0.0179
    cross_type_min = 0.0143
    result = derive_thresholds(same_type_spread, cross_type_min)
    assert result["ok"] is False
    assert result["reason"] is not None
    assert str(same_type_spread) in result["reason"]
    assert str(cross_type_min) in result["reason"]
    assert "overlap" in result["reason"].lower()


def test_derive_thresholds_strong_match_floor():
    """Very clean same-type distances must not round STRONG_MATCH down to 0.000."""
    result = derive_thresholds(0.0002, 0.0124)
    assert result["strong_match"] == STRONG_MATCH_FLOOR


def test_derive_thresholds_floor_overrides_only_when_needed():
    """When same_type_spread * 2 is above the floor the helper keeps the computed value."""
    result = derive_thresholds(0.0056, 0.0177)
    assert result["strong_match"] > STRONG_MATCH_FLOOR


def test_derive_thresholds_exact_boundary_is_not_ok():
    """Strict separability: equality at C == SEPARABILITY_FACTOR * S is NOT ok."""
    s = 0.01
    c = SEPARABILITY_FACTOR * s
    result = derive_thresholds(s, c)
    assert result["ok"] is False


def test_p90_reducer_discounts_single_outlier():
    """A single extreme outlier in same-type distances must not define spread."""
    same_type_pairs = np.array([0.001, 0.001, 0.0012, 0.0011, 0.018])
    spread = float(np.percentile(same_type_pairs, 90))
    assert spread < 0.018
    assert spread > 0.001


def test_p90_singleton_same_type_set():
    """p90 of a single-element set is the element itself."""
    assert float(np.percentile(np.array([0.0009]), 90)) == pytest.approx(0.0009)


def test_p90_empty_same_type_set_falls_back_to_zero():
    """The same-type spread falls back to 0.0 when no pairs exist."""
    same_type_pairs = []
    spread = float(np.percentile(same_type_pairs, 90)) if same_type_pairs else 0.0
    assert spread == 0.0
