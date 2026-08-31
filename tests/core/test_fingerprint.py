"""
tests/core/test_fingerprint.py — Tests for the extracted fingerprint_samples helper

fingerprint_samples() is the band-aware per-chunk wrapper that bundles
resolve_band_profile + compute_psd + fingerprint_spectrum. These tests
prove it resolves the correct per-device band profile and delegates to the
underlying fingerprint_spectrum() correctly.
"""

import numpy as np
import pytest

from core.pipeline.features import fingerprint_spectrum
from core.pipeline.fft import compute_psd
from core.pipeline.fingerprint import fingerprint_samples
from dashboard.shared_state import BAND_PROFILES, PLUTO_BAND_PROFILES


def _make_samples(num_samples: int = 4096) -> np.ndarray:
    """Synthetic noise-like IQ samples."""
    rng = np.random.default_rng(42)
    return (
        rng.standard_normal(num_samples) + 1j * rng.standard_normal(num_samples)
    ).astype(np.complex64)


class TestFingerprintSamples:
    """Happy-path and device-resolution tests."""

    def test_returns_fingerprint_with_expected_keys(self):
        """fingerprint_samples returns a dict matching fingerprint_spectrum's shape."""
        samples = _make_samples(4096)
        result = fingerprint_samples(
            samples,
            sample_rate_hz=2_000_000.0,
            core_freq_hz=98_000_000.0,
            band_key="fm_broadcast",
            device="hackrf",
        )

        expected = fingerprint_spectrum(
            compute_psd(samples, 2_000_000.0, 98_000_000.0),
            signal_threshold_db=BAND_PROFILES["fm_broadcast"].get("signal_threshold_db"),
            crop_half_width_hz=BAND_PROFILES["fm_broadcast"].get("crop_half_width_hz"),
            burst_use_wide_window=BAND_PROFILES["fm_broadcast"].get("burst_use_wide_window", False),
            trace_key=BAND_PROFILES["fm_broadcast"].get("fingerprint_trace_key", "psd_db"),
        )
        assert set(result.keys()) == set(expected.keys())
        assert result["signal_threshold_db"] == expected["signal_threshold_db"]

    def test_pluto_adsb_uses_pluto_overlay_threshold(self):
        """ADS-B on Pluto resolves the PLUTO_BAND_PROFILES signal_threshold_db."""
        samples = _make_samples(4096)
        result = fingerprint_samples(
            samples,
            sample_rate_hz=2_000_000.0,
            core_freq_hz=1_090_000_000.0,
            band_key="adsb",
            device="plutosdr",
        )
        assert result["signal_threshold_db"] == (
            PLUTO_BAND_PROFILES["adsb"]["signal_threshold_db"]
        )

    def test_hackrf_adsb_uses_base_threshold(self):
        """ADS-B on HackRF uses the raw BAND_PROFILES signal_threshold_db."""
        samples = _make_samples(4096)
        result = fingerprint_samples(
            samples,
            sample_rate_hz=2_000_000.0,
            core_freq_hz=1_090_000_000.0,
            band_key="adsb",
            device="hackrf",
        )
        assert result["signal_threshold_db"] == (
            BAND_PROFILES["adsb"]["signal_threshold_db"]
        )

    def test_unknown_device_falls_back_to_base_profile(self):
        """An unknown device string behaves like HackRF (base profile)."""
        samples = _make_samples(4096)
        result = fingerprint_samples(
            samples,
            sample_rate_hz=2_000_000.0,
            core_freq_hz=98_000_000.0,
            band_key="fm_broadcast",
            device="unknown_device",
        )
        expected_threshold = BAND_PROFILES["fm_broadcast"]["signal_threshold_db"]
        assert result["signal_threshold_db"] == expected_threshold

    def test_band_key_none_raises_key_error(self):
        """resolve_band_profile(None, device) raises KeyError, which propagates."""
        samples = _make_samples(4096)
        with pytest.raises(KeyError):
            fingerprint_samples(
                samples,
                sample_rate_hz=2_000_000.0,
                core_freq_hz=98_000_000.0,
                band_key=None,
                device="hackrf",
            )
