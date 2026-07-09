"""Tests for tools/calibrate_thresholds.py

Guard tests that verify CALIBRATION_TARGETS stays in sync with
BAND_PROFILES, and unit tests for the pure threshold-derivation helper and
cross-session merge helpers.
"""

from datetime import datetime, timedelta

import numpy as np
import pytest

from dashboard.shared_state import BAND_PROFILES
from embeddings.store import SignalStore
from tools.calibrate_thresholds import (
    CALIBRATION_TARGETS,
    CROSS_TYPE_MIN_FLOOR,
    SEPARABILITY_FACTOR,
    STALENESS_DAYS,
    STRONG_MATCH_FLOOR,
    _compute_band_freshness,
    _find_cross_type_min_pair,
    _merge_stored_entries,
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


def test_derive_thresholds_near_noise_run_fails_on_floor():
    """The 2026-07-08 degenerate live run: cross_type_min collapsed into the
    noise floor (0.0005). The ratio gate passes by coincidence (0.0005 > 2.5 *
    0.0001) but the absolute floor must reject it — this is the run that
    previously slipped through and emitted 0.000 thresholds.
    """
    result = derive_thresholds(0.0001, 0.0005)
    assert result["ok"] is False
    assert result["reason"] is not None
    assert "CROSS_TYPE_MIN_FLOOR" in result["reason"]


def test_derive_thresholds_floor_fails_even_when_ratio_passes():
    """Floor is independent of the ratio: a run can satisfy
    cross > SEPARABILITY_FACTOR * same yet still fail because cross is below
    the absolute floor. Guards against the floor being short-circuited by the
    ratio check.
    """
    same, cross = 0.0001, 0.0040
    assert cross > SEPARABILITY_FACTOR * same  # ratio alone would pass
    result = derive_thresholds(same, cross)
    assert result["ok"] is False
    assert "CROSS_TYPE_MIN_FLOOR" in result["reason"]


def test_derive_thresholds_at_cross_type_min_floor_is_ok():
    """A run with cross exactly at the floor (and a clean same-type spread)
    passes: the floor uses >=, so the boundary value is acceptable.
    """
    result = derive_thresholds(0.0010, CROSS_TYPE_MIN_FLOOR)
    assert result["ok"] is True
    assert result["reason"] is None


def test_derive_thresholds_floor_and_overlap_reasons_are_distinct():
    """A near-noise (floor) failure and an overlap (ratio) failure must produce
    different reason strings, so the operator can tell a dead capture from
    genuinely overlapping classes.
    """
    floor_fail = derive_thresholds(0.0001, 0.0005)
    overlap_fail = derive_thresholds(0.0179, 0.0143)
    assert floor_fail["ok"] is False
    assert overlap_fail["ok"] is False
    assert floor_fail["reason"] != overlap_fail["reason"]
    assert "CROSS_TYPE_MIN_FLOOR" in floor_fail["reason"]
    assert "overlap" in overlap_fail["reason"].lower()


# ---------------------------------------------------------------------------
# Cross-type min pair reporting tests
# ---------------------------------------------------------------------------

def test_find_cross_type_min_pair_reports_actual_minimum():
    """The reported pair must be the cross-type pair with the smallest distance."""
    distance_pairs = [
        ("a1", "b1", 0.05),
        ("a2", "b2", 0.02),
        ("a3", "a4", 0.01),
        ("a5", "n1", 0.001),
    ]
    entry_labels = {
        "a1": "FM_broadcast",
        "b1": "Aviation_VHF",
        "a2": "FM_broadcast",
        "b2": "ACARS",
        "a3": "ADS_B",
        "a4": "ADS_B",
        "a5": "FM_broadcast",
        "n1": "noise_floor",
    }
    cross_type_min, pair = _find_cross_type_min_pair(distance_pairs, entry_labels)
    assert cross_type_min == pytest.approx(0.02)
    assert pair == ("FM_broadcast", "ACARS")


# ---------------------------------------------------------------------------
# Staleness helper tests
# ---------------------------------------------------------------------------

def _freshness_stored(timestamp: str) -> dict:
    return {
        "ids": ["r1"],
        "embeddings": [[0.1]],
        "metadatas": [{"label": "FM_broadcast", "timestamp": timestamp}],
    }


def test_compute_band_freshness_fresh_record():
    """A record newer than STALENESS_DAYS is FRESH."""
    now = datetime.now()
    ts = (now - timedelta(days=STALENESS_DAYS - 1)).isoformat()
    freshness = _compute_band_freshness(_freshness_stored(ts), reference=now)
    assert freshness["FM_broadcast"][0] is True


def test_compute_band_freshness_stale_record():
    """A record older than STALENESS_DAYS is STALE."""
    now = datetime.now()
    ts = (now - timedelta(days=STALENESS_DAYS + 1)).isoformat()
    freshness = _compute_band_freshness(_freshness_stored(ts), reference=now)
    assert freshness["FM_broadcast"][0] is False


def test_compute_band_freshness_boundary_is_fresh():
    """A record exactly STALENESS_DAYS old is treated as FRESH (<= cutoff)."""
    now = datetime.now()
    ts = (now - timedelta(days=STALENESS_DAYS)).isoformat()
    freshness = _compute_band_freshness(_freshness_stored(ts), reference=now)
    assert freshness["FM_broadcast"][0] is True


def test_compute_band_freshness_malformed_timestamp_is_stale():
    """Malformed timestamps are ignored; the band is treated as stale/missing."""
    now = datetime.now()
    stored = {
        "ids": ["r1"],
        "embeddings": [[0.1]],
        "metadatas": [{"label": "FM_broadcast", "timestamp": "not-a-timestamp"}],
    }
    freshness = _compute_band_freshness(stored, reference=now)
    assert "FM_broadcast" not in freshness


def test_compute_band_freshness_missing_timestamp_is_stale():
    """Missing timestamps are ignored; the band is treated as stale/missing."""
    now = datetime.now()
    stored = {
        "ids": ["r1"],
        "embeddings": [[0.1]],
        "metadatas": [{"label": "FM_broadcast"}],
    }
    freshness = _compute_band_freshness(stored, reference=now)
    assert "FM_broadcast" not in freshness


# ---------------------------------------------------------------------------
# Merge assembly tests
# ---------------------------------------------------------------------------

def test_merge_stored_entries_includes_fresh_non_captured_and_excludes_stale():
    """Fresh stored bands not captured this run are merged; stale ones are not."""
    store = SignalStore(path=":memory:")
    now = datetime.now()

    # Fresh non-captured band.
    store.add({
        "id": "fresh_fm",
        "embedding": [0.1, 0.2],
        "label": "FM_broadcast",
        "metadata": {
            "label": "FM_broadcast",
            "timestamp": now.isoformat(),
        },
    })

    # Stale non-captured band.
    stale_ts = (now - timedelta(days=STALENESS_DAYS + 1)).isoformat()
    store.add({
        "id": "stale_aviation",
        "embedding": [0.3, 0.4],
        "label": "Aviation_VHF",
        "metadata": {
            "label": "Aviation_VHF",
            "timestamp": stale_ts,
        },
    })

    # Captured band (fresh vectors already in entries).
    store.add({
        "id": "fresh_adsb",
        "embedding": [0.5, 0.6],
        "label": "ADS_B",
        "metadata": {
            "label": "ADS_B",
            "timestamp": now.isoformat(),
        },
    })

    freshness = _compute_band_freshness(store.get_all_embeddings())
    entries = [{"id": "new_adsb", "label": "ADS_B", "embedding": [0.9, 0.9]}]
    merged = _merge_stored_entries(entries, store, freshness, {"ADS_B"})

    labels = {e["label"] for e in merged}
    assert "FM_broadcast" in labels
    assert "Aviation_VHF" not in labels
    assert "ADS_B" in labels
    assert len(merged) == 2
    store.delete_collection()


def test_merge_stored_entries_empty_when_all_captured_or_stale():
    """When no stored bands are fresh and non-captured, merge adds nothing."""
    store = SignalStore(path=":memory:")
    now = datetime.now()
    stale_ts = (now - timedelta(days=STALENESS_DAYS + 1)).isoformat()
    store.add({
        "id": "stale_fm",
        "embedding": [0.1, 0.2],
        "label": "FM_broadcast",
        "metadata": {"label": "FM_broadcast", "timestamp": stale_ts},
    })

    freshness = _compute_band_freshness(store.get_all_embeddings())
    entries = [{"id": "new_fm", "label": "FM_broadcast", "embedding": [0.9, 0.9]}]
    merged = _merge_stored_entries(entries, store, freshness, {"FM_broadcast"})

    assert len(merged) == 1
    store.delete_collection()
