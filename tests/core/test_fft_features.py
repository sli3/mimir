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
        assert np.median(result["psd_db"]) < -3.0

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
        """A tone at DC (zero offset from centre) peaks at the centre bin (nfft // 2)."""
        t = np.arange(nfft * 4)
        tone = np.exp(1j * 2 * np.pi * 0 * t / nfft).astype(np.complex64)
        result = compute_psd(tone, sample_rate, center_freq, nfft)
        peak_index = np.argmax(result["psd_db"])
        assert peak_index == nfft // 2
