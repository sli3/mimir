"""
tests/tools/test_diagnose_threshold.py
Mimir RF Scanner — Threshold Diagnostic Tool Tests

Smoke test for the all-band sweep logic without requiring live hardware.
"""

import sys
import os

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from dashboard.shared_state import BAND_PROFILES
from tools import diagnose_threshold


class TestDiagnoseThreshold:
    """Tests for the diagnose_threshold tool."""

    def test_sweep_band_recommends_threshold(self, monkeypatch):
        """Mock capture and PSD, assert sweep_band returns a recommended threshold."""

        def mock_capture_iq(**kwargs):
            num_samples = kwargs.get("num_samples", 256_000)
            return (
                np.random.randn(num_samples).astype(np.float32)
                + 1j * np.random.randn(num_samples).astype(np.float32)
            )

        def mock_compute_psd(samples, sample_rate_hz, center_freq_hz, nfft=2048):
            num_bins = nfft
            # Create a synthetic PSD with a peak so occupied_bins vary with threshold
            psd = np.full(num_bins, -40.0, dtype=np.float32)
            # A strong peak region
            psd[num_bins // 2 - 10 : num_bins // 2 + 10] = 0.0
            return {
                "frequencies_hz": np.linspace(
                    center_freq_hz - sample_rate_hz / 2,
                    center_freq_hz + sample_rate_hz / 2,
                    num_bins,
                ),
                "psd_db": psd,
                "psd_max_hold_db": psd + 5.0,
                "center_freq_hz": center_freq_hz,
                "sample_rate_hz": sample_rate_hz,
                "nfft": nfft,
                "num_chunks": 4,
            }

        monkeypatch.setattr(diagnose_threshold, "capture_iq", mock_capture_iq)
        monkeypatch.setattr(diagnose_threshold, "compute_psd", mock_compute_psd)

        band = {
            "name": "FM Broadcast",
            "freq_hz": 98_900_000,
            "lna_gain_db": 0,
            "vga_gain_db": 0,
            "target_bw_hz": 200_000,
            "sample_rate_hz": 2_000_000,
            "num_samples": 256_000,
        }

        result = diagnose_threshold.sweep_band(band)
        assert result["recommended_thr"] is not None
        assert result["recommended_thr"] in diagnose_threshold.THRESHOLD_CANDIDATES
        assert result["recommended_bw"] is not None
        assert isinstance(result["recommended_bw"], (int, float))
        assert len(result["rows"]) == len(diagnose_threshold.THRESHOLD_CANDIDATES)

    def test_band_keys_covers_all_sweep_bands(self):
        """Every BAND_SWEEP entry must be reachable via exactly one CLI key.

        Asserts the invariant (each band is uniquely reachable) rather than
        recomputing the key transform here — duplicating the transform in the
        test couples it to the implementation and silently breaks whenever the
        key derivation changes (as it did when ADS-B's key moved ads_b -> adsb).
        """
        # Every band object in BAND_SWEEP must be present as a value in BAND_KEYS.
        mapped_bands = list(diagnose_threshold.BAND_KEYS.values())
        for band in diagnose_threshold.BAND_SWEEP:
            assert band in mapped_bands, f"{band['name']} missing from BAND_KEYS"
        # And the mapping must be 1:1 — no two bands collapsing to the same key.
        assert len(diagnose_threshold.BAND_KEYS) == len(diagnose_threshold.BAND_SWEEP)
        # ADS-B specifically must be reachable as 'adsb' (matches docstring + BAND_PROFILES).
        assert "adsb" in diagnose_threshold.BAND_KEYS
        assert diagnose_threshold.BAND_KEYS["adsb"]["name"] == "ADS-B"

    def test_band_sweep_gains_match_band_profiles(self):
        """BAND_SWEEP gain values must match dashboard.shared_state.BAND_PROFILES."""
        NAME_TO_KEY = {
            "FM Broadcast": "fm_broadcast",
            "Aviation VHF": "aviation",
            "ACARS": "acars",
            "APRS": "aprs",
            "ISM / LoRa": "ism",
            "ADS-B": "adsb",
        }
        for band in diagnose_threshold.BAND_SWEEP:
            profile = BAND_PROFILES[NAME_TO_KEY[band["name"]]]
            assert band["lna_gain_db"] == profile["lna_gain_db"]
            assert band["vga_gain_db"] == profile["vga_gain_db"]

    def test_adsb_sweep_uses_max_hold_trace(self, monkeypatch):
        """sweep_band passes trace_key='psd_max_hold_db' for the ADS-B band."""
        seen_trace_keys = []

        def mock_capture_iq(**kwargs):
            num_samples = kwargs.get("num_samples", 256_000)
            return (
                np.random.randn(num_samples).astype(np.float32)
                + 1j * np.random.randn(num_samples).astype(np.float32)
            )

        def mock_compute_psd(samples, sample_rate_hz, center_freq_hz, nfft=2048):
            num_bins = nfft
            psd = np.full(num_bins, -40.0, dtype=np.float32)
            psd[num_bins // 2 - 10 : num_bins // 2 + 10] = 0.0
            return {
                "frequencies_hz": np.linspace(
                    center_freq_hz - sample_rate_hz / 2,
                    center_freq_hz + sample_rate_hz / 2,
                    num_bins,
                ),
                "psd_db": psd,
                "psd_max_hold_db": psd + 5.0,
                "center_freq_hz": center_freq_hz,
                "sample_rate_hz": sample_rate_hz,
                "nfft": nfft,
                "num_chunks": 4,
            }

        def trace_checking_fingerprint(psd_result, signal_threshold_db=None, trace_key='psd_db'):
            seen_trace_keys.append(trace_key)
            from core.pipeline.features import fingerprint_spectrum as real_fp
            return real_fp(psd_result, signal_threshold_db=signal_threshold_db, trace_key=trace_key)

        monkeypatch.setattr(diagnose_threshold, "capture_iq", mock_capture_iq)
        monkeypatch.setattr(diagnose_threshold, "compute_psd", mock_compute_psd)
        monkeypatch.setattr(diagnose_threshold, "fingerprint_spectrum", trace_checking_fingerprint)

        adsb_band = next(b for b in diagnose_threshold.BAND_SWEEP if b["name"] == "ADS-B")
        diagnose_threshold.sweep_band(adsb_band)

        assert all(t == "psd_max_hold_db" for t in seen_trace_keys)