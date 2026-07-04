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
    for label, _freq_hz, lna, vga, _threshold in targets:
        if label == "noise_floor":
            continue
        profile = BAND_PROFILES[LABEL_TO_KEY[label]]
        assert (lna, vga) == (profile["lna_gain_db"], profile["vga_gain_db"])


def test_noise_floor_intentionally_diverges(targets):
    noise_floor = next(t for t in targets if t[0] == "noise_floor")
    lna, vga = noise_floor[2], noise_floor[3]
    noise_profile = BAND_PROFILES["noise_floor"]
    assert (lna, vga) != (noise_profile["lna_gain_db"], noise_profile["vga_gain_db"])


def test_signal_thresholds_match_band_profiles(targets):
    for label, _freq_hz, _lna, _vga, threshold in targets:
        if label == "noise_floor":
            assert threshold == 10.0
            continue
        profile = BAND_PROFILES[LABEL_TO_KEY[label]]
        assert threshold == profile["signal_threshold_db"]
