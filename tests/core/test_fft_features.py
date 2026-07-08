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
        """Result dict contains all required keys."""
        result = compute_psd(samples, sample_rate, center_freq, nfft)
        expected_keys = {"frequencies_hz", "psd_db", "psd_max_hold_db", "center_freq_hz", "sample_rate_hz", "nfft", "num_chunks", "chunk_peak_db"}
        assert set(result.keys()) == expected_keys

    def test_frequencies_shape(self, samples, sample_rate, center_freq, nfft):
        """frequencies_hz has shape (nfft,)."""
        result = compute_psd(samples, sample_rate, center_freq, nfft)
        assert result["frequencies_hz"].shape == (nfft,)

    def test_psd_shape(self, samples, sample_rate, center_freq, nfft):
        """psd_db has shape (nfft,)."""
        result = compute_psd(samples, sample_rate, center_freq, nfft)
        assert result["psd_db"].shape == (nfft,)

    def test_psd_max_hold_db_key_present(self, samples, sample_rate, center_freq, nfft):
        """Result dict contains psd_max_hold_db key."""
        result = compute_psd(samples, sample_rate, center_freq, nfft)
        assert "psd_max_hold_db" in result

    def test_psd_max_hold_db_shape(self, samples, sample_rate, center_freq, nfft):
        """psd_max_hold_db has shape (nfft,)."""
        result = compute_psd(samples, sample_rate, center_freq, nfft)
        assert result["psd_max_hold_db"].shape == (nfft,)

    def test_psd_max_hold_db_gte_averaged(self, samples, sample_rate, center_freq, nfft):
        """Max-hold trace is always >= averaged trace pointwise."""
        result = compute_psd(samples, sample_rate, center_freq, nfft)
        assert np.all(result["psd_max_hold_db"] >= result["psd_db"])

    def test_psd_max_hold_db_empty_too_few_samples(self, sample_rate, center_freq, nfft):
        """Early return (len < nfft) includes an empty psd_max_hold_db array."""
        few_samples = np.random.randn(512).astype(np.float32) + 1j * np.random.randn(512).astype(np.float32)
        result = compute_psd(few_samples, sample_rate, center_freq, nfft)
        assert "psd_max_hold_db" in result
        assert result["psd_max_hold_db"].shape == (0,)

    def test_psd_max_hold_db_empty_num_chunks_zero(self, sample_rate, center_freq, nfft):
        """Early return (num_chunks == 0) includes an empty psd_max_hold_db array."""
        # len(samples) is exactly nfft - 1, so num_chunks == 0 after the initial check
        samples = np.random.randn(nfft - 1).astype(np.float32) + 1j * np.random.randn(nfft - 1).astype(np.float32)
        result = compute_psd(samples, sample_rate, center_freq, nfft)
        assert "psd_max_hold_db" in result
        assert result["psd_max_hold_db"].shape == (0,)

    def test_psd_db_unchanged_by_max_hold_addition(self, sample_rate, center_freq, nfft):
        """psd_db values are identical to a reference snapshot for a fixed synthetic input."""
        num_chunks = 4
        t = np.arange(nfft * num_chunks)
        tone = np.exp(1j * 2 * np.pi * 10 * t / nfft).astype(np.complex64)
        np.random.seed(42)
        noise = (np.random.randn(len(t)) * 0.01).astype(np.float32) + \
                1j * (np.random.randn(len(t)) * 0.01).astype(np.float32)
        samples = tone + noise
        result = compute_psd(samples, sample_rate, center_freq, nfft)
        expected_psd_db = np.array([
            -69.10545119, -71.49487071, -75.14477691, -71.34085955,
            -73.19596439, -70.70552243, -69.73676076, -67.97820771,
            -68.18218690, -7.77752153, -1.76198389, -7.77628199,
            -67.57857694, -70.80011497, -69.69375993, -68.50839083,
            -67.58642583, -70.07266844, -73.19570543, -71.44535042,
        ])
        peak_index = np.argmax(result["psd_db"])
        assert peak_index == nfft // 2 + 10
        assert np.allclose(result["psd_db"][peak_index - 10 : peak_index + 10], expected_psd_db, atol=1e-6)

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

    def test_chunk_peak_db_key_present(self, samples, sample_rate, center_freq, nfft):
        """Result dict contains chunk_peak_db key."""
        result = compute_psd(samples, sample_rate, center_freq, nfft)
        assert "chunk_peak_db" in result

    def test_chunk_peak_db_is_float(self, samples, sample_rate, center_freq, nfft):
        """chunk_peak_db is a Python float."""
        result = compute_psd(samples, sample_rate, center_freq, nfft)
        assert isinstance(result["chunk_peak_db"], float)

    def test_chunk_peak_db_gte_averaged_peak(self, sample_rate, center_freq, nfft):
        """For a synthetic tone signal, chunk_peak_db >= psd_db.max() (peak of single chunk >= averaged peak)."""
        num_chunks = 4
        t = np.arange(nfft * num_chunks)
        tone = np.exp(1j * 2 * np.pi * 10 * t / nfft).astype(np.complex64)
        result = compute_psd(tone, sample_rate, center_freq, nfft)
        assert result["chunk_peak_db"] >= result["psd_db"].max()

    def test_chunk_peak_db_empty_psd(self, sample_rate, center_freq, nfft):
        """With too-few samples, chunk_peak_db == 0.0 (matches the num_chunks == 0 early-return path)."""
        few_samples = np.random.randn(512).astype(np.float32) + 1j * np.random.randn(512).astype(np.float32)
        result = compute_psd(few_samples, sample_rate, center_freq, nfft)
        assert result["chunk_peak_db"] == 0.0


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
        """Result dict contains all 11 required keys."""
        result = fingerprint_spectrum(fm_psd)
        expected_keys = {
            "center_freq_hz", "peak_freq_hz", "peak_power_db", "noise_floor_db",
            "snr_db", "bandwidth_hz", "occupied_bins", "spectral_flatness",
            "signal_threshold_db", "snr_margin_db", "peak_bin_power_db",
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
        assert result["spectral_flatness"] == 0.0
        assert result["signal_threshold_db"] == SIGNAL_THRESHOLD_DB
        assert result["snr_margin_db"] == 0.0
        assert result["peak_bin_power_db"] == 0.0

    def test_spectral_flatness_is_float_between_zero_and_one(self, fm_psd):
        """spectral_flatness must be a float in [0.0, 1.0]."""
        result = fingerprint_spectrum(fm_psd)
        assert isinstance(result["spectral_flatness"], float)
        assert 0.0 <= result["spectral_flatness"] <= 1.0

    def test_spectral_flatness_tone_is_low(self):
        """Pure tone input should have spectral_flatness close to 0.0 (very tonal)."""
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
        assert result["spectral_flatness"] < 0.1

    def test_spectral_flatness_noise_is_high(self):
        """White noise input should have spectral_flatness close to 1.0 (noise-like)."""
        nfft = 2048
        num_chunks = 4
        samples = (
            np.random.randn(nfft * num_chunks).astype(np.float32)
            + 1j * np.random.randn(nfft * num_chunks).astype(np.float32)
        )
        psd = compute_psd(
            samples,
            sample_rate_hz=2_000_000,
            center_freq_hz=98_000_000,
            nfft=nfft,
        )
        result = fingerprint_spectrum(psd)
        assert result["spectral_flatness"] > 0.8

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

    def test_fallback_threshold_used_when_none_passed(self, fm_psd):
        """When signal_threshold_db is NOT passed, the fallback SIGNAL_THRESHOLD_DB is used."""
        result = fingerprint_spectrum(fm_psd)
        assert result["signal_threshold_db"] == SIGNAL_THRESHOLD_DB

    def test_custom_threshold_overrides_fallback(self, fm_psd):
        """When signal_threshold_db=4.0 is passed, it is used instead of the fallback."""
        result = fingerprint_spectrum(fm_psd, signal_threshold_db=4.0)
        assert result["signal_threshold_db"] == 4.0

    def test_snr_margin_is_positive_when_above_threshold(self):
        """Synthetic tone with known SNR > threshold produces positive snr_margin_db."""
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
        result = fingerprint_spectrum(psd, signal_threshold_db=5.0)
        assert result["snr_margin_db"] > 0.0
        assert result["snr_margin_db"] == result["snr_db"] - 5.0

    def test_snr_margin_is_negative_when_below_threshold(self):
        """Synthetic tone with threshold above SNR produces negative snr_margin_db."""
        nfft = 2048
        num_chunks = 4
        t = np.arange(nfft * num_chunks)
        tone = np.exp(1j * 2 * np.pi * 10 * t / nfft).astype(np.complex64)
        noise = (np.random.randn(len(t)) * 0.5).astype(np.float32) + \
                1j * (np.random.randn(len(t)) * 0.5).astype(np.float32)
        samples = tone + noise
        psd = compute_psd(
            samples,
            sample_rate_hz=2_000_000,
            center_freq_hz=98_000_000,
            nfft=nfft,
        )
        # Use a very high threshold so the signal is definitely below it
        result = fingerprint_spectrum(psd, signal_threshold_db=50.0)
        assert result["snr_margin_db"] < 0.0
        assert result["snr_margin_db"] == result["snr_db"] - 50.0

    def test_peak_bin_power_db_gte_peak_power_db(self):
        """For a pulsed signal fixture (strong tone in one chunk only, noise in the rest), peak_bin_power_db >= peak_power_db."""
        nfft = 2048
        num_chunks = 4
        num_samples = nfft * num_chunks
        t = np.arange(num_samples)

        # Build a pulsed signal: strong tone only in the first chunk
        chunk_size = nfft
        strong_tone = np.exp(1j * 2 * np.pi * 10 * t[:chunk_size] / nfft).astype(np.complex64) * 0.1
        noise_chunks = (
            (np.random.randn(num_samples - chunk_size) * 0.001).astype(np.float32)
            + 1j * (np.random.randn(num_samples - chunk_size) * 0.001).astype(np.float32)
        )
        samples = np.concatenate([strong_tone, noise_chunks])

        psd = compute_psd(
            samples,
            sample_rate_hz=2_000_000,
            center_freq_hz=98_000_000,
            nfft=nfft,
        )
        result = fingerprint_spectrum(psd)
        assert result["peak_bin_power_db"] >= result["peak_power_db"]

    def test_trace_key_default_matches_psd_db(self, fm_psd):
        """fingerprint_spectrum with default trace_key behaves identically to pre-change."""
        result_default = fingerprint_spectrum(fm_psd)
        result_explicit = fingerprint_spectrum(fm_psd, trace_key='psd_db')
        assert result_default == result_explicit

    def test_trace_key_max_hold_selects_psd_max_hold_db(self):
        """Passing trace_key='psd_max_hold_db' reads the max-hold array from psd_result."""
        freqs = np.linspace(97_000_000, 99_000_000, 2048)
        averaged = np.full(2048, -50.0)
        max_hold = np.full(2048, -30.0)
        psd_result = {
            'frequencies_hz': freqs,
            'psd_db': averaged,
            'psd_max_hold_db': max_hold,
            'center_freq_hz': 98_000_000,
            'sample_rate_hz': 2_000_000,
            'nfft': 2048,
        }
        result_avg = fingerprint_spectrum(psd_result)
        result_max = fingerprint_spectrum(psd_result, trace_key='psd_max_hold_db')
        assert result_avg['peak_power_db'] == -50.0
        assert result_max['peak_power_db'] == -30.0

    def test_missing_trace_key_raises_key_error(self):
        """Passing a trace_key that does not exist in psd_result raises KeyError."""
        psd_result = {
            'frequencies_hz': np.linspace(97_000_000, 99_000_000, 2048),
            'psd_db': np.full(2048, -50.0),
            'center_freq_hz': 98_000_000,
            'sample_rate_hz': 2_000_000,
            'nfft': 2048,
        }
        with pytest.raises(KeyError):
            fingerprint_spectrum(psd_result, trace_key='missing_trace')

    def test_max_hold_trace_reveals_burst_signal(self):
        """A burst visible only in max-hold produces higher bandwidth/occupied_bins/snr than averaged."""
        nfft = 2048
        num_chunks = 125
        sample_rate_hz = 2_000_000
        num_samples = nfft * num_chunks
        t = np.arange(num_samples)

        # ADS-B-like burst: strong PPM tone in a single chunk, noise elsewhere
        burst_start = nfft * 60
        burst_end = burst_start + nfft
        signal = np.zeros(num_samples, dtype=np.complex64)
        signal[burst_start:burst_end] = np.exp(
            1j * 2 * np.pi * 10 * np.arange(nfft) / nfft
        ).astype(np.complex64) * 0.5

        noise = (np.random.randn(num_samples) * 0.05).astype(np.float32) + \
                1j * (np.random.randn(num_samples) * 0.05).astype(np.float32)
        samples = signal + noise

        psd_result = compute_psd(
            samples,
            sample_rate_hz=sample_rate_hz,
            center_freq_hz=1_090_000_000,
            nfft=nfft,
        )

        avg = fingerprint_spectrum(psd_result, signal_threshold_db=5.0)
        max_hold = fingerprint_spectrum(psd_result, signal_threshold_db=5.0, trace_key='psd_max_hold_db')

        assert max_hold['snr_db'] > avg['snr_db']
        assert max_hold['occupied_bins'] >= avg['occupied_bins']
        assert max_hold['bandwidth_hz'] >= avg['bandwidth_hz']

