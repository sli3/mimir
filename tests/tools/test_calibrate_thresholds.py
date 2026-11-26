"""Tests for tools/calibrate_thresholds.py

Guard tests that verify CALIBRATION_TARGETS stays in sync with
BAND_PROFILES, unit tests for threshold derivation and cross-session merging,
and hardware-free console, failure and logging workflows.
"""

from datetime import datetime, timedelta
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock, patch

import io
import itertools
import logging
import os
import sys
from types import ModuleType

import numpy as np
import pytest

from dashboard.shared_state import BAND_PROFILES
from embeddings.store import SignalStore
from tools import _console, calibrate_thresholds
from tools._console import Spinner
from tools.calibrate_thresholds import (
    CALIBRATION_TARGETS,
    CROSS_TYPE_MIN_FLOOR,
    SEPARABILITY_FACTOR,
    STALENESS_DAYS,
    STRONG_MATCH_FLOOR,
    _classify_distance_pairs,
    _compute_band_freshness,
    _compute_pairwise_distances,
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


@pytest.fixture(autouse=True)
def restore_console_logging() -> Iterator[None]:
    """Restore pytest's handlers and logger levels after CLI logging setup."""
    root = logging.getLogger()
    handlers, root_level = root.handlers[:], root.level
    names = (
        calibrate_thresholds.__name__, "core", "embeddings", "llm", "tools",
        "chromadb",
    )
    levels = {name: logging.getLogger(name).level for name in names}
    try:
        yield
    finally:
        for handler in root.handlers[:]:
            root.removeHandler(handler)
        for handler in handlers:
            root.addHandler(handler)
        root.setLevel(root_level)
        for name, level in levels.items():
            logging.getLogger(name).setLevel(level)


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


def test_classify_distance_pairs_partitions_all_three_buckets():
    """Step G in main() prints len(cross_type_pairs); the helper must actually
    build the cross-type list. Regression guard for the NameError that shipped
    when the cross-type branch was dropped from the inline loop in main().

    The (n1, n2) pair is same-type under the original loop's `is_same_type =
    a_label == b_label` rule (both endpoints are "noise_floor") and therefore
    lands in same_type_pairs, NOT noise_pairs. noise_pairs only catches pairs
    where exactly one endpoint is noise_floor.
    """
    distance_pairs = [
        ("fm1", "fm2", 0.0010),
        ("fm1", "av1", 0.0340),
        ("ac1", "fm1", 0.0280),
        ("ac1", "ac2", 0.0012),
        ("fm1", "n1",  0.0500),
        ("n1",  "n2",  0.0400),
        ("av1", "ap1", 0.0410),
    ]
    entry_labels = {
        "fm1": "FM_broadcast", "fm2": "FM_broadcast",
        "av1": "Aviation_VHF",
        "ac1": "ACARS",        "ac2": "ACARS",
        "ap1": "APRS",
        "n1":  "noise_floor",  "n2":  "noise_floor",
    }

    same_type_pairs, cross_type_pairs, noise_pairs = _classify_distance_pairs(
        distance_pairs, entry_labels
    )

    assert same_type_pairs == [0.0010, 0.0012, 0.0400]
    assert cross_type_pairs == [0.0340, 0.0280, 0.0410]
    assert noise_pairs == [0.0500]


def test_classify_distance_pairs_handles_all_same_type():
    """All-same-type input must leave the cross-type and noise lists empty."""
    distance_pairs = [("a1", "a2", 0.01), ("a3", "a4", 0.02)]
    entry_labels = {"a1": "ADS_B", "a2": "ADS_B", "a3": "ADS_B", "a4": "ADS_B"}

    same_type_pairs, cross_type_pairs, noise_pairs = _classify_distance_pairs(
        distance_pairs, entry_labels
    )

    assert same_type_pairs == [0.01, 0.02]
    assert cross_type_pairs == []
    assert noise_pairs == []


def test_classify_distance_pairs_handles_empty_input():
    """Empty input must not raise and must return three empty lists."""
    same_type_pairs, cross_type_pairs, noise_pairs = _classify_distance_pairs([], {})

    assert same_type_pairs == []
    assert cross_type_pairs == []
    assert noise_pairs == []


def test_classify_distance_pairs_noise_floor_partner_excludes_cross_type():
    """A pair where one endpoint is noise_floor is NOT a cross-type pair,
    even though its two labels differ. Confirms the noise check is applied
    before the cross-type classification in the if/elif chain.
    """
    distance_pairs = [("fm1", "n1", 0.07)]
    entry_labels = {"fm1": "FM_broadcast", "n1": "noise_floor"}

    same_type_pairs, cross_type_pairs, noise_pairs = _classify_distance_pairs(
        distance_pairs, entry_labels
    )

    assert same_type_pairs == []
    assert cross_type_pairs == []
    assert noise_pairs == [0.07]


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


@pytest.mark.parametrize("device", ["hackrf", "pluto"])
@pytest.mark.parametrize("stale", [False, True])
@pytest.mark.parametrize(
    "outcome", ["all_fail", "partial_fail", "success", "interrupted"],
)
def test_band_replacement_requires_every_capture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
    device: str,
    stale: bool,
    outcome: str,
) -> None:
    """Replace only complete bands and preserve each device after failures.

    The first failure stops the band, retains fresh or stale priors and exits
    before merging when no band completes. Interrupts still propagate before
    replacement takes place.
    """
    label = "FM_broadcast"
    target = dict(next(t for t in CALIBRATION_TARGETS if t["label"] == label))
    target.update(captures=2, num_samples=8, gain_db=20.0)
    timestamp = (
        datetime.now() - timedelta(days=STALENESS_DAYS + 1 if stale else 0)
    ).isoformat()
    store = SignalStore(str(tmp_path))
    prior = []
    for idx in range(3):
        metadata = {"label": label, "timestamp": timestamp, "device": device}
        if device == "hackrf" and idx == 0:
            del metadata["device"]  # Legacy records belong to HackRF.
        prior.append({
            "id": f"{label}_{device}_{idx}",
            "embedding": [0.1] * 7,
            "metadata": metadata,
        })
    other = {
        "id": "other_device",
        "embedding": [0.2] * 7,
        "metadata": {
            "label": label,
            "device": "pluto" if device == "hackrf" else "hackrf",
            "timestamp": datetime.now().isoformat(),
        },
    }
    store.add_batch([*prior, other])
    before = store.get_all_embeddings()
    store._collection = MagicMock(wraps=store._collection)
    samples = np.ones(8, dtype=np.complex64)
    outcomes = {
        "all_fail": [RuntimeError("failed"), RuntimeError("failed")],
        "partial_fail": [samples, RuntimeError("capture failed")],
        "success": [samples, samples],
        "interrupted": [samples, KeyboardInterrupt()],
    }
    monkeypatch.setattr(
        "sys.argv", ["calibrate_thresholds.py", "--device", device],
    )
    monkeypatch.setattr("builtins.input", lambda _prompt: "")
    profiles = {
        "1": {"name": "Test antenna", "range": "test", "bands": [label]},
        "3": {"name": "Other antenna", "range": "test", "bands": []},
    }
    with (
        patch.object(calibrate_thresholds, "Path", return_value=tmp_path),
        patch.object(calibrate_thresholds, "SignalStore", return_value=store),
        patch.object(calibrate_thresholds, "CALIBRATION_TARGETS", [target]),
        patch.object(calibrate_thresholds, "ANTENNA_PROFILES", profiles),
        patch.object(
            calibrate_thresholds, "_build_pluto_calibration_targets",
            return_value=[target],
        ),
        patch.object(
            calibrate_thresholds, "_prompt_recapture_fresh_bands",
            return_value={label},
        ),
        patch.object(calibrate_thresholds, "time"),
        patch.object(
            calibrate_thresholds,
            "capture_iq_pluto" if device == "pluto" else "capture_iq",
            side_effect=outcomes[outcome],
        ) as capture,
        patch.object(calibrate_thresholds, "compute_psd", return_value={}),
        patch.object(
            calibrate_thresholds, "fingerprint_spectrum", return_value={
                "peak_power_db": -30.0, "snr_db": 12.0,
            },
        ),
        patch.object(calibrate_thresholds, "SpectrumEmbedder") as embedder,
        patch.object(store, "add_batch", wraps=store.add_batch) as add_batch,
        patch.object(store, "add", wraps=store.add) as add,
        patch.object(
            calibrate_thresholds, "_merge_stored_entries",
            wraps=_merge_stored_entries,
        ) as merge,
        patch.object(
            calibrate_thresholds, "_compute_pairwise_distances", return_value=[],
        ),
        patch.object(calibrate_thresholds, "_print_matrix"),
    ):
        embedder.return_value.embed.return_value = [0.8] * 7
        calls = MagicMock()
        calls.attach_mock(store._collection.delete, "delete")
        calls.attach_mock(add_batch, "add_batch")
        if outcome == "interrupted":
            with pytest.raises(KeyboardInterrupt):
                calibrate_thresholds.main()
            merge.assert_not_called()
        elif outcome != "success":
            with pytest.raises(SystemExit) as exc:
                calibrate_thresholds.main()
            assert exc.value.code == 1
            merge.assert_not_called()
        else:
            calibrate_thresholds.main()

        add.assert_not_called()
        assert capture.call_count == (1 if outcome == "all_fail" else 2)
        if outcome == "success":
            assert [call[0] for call in calls.mock_calls] == [
                "delete", "add_batch",
            ]
            add_batch.assert_called_once()
            assert len(add_batch.call_args.args[0]) == target["captures"]
        else:
            store._collection.delete.assert_not_called()
            add_batch.assert_not_called()
        if outcome == "success":
            merged_entries, _, _, captured_bands = merge.call_args.args
            assert captured_bands == {label}
            expected_ids = {f"{label}_{device}_{idx}" for idx in range(2)}
            assert {entry["id"] for entry in merged_entries} == expected_ids

    after = store.get_all_embeddings()
    records_after = {
        rec_id: (vec, meta)
        for rec_id, vec, meta in zip(
            after["ids"], after["embeddings"], after["metadatas"],
        )
    }
    before_records = {
        rec_id: (vec, meta)
        for rec_id, vec, meta in zip(
            before["ids"], before["embeddings"], before["metadatas"],
        )
    }
    assert records_after[other["id"]] == before_records[other["id"]]
    if outcome == "success":
        assert len(after["ids"]) == target["captures"] + 1
        assert len(after["ids"]) == len(set(after["ids"]))
        for idx in range(2):
            np.testing.assert_allclose(
                records_after[f"{label}_{device}_{idx}"][0], [0.8] * 7,
            )
    else:
        assert records_after == before_records
        if outcome != "interrupted":
            output = capsys.readouterr().out
            assert "Kept 3 prior" in output
            assert "no new records were stored" in output
            assert "stale prior set is still excluded" in output


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


# ---------------------------------------------------------------------------
# Pairwise distance computation tests (Phase 77)
# ---------------------------------------------------------------------------

def test_pair_query_is_not_silently_dropped_when_partner_is_outside_top_k(tmp_path):
    """Phase 77 regression test.

    When the store has more records than `entries`, the partner for a pair
    could previously fall outside the truncated top-K returned by
    store.query(n_results=len(entries)) and the pair was silently dropped.
    After the fix, n_results = store.count() so the partner is always in
    the neighbour list and the pair is always computed.
    """
    store = SignalStore(path=":memory:")

    # 2 entries (a, b), so pair (a, b) is the only combination.
    # The 18 noise records are placed deliberately close to a's embedding so
    # they crowd the top of the nearest-neighbour ranking, pushing b
    # outside the top-2 (which is what the OLD buggy code would have
    # asked for: n_results=len(entries)=2).
    a_vec = [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    b_vec = [1.0, 0.1, 0.0, 0.0, 0.0, 0.0, 0.0]  # close to a but not identical
    entries = [
        {"id": "a", "label": "X", "embedding": a_vec},
        {"id": "b", "label": "X", "embedding": b_vec},
    ]

    store.add({"id": "a", "embedding": a_vec,
               "metadata": {"label": "X", "device": "hackrf"}})
    store.add({"id": "b", "embedding": b_vec,
               "metadata": {"label": "X", "device": "hackrf"}})

    # Add 18 noise records close to a, all distinct IDs, all with the same
    # embedding so they are tied at a small distance from a. With
    # n_results=2 (old buggy behaviour), only a + 1 noise record are returned,
    # and b is excluded. With n_results=store.count() (the fix), all 20 records
    # are returned and b is found.
    for i in range(18):
        store.add({"id": f"noise_{i}", "embedding": [0.95, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                   "metadata": {"label": "noise_floor", "device": "hackrf"}})

    pairs = _compute_pairwise_distances(entries, store)

    assert len(pairs) == 1, "exactly one pair (a, b) should be computed"
    a_id, b_id, dist = pairs[0]
    assert (a_id, b_id) == ("a", "b")
    assert dist is not None
    assert isinstance(dist, float)
    assert dist > 0  # a and b are not identical

    store.delete_collection()


def test_pair_count_unaffected_by_off_device_records_in_store(tmp_path):
    """Off-device records in the store must not push any active pair out of the neighbour list."""
    store = SignalStore(path=":memory:")

    # 3 active entries, all hackrf.
    active = [
        {"id": "h1", "label": "X", "embedding": [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]},
        {"id": "h2", "label": "X", "embedding": [0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0]},
        {"id": "h3", "label": "X", "embedding": [0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0]},
    ]
    for entry in active:
        store.add({"id": entry["id"], "embedding": entry["embedding"],
                   "metadata": {"label": "X", "device": "hackrf"}})

    # Add 30 Pluto records with embeddings closer to h1 than h2/h3 are,
    # so under the OLD buggy n_results=3 they would crowd h2 and h3 out
    # of the top-3 neighbours of h1.
    for i in range(30):
        store.add({"id": f"pluto_{i}", "embedding": [0.99, 0.01, 0.0, 0.0, 0.0, 0.0, 0.0],
                   "metadata": {"label": "X", "device": "plutosdr"}})

    pairs = _compute_pairwise_distances(active, store)
    pair_set = {(a, b) for a, b, _ in pairs}

    # C(3, 2) = 3 pairs expected, all computed.
    expected = {("h1", "h2"), ("h1", "h3"), ("h2", "h3")}
    assert pair_set == expected, (
        f"all 3 pairs must be computed regardless of off-device store records; "
        f"got {pair_set}"
    )

    store.delete_collection()


def test_pair_count_is_n_choose_2_with_no_drops(tmp_path):
    """For N entries, exactly N*(N-1)/2 pairs are computed (no drops)."""
    store = SignalStore(path=":memory:")

    # 5 entries, all hackrf, all distinct IDs.
    n = 5
    entries = [
        {"id": f"e{i}", "label": "X",
         "embedding": [float(i == j) for j in range(7)]}  # one-hot in 7D
        for i in range(n)
    ]
    for entry in entries:
        store.add({"id": entry["id"], "embedding": entry["embedding"],
                   "metadata": {"label": "X", "device": "hackrf"}})

    # Add 20 noise records to make the store larger than entries
    # (exercising the truncation scenario).
    for i in range(20):
        store.add({"id": f"noise_{i}",
                   "embedding": [0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5],
                   "metadata": {"label": "noise_floor", "device": "hackrf"}})

    pairs = _compute_pairwise_distances(entries, store)

    assert len(pairs) == n * (n - 1) // 2  # 10 pairs, no drops
    assert all(dist is not None for _, _, dist in pairs)
    # Distances must be positive (distinct one-hots give positive L2).
    assert all(dist > 0 for _, _, dist in pairs)

    store.delete_collection()


def test_missing_pair_in_store_logs_error_with_diagnostic_info(tmp_path, caplog):
    """If a partner ID is genuinely missing from the store (a real bug),
    the helper's logger emits an ERROR with store.count() and n_results so the
    cause is diagnosable from the log line alone, and the pair is dropped.
    """
    store = SignalStore(path=":memory:")
    a_vec = [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    # 'entries' contains an ID that was NEVER added to the store, a real
    # bug scenario. The fix makes the helper detect and log this loudly.
    entries = [
        {"id": "in_store", "label": "X", "embedding": a_vec},
        {"id": "missing", "label": "X", "embedding": [0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0]},
    ]
    store.add({"id": "in_store", "embedding": a_vec,
               "metadata": {"label": "X", "device": "hackrf"}})

    with caplog.at_level(logging.ERROR, logger="tools.calibrate_thresholds"):
        pairs = _compute_pairwise_distances(entries, store)

    assert len(pairs) == 0  # pair dropped
    # Third-party loggers such as ChromaDB telemetry can emit unrelated errors.
    error_records = [
        r for r in caplog.records
        if r.levelno == logging.ERROR and r.name == "tools.calibrate_thresholds"
    ]
    assert len(error_records) == 1
    msg = error_records[0].getMessage()
    assert "in_store" in msg and "missing" in msg
    assert "n_results=" in msg or "n_results = " in msg  # diagnostic context
    assert "store has" in msg or "store size" in msg.lower()

    store.delete_collection()


def _prin_run() -> tuple[list[dict], list[tuple[str, str, float]]]:
    """Model five tight ADS-B captures and a LoRa capture close to ADS-B."""
    entries = [
        {"id": f"ADS_B_pluto_{index}", "label": "ADS_B"}
        for index in range(5)
    ] + [
        {"id": f"ISM_LoRa_pluto_{index}", "label": "ISM_LoRa"}
        for index in range(2)
    ]
    pairs = []
    for a, b in itertools.combinations(entries, 2):
        if a["label"] == b["label"] == "ADS_B":
            distance = 0.001
        elif a["label"] == b["label"]:
            distance = 0.786
        elif b["id"] == "ISM_LoRa_pluto_1":
            distance = 0.013 + int(a["id"].rsplit("_", 1)[1]) * 0.00125
        else:
            distance = 0.8
        pairs.append((a["id"], b["id"], distance))
    return entries, pairs


def test_find_misplaced_captures_prin_run() -> None:
    """Catch the misplaced LoRa window despite a usable p90 ladder."""
    entries, pairs = _prin_run()
    before = [dict(entry) for entry in entries], list(pairs)
    assert calibrate_thresholds._find_misplaced_captures(entries, pairs) == [{
        "id": "ISM_LoRa_pluto_1", "label": "ISM_LoRa",
        "nearest_other_id": "ADS_B_pluto_0", "nearest_other_label": "ADS_B",
        "own_distance": 0.786, "other_distance": 0.013,
    }]
    assert (entries, pairs) == before


@pytest.mark.parametrize("other_distance", [0.01, 0.05, 0.1])
def test_find_misplaced_captures_noise_and_ties(other_distance: float) -> None:
    """Include noise_floor neighbours and require a strictly smaller gap."""
    entries = [
        {"id": "a1", "label": "ADS_B"},
        {"id": "a2", "label": "ADS_B"},
        {"id": "n", "label": "noise_floor"},
    ]
    pairs = [("a1", "a2", 0.05), ("n", "a1", other_distance), ("a2", "n", 0.1)]
    found = calibrate_thresholds._find_misplaced_captures(entries, pairs)
    if other_distance < 0.05:
        assert found == [{
            "id": "a1", "label": "ADS_B", "nearest_other_id": "n",
            "nearest_other_label": "noise_floor", "own_distance": 0.05,
            "other_distance": other_distance,
        }]
    else:
        assert found == []


def test_find_misplaced_captures_single_entry() -> None:
    """Skip singleton bands even beside a neighbour with another label."""
    entries = [
        {"id": "a", "label": "ADS_B"},
        {"id": "b", "label": "ISM_LoRa"},
        {"id": "c", "label": "ISM_LoRa"},
    ]
    assert calibrate_thresholds._find_misplaced_captures(
        entries, [("a", "b", 0.01), ("a", "c", 0.02), ("b", "c", 0.001)]
    ) == []


def test_find_misplaced_captures_clean() -> None:
    """Tight bands with distant cross-label neighbours produce no warnings."""
    entries, pairs = _prin_run()
    pairs = [
        (a, b, 0.001 if a.split("_pluto")[0] == b.split("_pluto")[0] else 0.2)
        for a, b, _ in pairs
    ]
    assert calibrate_thresholds._find_misplaced_captures(entries, pairs) == []


@pytest.fixture
def console_calibration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> dict[str, MagicMock]:
    """Prepare a full CLI run with both capture paths and storage stubbed.

    Capture paths, storage and log setup are stubbed, with an 80-column
    terminal. The store path is temporary; real reporting and derivation run.
    """
    targets = [
        dict(target, gain_db=20.0, num_samples=8)
        for target in CALIBRATION_TARGETS
        if target["label"] in {"ADS_B", "ISM_LoRa"}
    ]
    _, pairs = _prin_run()
    clean_pairs = [
        (a, b, 0.001 if a.split("_pluto")[0] == b.split("_pluto")[0] else 0.2)
        for a, b, _ in pairs
    ]
    store = MagicMock()
    store.get_all_embeddings.return_value = {
        "ids": [], "metadatas": [], "embeddings": [],
    }
    embedder = MagicMock()
    embedder.embed.return_value = [0.1] * 7
    mocks = {
        "capture": MagicMock(return_value=np.ones(8, dtype=np.complex64)),
        "matrix": MagicMock(wraps=calibrate_thresholds._print_matrix),
        "distances": MagicMock(return_value=clean_pairs),
        "derive": MagicMock(wraps=derive_thresholds),
        "store": store,
        "input": MagicMock(return_value=""),
        "fingerprint": MagicMock(return_value={
            "peak_power_db": -73.30, "snr_db": 14.99,
        }),
    }
    monkeypatch.setattr(
        calibrate_thresholds, "_quiet_soapy_info_logs", MagicMock()
    )
    monkeypatch.setattr(
        _console.shutil, "get_terminal_size",
        lambda **_: os.terminal_size((80, 24)),
    )
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr(
        "sys.argv", ["calibrate_thresholds.py", "--device", "pluto"]
    )
    monkeypatch.setattr("builtins.input", mocks["input"])
    monkeypatch.setattr(
        calibrate_thresholds, "Path", MagicMock(return_value=tmp_path)
    )
    monkeypatch.setattr(
        calibrate_thresholds, "SignalStore", MagicMock(return_value=store)
    )
    monkeypatch.setattr(
        calibrate_thresholds, "SpectrumEmbedder", MagicMock(return_value=embedder)
    )
    monkeypatch.setattr(
        calibrate_thresholds, "_build_pluto_calibration_targets",
        MagicMock(return_value=targets),
    )
    monkeypatch.setattr(calibrate_thresholds, "capture_iq", mocks["capture"])
    monkeypatch.setattr(calibrate_thresholds, "capture_iq_pluto", mocks["capture"])
    monkeypatch.setattr(
        calibrate_thresholds, "compute_psd", MagicMock(return_value={})
    )
    monkeypatch.setattr(
        calibrate_thresholds, "fingerprint_spectrum", mocks["fingerprint"],
    )
    monkeypatch.setattr(calibrate_thresholds, "time", MagicMock())
    monkeypatch.setattr(calibrate_thresholds, "_print_matrix", mocks["matrix"])
    monkeypatch.setattr(
        calibrate_thresholds, "_compute_pairwise_distances", mocks["distances"]
    )
    monkeypatch.setattr(
        calibrate_thresholds, "derive_thresholds", mocks["derive"]
    )
    return mocks


@pytest.mark.parametrize("verbose", [False, True])
def test_console_verbose_and_default(
    console_calibration: dict[str, MagicMock], monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str], verbose: bool,
) -> None:
    """Keep piped logs readable and gate diagnostics without changing maths."""
    argv = ["calibrate_thresholds.py", "--device", "pluto"]
    monkeypatch.setattr("sys.argv", argv + (["--verbose"] if verbose else []))
    calibrate_thresholds.main()
    output = capsys.readouterr().out
    assert "\x1b" not in output
    assert "\r" not in output
    assert ("PAIRWISE DISTANCE MATRIX" in output) is verbose
    assert ("Computed statistics:" in output) is verbose
    assert ("same_type_pairs:" in output) is verbose
    assert ("Cross-type min distance:" in output) is verbose
    assert console_calibration["matrix"].call_count == int(verbose)
    assert console_calibration["derive"].call_count == 2
    assert all(
        call.args == pytest.approx((0.001, 0.2))
        for call in console_calibration["derive"].call_args_list
    )
    assert console_calibration["capture"].call_count == 7
    assert "✓ usable" in output
    assert any(
        line[3:-3].split() == ["ADS_B", "5", "0.0010", "✓", "consistent"]
        for line in output.splitlines() if line.startswith("│")
    )
    assert "✓ capture 1/5 · peak -73.30 dB · SNR 14.99 dB" in output
    assert "[1/2] ADS_B · 1090.000 MHz" in output
    assert "Telescopic whip, retracted to ~68 mm" in output
    for name, value in [
        ("STRONG_MATCH", "0.002"), ("POSSIBLE_MATCH", "0.101"),
        ("DIFFERENT_TYPE", "0.180"), ("NOVEL_SIGNAL", "0.180"),
    ]:
        assert any(
            line[3:-3].split()[:2] == [name, value]
            for line in output.splitlines() if line.startswith("│")
        )
    assert "not safe to apply" not in output
    assert "_DISTANCE_SCALE_REFERENCE" in output
    assert "_build_user_prompt() threshold block" in output
    assert "~line" not in output
    assert output.rstrip().endswith(
        "→ Next: copy the values into llm/classifier.py"
    )


@pytest.mark.parametrize("verbose", [False, True])
def test_console_misplaced_verdict(
    console_calibration: dict[str, MagicMock], monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str], verbose: bool,
) -> None:
    """Warn against applying a usable ladder affected by misplaced captures."""
    _, pairs = _prin_run()
    console_calibration["distances"].return_value = pairs
    monkeypatch.setattr("sys.argv", [
        "calibrate_thresholds.py", "--device", "pluto",
        *(["--verbose"] if verbose else []),
    ])
    calibrate_thresholds.main()
    output = capsys.readouterr().out
    assert "\x1b" not in output
    assert "\r" not in output
    assert "✓ usable" not in output
    assert "⚠ usable but affected by misplaced captures" in output
    assert any(
        line[3:-3].split() == [
            "ISM_LoRa", "2", "0.7860", "⚠", "captures", "disagree",
        ]
        for line in output.splitlines() if line.startswith("│")
    )
    assert (
        "ISM_LoRa_pluto_1 looks like ADS_B (0.013 away, own band 0.786)"
    ) in output
    assert "Suggested thresholds · not safe to apply" in output
    assert (
        "→ Next: recapture ISM_LoRa. Leave llm/classifier.py unchanged."
    ) in output


def test_console_failed_thresholds(
    console_calibration: dict[str, MagicMock],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Print remediation and the next step before exiting 1 on failure."""
    pairs = console_calibration["distances"].return_value
    console_calibration["distances"].return_value = [
        (a, b, 0.0001) for a, b, _ in pairs
    ]
    with pytest.raises(SystemExit) as exc:
        calibrate_thresholds.main()
    assert exc.value.code == 1
    output = capsys.readouterr().out
    assert "✗ failed" in output
    assert "CROSS_TYPE_MIN_FLOOR" in output
    assert "REMEDIATION:" in output
    assert "Suggested thresholds" not in output
    assert output.rstrip().endswith(
        "→ Next: recapture with a live signal present"
    )


def test_console_singleton_and_noise_warning(
    console_calibration: dict[str, MagicMock], monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Singletons are unchecked and noise neighbours are named explicitly."""
    entries = [
        {"id": "a1", "label": "ADS_B"},
        {"id": "a2", "label": "ADS_B"},
        {"id": "n", "label": "noise_floor"},
    ]
    monkeypatch.setattr(
        calibrate_thresholds, "_merge_stored_entries",
        MagicMock(return_value=entries),
    )
    console_calibration["distances"].return_value = [
        ("a1", "a2", 0.05), ("a1", "n", 0.01), ("a2", "n", 0.1),
    ]
    calibrate_thresholds.main()
    output = capsys.readouterr().out
    assert any(
        line[3:-3].split() == [
            "noise_floor", "1", "—", "only", "one", "capture,", "not", "checked",
        ]
        for line in output.splitlines() if line.startswith("│")
    )
    assert "a1 looks like noise_floor (0.010 away, own band 0.050)" in output
    assert "✓ usable" not in output


def test_console_startup_summary(capsys: pytest.CaptureFixture[str]) -> None:
    """Show the Mimir header, aligned fresh/stale status and exclusion text."""
    calibrate_thresholds._print_startup_summary({
        "ADS_B": (True, 0.5, "2026-11-25T12:00:00"),
        "ISM_LoRa": (False, 20.0, "2026-11-05T12:00:00"),
    }, "pluto")
    output = capsys.readouterr().out
    assert "Mimir · calibrate thresholds · pluto" in output
    assert "✓ ADS_B" in output
    assert "fresh · today" in output
    assert "⚠ ISM_LoRa" in output
    assert "stale · 20 days ago (2026-11-05)" in output
    body = " ".join(
        line[3:-3].strip() for line in output.splitlines()
        if line.startswith("│")
    )
    assert "excluded unless recaptured" in body
    assert "\x1b" not in output
    assert "\r" not in output
    calibrate_thresholds._print_startup_summary({}, "hackrf")
    assert "No prior calibration data, starting fresh" in capsys.readouterr().out


@pytest.mark.parametrize("answer", ["", "ADS_B, unknown", None])
def test_console_recapture_prompt(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    answer: str | None,
) -> None:
    """Use short plain recapture text with unchanged validation and skips."""
    response = MagicMock(
        side_effect=KeyboardInterrupt if answer is None else None,
        return_value=answer,
    )
    monkeypatch.setattr("builtins.input", response)
    targets = [t for t in CALIBRATION_TARGETS if t["label"] == "ADS_B"]
    selected = calibrate_thresholds._prompt_recapture_fresh_bands(
        {"ADS_B"}, targets
    )
    assert selected == ({"ADS_B"} if answer else set())
    response.assert_called_once_with("> ")
    output = capsys.readouterr().out
    assert "Fresh within the last 14 days: ADS_B." in output
    assert "Recapture which? ADS_B (comma-separated, Enter to skip)" in output
    assert "╭" not in output


def test_single_band_groups_have_one_prompt(
    console_calibration: dict[str, MagicMock], capsys: pytest.CaptureFixture[str],
) -> None:
    """Each Pluto band card covers connection, length and signal warnings."""
    calibrate_thresholds.main()
    prompts = [call.args[0] for call in console_calibration["input"].call_args_list]
    assert prompts == ["  Enter to start · Ctrl+C to skip this band\n"] * 2
    output = capsys.readouterr().out
    assert "Antenna capture plan" not in output
    assert "Telescopic whip, retracted to ~68 mm" in output
    assert "Aircraft overhead, otherwise only noise" in output
    assert "Live traffic: flightradar24.com" in output
    assert "Samples" in output and "8" in output


def test_band_prompt_interrupt_skips_capture(
    console_calibration: dict[str, MagicMock], monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Keep prompt skips separate from failures and preserve the skip log call."""
    builder = calibrate_thresholds._build_pluto_calibration_targets
    builder.return_value = [
        target for target in builder.return_value if target["label"] == "ADS_B"
    ]
    console_calibration["input"].side_effect = KeyboardInterrupt
    info = MagicMock(wraps=calibrate_thresholds.logger.info)
    monkeypatch.setattr(calibrate_thresholds.logger, "info", info)
    with pytest.raises(SystemExit) as exc:
        calibrate_thresholds.main()
    # The skipped run still exits for insufficient entries.
    assert exc.value.code == 1
    console_calibration["capture"].assert_not_called()
    console_calibration["store"].add_batch.assert_not_called()
    console_calibration["input"].assert_called_once()
    info.assert_any_call("User skipped %s band at antenna length check", "ADS_B")
    assert "No new captures" not in capsys.readouterr().out


@pytest.mark.parametrize("skip_group", [False, True])
def test_multi_band_group_connection_prompt(
    console_calibration: dict[str, MagicMock], monkeypatch: pytest.MonkeyPatch,
    skip_group: bool,
) -> None:
    """Keep one group connection prompt and allow Ctrl+C to skip every band."""
    monkeypatch.setattr(calibrate_thresholds, "ANTENNA_PROFILES", {
        "1": {
            "name": "Test antenna", "range": "test",
            "bands": ["ADS_B", "ISM_LoRa"],
        },
        "3": {"name": "Unused", "range": "test", "bands": []},
    })
    if skip_group:
        console_calibration["input"].side_effect = KeyboardInterrupt
        with pytest.raises(SystemExit) as exc:
            calibrate_thresholds.main()
        assert exc.value.code == 1
        console_calibration["capture"].assert_not_called()
    else:
        calibrate_thresholds.main()
    prompts = [call.args[0] for call in console_calibration["input"].call_args_list]
    assert prompts[0].startswith("Connect Test antenna now.")
    assert len(prompts) == (1 if skip_group else 3)


class CalibrationTTY(io.StringIO):
    """Supply a terminal stream for progress without changing pytest stdout."""

    def isatty(self) -> bool:
        """Enable spinner behaviour without requiring a real terminal."""
        return True


@pytest.mark.parametrize("verbose", [False, True])
def test_tty_capture_summary_and_verbose(
    console_calibration: dict[str, MagicMock], monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str], verbose: bool,
) -> None:
    """Show SNR range summaries and retain capture detail only with verbose."""
    terminal = CalibrationTTY()

    def tty_spinner(label: str = "", total: int = 1) -> Spinner:
        """Run labelled progress on an isolated fake terminal."""
        return Spinner(label=label, total=total, stream=terminal)

    monkeypatch.setattr(calibrate_thresholds, "Spinner", tty_spinner)
    monkeypatch.setattr("sys.argv", [
        "calibrate_thresholds.py", "--device", "pluto",
        *(["--verbose"] if verbose else []),
    ])
    console_calibration["fingerprint"].side_effect = [
        {"peak_power_db": -73.30, "snr_db": snr}
        for snr in [14.6, 18.1, 16.0, 17.0, 15.0, 12.0, 13.0]
    ]
    calibrate_thresholds.main()
    output = capsys.readouterr().out
    assert "✓ 5/5 captured · SNR 14.6 to 18.1 dB" in output
    assert "✓ 2/2 captured · SNR 12.0 to 13.0 dB" in output
    assert ("✓ capture 1/5" in terminal.getvalue()) is verbose
    assert "✓ capture 1/5" not in output
    assert terminal.getvalue().endswith("\r\033[2K")


def test_tty_failed_capture_is_reported(
    console_calibration: dict[str, MagicMock], monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Stop a failed band, report its error above progress and analyse successes."""
    terminal = CalibrationTTY()

    def tty_spinner(label: str = "", total: int = 1) -> Spinner:
        """Isolate labelled progress and explicit messages on a fake terminal."""
        return Spinner(label=label, total=total, stream=terminal)

    monkeypatch.setattr(calibrate_thresholds, "Spinner", tty_spinner)
    samples = console_calibration["capture"].return_value
    console_calibration["capture"].side_effect = [
        RuntimeError("capture unavailable"), samples, samples,
    ]
    console_calibration["distances"].return_value = [
        ("ISM_LoRa_pluto_0", "ISM_LoRa_pluto_1", 0.001),
    ]
    calibrate_thresholds.main()
    assert "✗ capture 1/5 failed" in terminal.getvalue()
    assert "    capture unavailable" in terminal.getvalue()
    assert console_calibration["capture"].call_count == 3
    output = capsys.readouterr().out
    assert "0/5 captured" not in output
    assert "Results" in output
    assert "No new captures" not in output
    assert "Kept 0 prior" in output
    assert "no new records were stored" in output
    assert "stale prior set is still excluded" in output


@pytest.mark.parametrize("setter_name", ["SoapySDR_setLogLevel", "setLogLevel"])
@pytest.mark.parametrize("level", [0, 3])
def test_quiet_soapy_info_logs(
    monkeypatch: pytest.MonkeyPatch, setter_name: str, level: int,
) -> None:
    """Use either log binding and its warning level without device APIs."""
    module = ModuleType("SoapySDR")
    setter = MagicMock()
    setattr(module, setter_name, setter)
    module.SOAPY_SDR_WARNING = level
    monkeypatch.setitem(sys.modules, "SoapySDR", module)
    calibrate_thresholds._quiet_soapy_info_logs()
    setter.assert_called_once_with(level)


@pytest.mark.parametrize("missing", ["module", "setter", "level"])
def test_quiet_soapy_missing_controls(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
    missing: str,
) -> None:
    """Leave logging alone and emit debug when bindings or controls are missing."""
    module = ModuleType("SoapySDR")
    setter = MagicMock()
    if missing != "setter":
        module.SoapySDR_setLogLevel = setter
    if missing != "level":
        module.SOAPY_SDR_WARNING = 3
    monkeypatch.setitem(
        sys.modules, "SoapySDR", None if missing == "module" else module
    )
    with caplog.at_level(logging.DEBUG, logger="tools.calibrate_thresholds"):
        calibrate_thresholds._quiet_soapy_info_logs()
    setter.assert_not_called()
    assert "leaving" in caplog.text


@pytest.mark.parametrize("device, band_count", [
    ("pluto", 1), ("pluto", 2), ("hackrf", 1),
])
def test_capture_failure_exits_before_stored_analysis(
    console_calibration: dict[str, MagicMock], monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str], device: str, band_count: int,
) -> None:
    """Attempt each band once, report errors once and preserve stored priors."""
    targets = calibrate_thresholds._build_pluto_calibration_targets.return_value
    selected = sorted(targets, key=lambda target: target["label"])[:band_count]
    monkeypatch.setattr(calibrate_thresholds, "CALIBRATION_TARGETS", selected)
    calibrate_thresholds._build_pluto_calibration_targets.return_value = selected
    monkeypatch.setattr(
        "sys.argv", ["calibrate_thresholds.py", "--device", device]
    )
    monkeypatch.setattr(
        calibrate_thresholds, "_prompt_recapture_fresh_bands",
        MagicMock(return_value={"ADS_B"}),
    )
    timestamp = datetime.now().isoformat()
    store = console_calibration["store"]
    store.get_all_embeddings.return_value = {
        "ids": [f"ADS_B_{device}_{index}" for index in range(5)],
        "embeddings": [[0.1] * 7 for _ in range(5)],
        "metadatas": [
            {"label": "ADS_B", "device": device, "timestamp": timestamp}
            for _ in range(5)
        ],
    }
    error = (
        "No ADALM-PLUTO device found. Check USB connection and run 'iio_info' "
        "to verify hardware." if device == "pluto" else "No HackRF device found."
    )

    def fail_capture(**_kwargs: object) -> np.ndarray:
        """Reproduce the pipeline's error log and raised capture failure."""
        logging.getLogger("core.pipeline.capture").error(
            "IQ capture failed: %s", error
        )
        raise RuntimeError(error)

    console_calibration["capture"].side_effect = fail_capture
    merge = MagicMock()
    monkeypatch.setattr(calibrate_thresholds, "_merge_stored_entries", merge)
    with pytest.raises(SystemExit) as exc:
        calibrate_thresholds.main()
    assert exc.value.code == 1
    assert console_calibration["capture"].call_count == band_count
    captured = capsys.readouterr()
    assert captured.out.count(error) == band_count
    assert captured.err == ""
    assert "\r" not in captured.out and "\x1b" not in captured.out
    assert "✗ capture 1/5 failed\n" in captured.out
    assert "Kept 5 prior" in captured.out
    assert "no new records were stored" in captured.out
    assert "stale prior set is still excluded" in captured.out
    assert "No new captures" in captured.out
    assert "Stored records were left untouched." in captured.out
    assert "0/5 captured" not in captured.out
    assert "Results" not in captured.out
    assert "Suggested thresholds" not in captured.out
    device_name = "Pluto" if device == "pluto" else "HackRF"
    diagnostic = "iio_info" if device == "pluto" else "hackrf_info"
    assert captured.out.rstrip().endswith(
        f"→ Next: check the {device_name} is plugged in "
        f"({diagnostic} should list it), then run again"
    )
    console_calibration["derive"].assert_not_called()
    merge.assert_not_called()
    store.add_batch.assert_not_called()
    store._collection.delete.assert_not_called()
    calibrate_thresholds.time.sleep.assert_not_called()


def test_wiped_capture_failure_reports_prior_records_gone(
    console_calibration: dict[str, MagicMock], monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Report wiped prior calibration accurately when every capture fails."""
    monkeypatch.setattr("sys.argv", [
        "calibrate_thresholds.py", "--device", "pluto", "--wipe",
    ])
    console_calibration["capture"].side_effect = RuntimeError("device missing")
    with pytest.raises(SystemExit) as exc:
        calibrate_thresholds.main()
    assert exc.value.code == 1
    output = capsys.readouterr().out
    assert "No new captures" in output
    assert (
        "The calibration store was wiped at the start of this run."
    ) in output
    assert (
        "Earlier calibration records are gone; recapture is needed."
    ) in output
    assert "Stored records were left untouched." not in output
    console_calibration["store"].delete_collection.assert_called_once_with()
    console_calibration["store"].add_batch.assert_not_called()
    console_calibration["derive"].assert_not_called()


def test_verbose_failure_logs_without_third_party_info(
    console_calibration: dict[str, MagicMock], monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Show Mimir INFO and capture errors while filtering third-party INFO."""
    targets = calibrate_thresholds._build_pluto_calibration_targets.return_value
    calibrate_thresholds._build_pluto_calibration_targets.return_value = [
        target for target in targets if target["label"] == "ADS_B"
    ]
    monkeypatch.setattr("sys.argv", [
        "calibrate_thresholds.py", "--device", "pluto", "--verbose",
    ])
    third_party = logging.getLogger("chromadb")
    third_party.setLevel(logging.INFO)

    def fail_capture(**_kwargs: object) -> np.ndarray:
        """Emit representative library and Mimir messages before failing."""
        core_logger = logging.getLogger("core.pipeline.capture")
        core_logger.info("Mimir capture attempt")
        core_logger.error("IQ capture failed: unplugged")
        third_party.info("third-party INFO should stay hidden")
        third_party.warning("library warning remains visible")
        raise RuntimeError("unplugged")

    console_calibration["capture"].side_effect = fail_capture
    with pytest.raises(SystemExit) as exc:
        calibrate_thresholds.main()
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert "INFO core.pipeline.capture: Mimir capture attempt" in captured.err
    assert (
        "ERROR core.pipeline.capture: IQ capture failed: unplugged"
    ) in captured.err
    assert "Capture failed for ADS_B (capture 0): unplugged" in captured.err
    assert "library warning remains visible" in captured.err
    assert "third-party INFO should stay hidden" not in (
        captured.err + captured.out
    )
    assert "\r" not in captured.err + captured.out
    assert "\x1b" not in captured.err + captured.out
    console_calibration["derive"].assert_not_called()
    assert logging.getLogger().level == logging.WARNING
    for name in (
        calibrate_thresholds.__name__, "core", "embeddings", "llm", "tools",
    ):
        assert logging.getLogger(name).level == logging.INFO


def test_default_logging_has_no_console_handler(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Replace console handlers and silence core/library warnings/errors."""
    root = logging.getLogger()
    root.addHandler(logging.StreamHandler(sys.stderr))
    calibrate_thresholds._configure_console_logging(verbose=False)
    logging.getLogger("core.pipeline.capture").error("hidden capture error")
    logging.getLogger("core").warning("hidden core warning")
    logging.getLogger("chromadb").warning("hidden library warning")
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""
    assert len(root.handlers) == 1
    assert isinstance(root.handlers[0], logging.NullHandler)
