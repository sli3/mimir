"""Tests for AcarsDemodulator — synthetic signal generation, no live hardware."""

import numpy as np

from modules.acars.demodulator import AcarsDemodulator


class TestAcarsDemodulator:
    def setup_method(self):
        self.demod = AcarsDemodulator()

    def test_envelope_detect_returns_magnitude(self):
        """Envelope of a pure carrier is the amplitude."""
        iq = np.array([1.0 + 0j, 0.0 + 1j, -1.0 + 0j])
        env = self.demod.envelope_detect(iq)
        assert np.allclose(np.abs(env[0]), 0.0, atol=1e-6)
        assert np.allclose(np.abs(env[1]), 0.0, atol=1e-6)
        assert np.allclose(np.abs(env[2]), 0.0, atol=1e-6)
        # After DC removal and normalisation the envelope is zero-mean
        assert np.isclose(np.mean(env), 0.0, atol=1e-6)

    def test_envelope_detect_removes_dc(self):
        """A constant-amplitude signal has zero mean after DC removal."""
        t = np.linspace(0, 1, 100_000)
        iq = np.exp(2j * np.pi * 100 * t)
        env = self.demod.envelope_detect(iq)
        assert np.isclose(np.mean(env), 0.0, atol=1e-6)

    def test_envelope_detect_normalises(self):
        """Standard deviation of the normalised envelope is 1.0."""
        t = np.linspace(0, 1, 1_000)
        iq = (1.0 + 0.3 * np.sin(2 * np.pi * 5 * t)) * np.exp(2j * np.pi * 100_000 * t)
        env = self.demod.envelope_detect(iq)
        assert np.isclose(np.std(env), 1.0, atol=1e-6)

    def test_decimate_reduces_sample_count(self):
        """Decimating by 41 from 2 MHz to ~48.8 kHz reduces length."""
        envelope = np.ones(82_000)
        audio = self.demod.decimate_to_audio(envelope, 2_000_000.0)
        assert len(audio) < len(envelope)

    def test_decimate_output_length_correct_for_2mhz_input(self):
        """Exact output length for 2 MHz -> 48 kHz decimation."""
        factor = int(2_000_000 / 48_000)
        envelope = np.ones(factor * 100)
        audio = self.demod.decimate_to_audio(envelope, 2_000_000.0, 48_000.0)
        assert len(audio) == 100

    def test_detect_tones_2400hz_returns_no_change(self):
        """A pure 2400 Hz tone at 48 kHz decides all 1s (no-change)."""
        audio_rate = 48_000.0
        baud_rate = 2_400.0
        bit_samples = int(audio_rate / baud_rate)
        duration = 20 * bit_samples / audio_rate
        t = np.linspace(0, duration, 20 * bit_samples, endpoint=False)
        audio = np.sin(2 * np.pi * 2_400.0 * t)
        decisions = self.demod.detect_tones(audio, audio_rate, baud_rate)
        assert all(d == 1 for d in decisions)

    def test_detect_tones_1200hz_returns_toggle(self):
        """A pure 1200 Hz tone at 48 kHz decides all 0s (toggle)."""
        audio_rate = 48_000.0
        baud_rate = 2_400.0
        bit_samples = int(audio_rate / baud_rate)
        duration = 20 * bit_samples / audio_rate
        t = np.linspace(0, duration, 20 * bit_samples, endpoint=False)
        # Use cosine to align window peaks with tone peaks
        audio = np.cos(2 * np.pi * 1_200.0 * t)
        decisions = self.demod.detect_tones(audio, audio_rate, baud_rate)
        assert all(d == 0 for d in decisions)

    def test_nrzi_decode_alternating_toggles(self):
        """Alternating 0 tones flip the bit every symbol."""
        tones = [0, 0, 0, 0]
        bits = self.demod.nrzi_decode(tones)
        # Initial bit=1, each tone=0 toggles: 1->0->1->0->1
        assert bits == [0, 1, 0, 1]

    def test_nrzi_decode_all_same(self):
        """All 1 tones keep the bit constant."""
        tones = [1, 1, 1, 1]
        bits = self.demod.nrzi_decode(tones)
        assert bits == [1, 1, 1, 1]

    def test_nrzi_decode_known_sequence(self):
        """A mixed tone sequence yields the expected bit pattern."""
        tones = [1, 0, 1, 0, 0, 1, 1, 0]
        bits = self.demod.nrzi_decode(tones)
        # 1 -> keep 1, 0 -> toggle, 1 -> keep, 0 -> toggle, 0 -> toggle, 1 -> keep, 1 -> keep, 0 -> toggle
        assert bits == [1, 0, 0, 1, 0, 0, 0, 1]
