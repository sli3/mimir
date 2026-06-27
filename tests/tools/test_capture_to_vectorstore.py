"""
Tests for tools/capture_to_vectorstore.py

All tests use mocked hardware (capture_iq) and in-memory ChromaDB stores.
"""

import argparse
import numpy as np
import pytest
from unittest.mock import MagicMock, patch

from embeddings.store import SignalStore
from tools import capture_to_vectorstore
from tools.capture_to_vectorstore import (
    ANTENNA_PROFILES,
    CAPTURE_TARGETS,
    build_metadata,
    run_capture_loop,
)


def test_capture_targets_structure():
    required_keys = {
        "label",
        "freq_hz",
        "sample_rate_hz",
        "num_samples",
        "lna_gain_db",
        "vga_gain_db",
        "signal_threshold_db",
        "captures",
    }
    assert len(CAPTURE_TARGETS) == 7
    for target in CAPTURE_TARGETS:
        assert set(target.keys()) == required_keys
        assert isinstance(target["label"], str)
        assert isinstance(target["freq_hz"], int)
        assert isinstance(target["sample_rate_hz"], int)
        assert isinstance(target["num_samples"], int)
        assert isinstance(target["lna_gain_db"], int)
        assert isinstance(target["vga_gain_db"], int)
        assert isinstance(target["signal_threshold_db"], float)
        assert isinstance(target["captures"], int)
        assert target["sample_rate_hz"] == 2_000_000
        assert target["num_samples"] == 256_000
        assert target["captures"] == 5


def test_antenna_profiles_coverage():
    all_labels = {t["label"] for t in CAPTURE_TARGETS}
    for key, profile in ANTENNA_PROFILES.items():
        for band in profile["bands"]:
            assert band in all_labels, f"Antenna {key} band {band!r} not in CAPTURE_TARGETS"


def test_no_missing_signal_threshold():
    labels = {t["label"] for t in CAPTURE_TARGETS}
    for profile in ANTENNA_PROFILES.values():
        for band in profile["bands"]:
            assert band in labels
            target = next(t for t in CAPTURE_TARGETS if t["label"] == band)
            assert isinstance(target["signal_threshold_db"], float)


def test_build_metadata():
    target = {
        "freq_hz": 98_900_000,
        "sample_rate_hz": 2_000_000,
        "signal_threshold_db": 21.0,
    }
    fingerprint = {
        "peak_power_db": -45.5,
        "snr_db": 18.3,
    }
    metadata = build_metadata("FM_broadcast", "Telescopic whip", target, fingerprint, 2)

    assert metadata["label"] == "FM_broadcast"
    assert metadata["source"] == "live_capture"
    assert metadata["antenna"] == "Telescopic whip"
    assert metadata["freq_hz"] == 98_900_000
    assert metadata["sample_rate_hz"] == 2_000_000
    assert metadata["capture_origin"] == "Adelaide, SA, AU"
    assert metadata["signal_threshold_db"] == 21.0
    assert isinstance(metadata["timestamp"], str)
    assert metadata["peak_power_db"] == -45.5
    assert metadata["snr_db"] == 18.3
    assert metadata["capture_index"] == 2


def test_one_band_captures_five_records(tmp_path):
    store = SignalStore(str(tmp_path))
    embedder = capture_to_vectorstore.SpectrumEmbedder()
    target = next(t for t in CAPTURE_TARGETS if t["label"] == "FM_broadcast")

    samples = np.ones(target["num_samples"], dtype=np.complex64)

    with (
        patch("tools.capture_to_vectorstore.capture_iq", return_value=samples),
        patch("tools.capture_to_vectorstore.time.sleep") as mock_sleep,
    ):
        captured = run_capture_loop(
            store=store,
            embedder=embedder,
            selected_targets=[target],
            antenna_name="Telescopic whip",
            input_func=lambda _prompt: "",
            sleep_func=mock_sleep,
        )

    assert captured == 5
    assert store.count() == 5
    for meta in store._collection.get(include=["metadatas"])["metadatas"]:
        assert meta["label"] == "FM_broadcast"
        assert meta["source"] == "live_capture"


def test_runtime_error_continues_to_next_capture(tmp_path):
    store = SignalStore(str(tmp_path))
    embedder = capture_to_vectorstore.SpectrumEmbedder()
    target = next(t for t in CAPTURE_TARGETS if t["label"] == "Aviation_VHF")
    samples = np.ones(target["num_samples"], dtype=np.complex64)

    call_count = 0
    def flaky_capture(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("HackRF not found")
        return samples

    with patch("tools.capture_to_vectorstore.capture_iq", side_effect=flaky_capture):
        captured = run_capture_loop(
            store=store,
            embedder=embedder,
            selected_targets=[target],
            antenna_name="Telescopic whip",
            input_func=lambda _prompt: "",
            sleep_func=lambda _secs: None,
        )

    assert call_count == 5
    assert captured == 4
    assert store.count() == 4
    for meta in store._collection.get(include=["metadatas"])["metadatas"]:
        assert meta["label"] == "Aviation_VHF"


def test_wipe_flag_deletes_collection():
    mock_store = MagicMock(spec=SignalStore)
    mock_store.count.return_value = 7

    def fresh_mock(*args, **kwargs):
        return mock_store

    with (
        patch("tools.capture_to_vectorstore._parse_args", return_value=argparse.Namespace(wipe=True)),
        patch("tools.capture_to_vectorstore.SignalStore", side_effect=fresh_mock),
        patch("tools.capture_to_vectorstore.SpectrumEmbedder"),
        patch("tools.capture_to_vectorstore._select_antenna", return_value=("1", ANTENNA_PROFILES["1"])),
        patch("tools.capture_to_vectorstore.run_capture_loop") as mock_loop,
    ):
        capture_to_vectorstore.main()

    assert mock_store.delete_collection.call_count == 1
    assert mock_loop.call_count == 1


def test_ctrl_c_during_warning_skips_band(tmp_path):
    store = SignalStore(str(tmp_path))
    embedder = capture_to_vectorstore.SpectrumEmbedder()
    target = next(t for t in CAPTURE_TARGETS if t["label"] == "ADS_B")
    samples = np.ones(target["num_samples"], dtype=np.complex64)

    call_count = 0
    def raising_input(_prompt):
        nonlocal call_count
        call_count += 1
        raise KeyboardInterrupt

    with patch("tools.capture_to_vectorstore.capture_iq", return_value=samples):
        captured = run_capture_loop(
            store=store,
            embedder=embedder,
            selected_targets=[target],
            antenna_name="Spiral discone",
            input_func=raising_input,
            sleep_func=lambda _secs: None,
        )

    assert call_count == 1
    assert captured == 0
    assert store.count() == 0


def test_signal_threshold_passed_and_stored(tmp_path):
    store = SignalStore(str(tmp_path))
    embedder = capture_to_vectorstore.SpectrumEmbedder()
    target = next(t for t in CAPTURE_TARGETS if t["label"] == "APRS")
    samples = np.ones(target["num_samples"], dtype=np.complex64)
    expected_threshold = target["signal_threshold_db"]

    real_fingerprint_spectrum = capture_to_vectorstore.fingerprint_spectrum
    seen_thresholds = []

    def threshold_checking_fingerprint(psd_result, signal_threshold_db=None):
        seen_thresholds.append(signal_threshold_db)
        return real_fingerprint_spectrum(psd_result, signal_threshold_db=signal_threshold_db)

    with (
        patch("tools.capture_to_vectorstore.capture_iq", return_value=samples),
        patch("tools.capture_to_vectorstore.fingerprint_spectrum", side_effect=threshold_checking_fingerprint),
    ):
        run_capture_loop(
            store=store,
            embedder=embedder,
            selected_targets=[target],
            antenna_name="Telescopic whip",
            input_func=lambda _prompt: "",
            sleep_func=lambda _secs: None,
        )

    assert store.count() == 5
    assert all(t == expected_threshold for t in seen_thresholds)
    for meta in store._collection.get(include=["metadatas"])["metadatas"]:
        assert meta["signal_threshold_db"] == expected_threshold
