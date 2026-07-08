"""
Tests for tools/diagnose_fingerprints.py

Guard tests that verify TARGETS stays in sync with BAND_PROFILES.
Because the module runs a top-level capture loop on import, the
hardware-facing functions must be mocked before import.
"""

from unittest.mock import patch

import numpy as np
import pytest

from dashboard.shared_state import BAND_PROFILES


LABEL_TO_KEY = {
    "FM_broadcast": "fm_broadcast",
    "Aviation_VHF": "aviation",
    "ACARS": "acars",
    "APRS": "aprs",
    "AIS": "ais",
    "ISM_LoRa": "ism",
    "ADS_B": "adsb",
}


@pytest.fixture
def targets():
    with patch(
        "core.pipeline.capture.capture_iq",
        return_value=np.zeros(256_000, dtype=np.complex64),
    ):
        with patch(
            "core.pipeline.fft.compute_psd",
            return_value={
                "frequencies_hz": np.zeros(2048),
                "psd_db": np.zeros(2048),
                "center_freq_hz": 0,
                "sample_rate_hz": 2_000_000,
                "nfft": 2048,
                "num_chunks": 4,
            },
        ):
            with patch(
                "core.pipeline.features.fingerprint_spectrum",
                return_value={},
            ):
                from tools import diagnose_fingerprints
                yield diagnose_fingerprints.TARGETS


def test_targets_gains_match_band_profiles(targets):
    for target in targets:
        if target["label"] == "noise_floor":
            continue
        profile = BAND_PROFILES[LABEL_TO_KEY[target["label"]]]
        assert (target["lna_gain_db"], target["vga_gain_db"]) == (profile["lna_gain_db"], profile["vga_gain_db"])


def test_noise_floor_intentionally_diverges(targets):
    noise_floor = next(t for t in targets if t["label"] == "noise_floor")
    lna = noise_floor["lna_gain_db"]
    vga = noise_floor["vga_gain_db"]
    noise_profile = BAND_PROFILES["noise_floor"]
    assert (lna, vga) != (noise_profile["lna_gain_db"], noise_profile["vga_gain_db"])


def test_signal_thresholds_match_band_profiles(targets):
    for target in targets:
        if target["label"] == "noise_floor":
            assert target["signal_threshold_db"] == 10.0
            continue
        profile = BAND_PROFILES[LABEL_TO_KEY[target["label"]]]
        assert target["signal_threshold_db"] == profile["signal_threshold_db"]


def test_adsb_only_uses_max_hold(targets):
    """Only the ADS_B target carries the psd_max_hold_db trace key."""
    for target in targets:
        if target["label"] == "ADS_B":
            assert target.get("trace_key") == "psd_max_hold_db"
        else:
            assert "trace_key" not in target

