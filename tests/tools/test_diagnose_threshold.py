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
        """BAND_KEYS must map every BAND_SWEEP entry by a valid CLI key."""
        for band in diagnose_threshold.BAND_SWEEP:
            key = band["name"].lower().replace(" / ", "_").replace("-", "_").replace(" ", "_")
            assert key in diagnose_threshold.BAND_KEYS, f"{band['name']} missing from BAND_KEYS"
