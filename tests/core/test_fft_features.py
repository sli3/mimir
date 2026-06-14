"""
tests/core/test_fft_features.py
Mimir RF Scanner — Phase 2 FFT Feature Extraction Tests

PURPOSE
───────
Tests for compute_psd() in core/pipeline/fft.py.
Proves PSD computation produces correct frequencies, shapes, and values.

Run with:
    python -m pytest tests/core/test_fft_features.py -v

IMPORTANT: These tests use synthetic samples only — no hardware required.
"""

import sys
import os

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from core.pipeline.fft import compute_psd
from core.pipeline.features import fingerprint_spectrum, SIGNAL_THRESHOLD_DB


class TestComputePsd:
    """Tests for the compute_psd() function."""

    @pytest.fixture
    def samples(self):
        """Complex random noise samples for standard tests."""
        return np.random.randn(8192).astype(np.float32) + 1j * np.random.randn(8192).astype(np.float32)

    @pytest.fixture
    def center_freq(self):
        return 98_000_000

    @pytest.fixture
    def sample_rate(self):
        return 2_000_000

    @pytest.fixture
    def nfft(self):
        return 2048

    def test_output_keys_present(self, samples, sample_rate, center_freq, nfft):
        """Result dict contains all 6 required keys."""
        result = compute_psd(samples, sample_rate, center_freq, nfft)
        expected_keys = {"frequencies_hz", "psd_db", "center_freq_hz", "sample_rate_hz", "nfft", "num_chunks"}
        assert set(result.keys()) == expected_keys

    def test_frequencies_shape(self, samples, sample_rate, center_freq, nfft):
        """frequencies_hz has shape (nfft,)."""
        result = compute_psd(samples, sample_rate, center_freq, nfft)
        assert result["frequencies_hz"].shape == (nfft,)

    def test_psd_shape(self, samples, sample_rate, center_freq, nfft):
        """psd_db has shape (nfft,)."""
        result = compute_psd(samples, sample_rate, center_freq, nfft)
        assert result["psd_db"].shape == (nfft,)

    def test_frequencies_are_absolute(self, samples, sample_rate, center_freq, nfft):
        """Frequencies are absolute, centered on center_freq_hz."""
        result = compute_psd(samples, sample_rate, center_freq, nfft)
        freqs = result["frequencies_hz"]
        assert freqs.min() >= center_freq - sample_rate / 2
        assert freqs.max() <= center_freq + sample_rate / 2

    def test_num_chunks_correct(self, sample_rate, center_freq, nfft):
        """num_chunks equals len(samples) // nfft, remainder discarded."""
        samples_8192 = np.random.randn(8192).astype(np.float32) + 1j * np.random.randn(8192).astype(np.float32)
        result_8192 = compute_psd(samples_8192, sample_rate, center_freq, nfft)
        assert result_8192["num_chunks"] == 4

        samples_5000 = np.random.randn(5000).astype(np.float32) + 1j * np.random.randn(5000).astype(np.float32)
        result_5000 = compute_psd(samples_5000, sample_rate, center_freq, nfft)
        assert result_5000["num_chunks"] == 2

    def test_psd_values_are_finite(self, samples, sample_rate, center_freq, nfft):
        """No NaN or Inf values in psd_db."""
        result = compute_psd(samples, sample_rate, center_freq, nfft)
        assert np.all(np.isfinite(result["psd_db"]))

    def test_psd_values_are_negative_dbfs(self, samples, sample_rate, center_freq, nfft):
        """Median PSD of random noise input is well below 0 dBFS."""
        result = compute_psd(samples, sample_rate, center_freq, nfft)
        # True dBFS: random noise sits well below -10 dBFS
        assert np.median(result["psd_db"]) < -10.0

    def test_too_few_samples_returns_empty(self, sample_rate, center_freq, nfft):
        """With fewer samples than nfft, returns empty arrays and num_chunks == 0."""
        few_samples = np.random.randn(512).astype(np.float32) + 1j * np.random.randn(512).astype(np.float32)
        result = compute_psd(few_samples, sample_rate, center_freq, nfft)
        assert result["num_chunks"] == 0
        assert result["frequencies_hz"].shape == (0,)
        assert result["psd_db"].shape == (0,)

    def test_passthrough_values(self, samples, sample_rate, center_freq, nfft):
        """center_freq_hz, sample_rate_hz, and nfft in result match what was passed in."""
        result = compute_psd(samples, sample_rate, center_freq, nfft)
        assert result["center_freq_hz"] == center_freq
        assert result["sample_rate_hz"] == sample_rate
        assert result["nfft"] == nfft

    def test_known_tone_appears_at_correct_bin(self, sample_rate, center_freq, nfft):
        """A tone at offset bin 10 peaks at centre bin + 10 after DC removal."""
        t = np.arange(nfft * 4)
        tone = np.exp(1j * 2 * np.pi * 10 * t / nfft).astype(np.complex64)
        result = compute_psd(tone, sample_rate, center_freq, nfft)
        peak_index = np.argmax(result["psd_db"])
        assert peak_index == nfft // 2 + 10


class TestSignalThresholdDb:
    """Tests for the SIGNAL_THRESHOLD_DB constant."""

    def test_signal_threshold_db_is_calibrated(self):
        """SIGNAL_THRESHOLD_DB must be 24.0 dB after live hardware calibration."""
        assert SIGNAL_THRESHOLD_DB == 24.0


class TestFingerprintSpectrum:
    """Tests for the fingerprint_spectrum() function."""

    @pytest.fixture
    def fm_psd(self):
        """Synthetic FM-like capture: wideband signal spanning ~200 bins."""
        nfft = 2048
        num_chunks = 4
        sample_rate_hz = 2_000_000
        num_samples = nfft * num_chunks
        t = np.arange(num_samples)

        carrier_bin = 50
        deviation_hz = 80_000
        mod_freq_hz = 1_000
        mod_index = deviation_hz / mod_freq_hz

        phi_c = 2 * np.pi * carrier_bin * t / nfft
        phi_m = mod_index * np.sin(2 * np.pi * mod_freq_hz * t / sample_rate_hz)
        signal = np.exp(1j * (phi_c + phi_m)).astype(np.complex64)

        noise = (np.random.randn(num_samples) * 1e-4).astype(np.float32) + \
                1j * (np.random.randn(num_samples) * 1e-4).astype(np.float32)
        samples = signal + noise

        return compute_psd(
            samples,
            sample_rate_hz=sample_rate_hz,
            center_freq_hz=98_000_000,
            nfft=nfft,
        )

    def test_output_keys_present(self, fm_psd):
        """Result dict contains all 7 required keys."""
        result = fingerprint_spectrum(fm_psd)
        expected_keys = {
            "center_freq_hz", "peak_freq_hz", "peak_power_db", "noise_floor_db",
            "snr_db", "bandwidth_hz", "occupied_bins",
        }
        assert set(result.keys()) == expected_keys

    def test_peak_freq_within_band(self, fm_psd):
        """peak_freq_hz must be between 97_000_000 and 99_000_000."""
        result = fingerprint_spectrum(fm_psd)
        assert 97_000_000 <= result["peak_freq_hz"] <= 99_000_000

    def test_snr_is_positive(self, fm_psd):
        """SNR must be >= 0.0 for any valid signal input."""
        result = fingerprint_spectrum(fm_psd)
        assert result["snr_db"] >= 0.0

    def test_snr_equals_peak_minus_noise(self, fm_psd):
        """snr_db == peak_power_db - noise_floor_db exactly."""
        result = fingerprint_spectrum(fm_psd)
        assert result["snr_db"] == result["peak_power_db"] - result["noise_floor_db"]

    def test_occupied_bins_is_non_negative(self, fm_psd):
        """occupied_bins >= 0 always."""
        result = fingerprint_spectrum(fm_psd)
        assert result["occupied_bins"] >= 0

    def test_bandwidth_equals_bins_times_hz_per_bin(self, fm_psd):
        """bandwidth_hz == occupied_bins * (sample_rate_hz / nfft)."""
        result = fingerprint_spectrum(fm_psd)
        hz_per_bin = fm_psd["sample_rate_hz"] / fm_psd["nfft"]
        assert result["bandwidth_hz"] == result["occupied_bins"] * hz_per_bin

    def test_empty_psd_returns_zeroed_dict(self):
        """When compute_psd returns empty arrays, fingerprint_spectrum returns zeroed dict."""
        empty_psd = {
            "frequencies_hz": np.array([]),
            "psd_db": np.array([]),
            "center_freq_hz": 98_000_000,
            "sample_rate_hz": 2_000_000,
            "nfft": 2048,
        }
        result = fingerprint_spectrum(empty_psd)
        assert result["center_freq_hz"] == 98_000_000
        assert result["peak_freq_hz"] == 0.0
        assert result["peak_power_db"] == 0.0
        assert result["noise_floor_db"] == 0.0
        assert result["snr_db"] == 0.0
        assert result["bandwidth_hz"] == 0.0
        assert result["occupied_bins"] == 0

    def test_center_freq_passthrough(self, fm_psd):
        """center_freq_hz in result matches what was passed to compute_psd."""
        result = fingerprint_spectrum(fm_psd)
        assert result["center_freq_hz"] == fm_psd["center_freq_hz"]

    def test_known_tone_has_positive_snr(self):
        """Inject a synthetic tone at bin 10 offset (non-DC, survives DC removal) — fingerprint_spectrum must return snr_db > 10.0."""
        nfft = 2048
        num_chunks = 4
        t = np.arange(nfft * num_chunks)
        tone = np.exp(1j * 2 * np.pi * 10 * t / nfft).astype(np.complex64)
        noise = (np.random.randn(len(t)) * 0.01).astype(np.float32) + \
                1j * (np.random.randn(len(t)) * 0.01).astype(np.float32)
        samples = tone + noise
        psd = compute_psd(
            samples,
            sample_rate_hz=2_000_000,
            center_freq_hz=98_000_000,
            nfft=nfft,
        )
        result = fingerprint_spectrum(psd)
        assert result["snr_db"] > 10.0

    def test_occupied_bins_type_is_int(self, fm_psd):
        """occupied_bins must be Python int, not numpy int."""
        result = fingerprint_spectrum(fm_psd)
        assert type(result["occupied_bins"]) is int

    def test_bandwidth_realistic_fm_signal(self, fm_psd):
        """bandwidth_hz must be between 100_000 and 300_000 Hz for wideband FM-like signal."""
        result = fingerprint_spectrum(fm_psd)
        assert 100_000 <= result["bandwidth_hz"] <= 300_000
