"""Tests for AcarsDemodulator — synthetic signal generation, no live hardware."""

from functools import reduce

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
        """Staged decimation from 2 MHz to 50 kHz reduces length."""
        envelope = np.ones(82_000)
        audio, audio_rate = self.demod.decimate_to_audio(envelope, 2_000_000.0)
        assert len(audio) < len(envelope)
        assert isinstance(audio_rate, float)
        assert audio_rate > 0.0

    def test_decimate_output_length_correct_for_2mhz_input(self):
        """Exact output length for 2 MHz -> 50 kHz decimation (factor 40)."""
        factor = int(2_000_000 / 50_000)  # 40 = 8 x 5 (or 10 x 4), IIR-safe
        envelope = np.ones(factor * 100)
        audio, audio_rate = self.demod.decimate_to_audio(
            envelope, 2_000_000.0
        )
        assert len(audio) == 100
        # Factor 40 splits exactly, so the actual rate is the target rate.
        assert audio_rate == 2_000_000.0 / 40
        assert audio_rate == 50_000.0

    def test_decimate_48khz_target_prime_fallback(self):
        """Explicit 48 kHz target: factor 41 is prime, so stages fall back
        to the nearest achievable product <= 41 (all stages <= 13) and the
        actual rate propagates instead of matching 48 kHz exactly."""
        envelope = np.ones(4_100)
        audio, audio_rate = self.demod.decimate_to_audio(
            envelope, 2_000_000.0, 48_000.0
        )
        # Product of stages must be <= 41, so the achieved rate is above
        # the 48 kHz target rather than below it.
        assert audio_rate != 48_000.0
        assert audio_rate > 48_000.0
        assert len(audio) < len(envelope)

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


class TestStageFactors:
    """Tests for AcarsDemodulator._stage_factors — IIR-safe decimation splits."""

    def setup_method(self):
        self.demod = AcarsDemodulator()

    @staticmethod
    def _product(stages: list[int]) -> int:
        return reduce(lambda a, b: a * b, stages, 1)

    def test_factor_one_or_less_returns_empty(self):
        """No decimation needed at or below the target rate."""
        assert self.demod._stage_factors(1) == []
        assert self.demod._stage_factors(0) == []
        assert self.demod._stage_factors(-5) == []

    def test_factor_40_splits_exactly(self):
        """40 (2 MHz -> 50 kHz) factorises exactly with all stages <= 13."""
        stages = self.demod._stage_factors(40)
        assert self._product(stages) == 40
        assert all(s <= 13 for s in stages)

    def test_factor_13_splits_exactly(self):
        """13 is itself IIR-safe, so a single stage suffices."""
        stages = self.demod._stage_factors(13)
        assert self._product(stages) == 13
        assert all(s <= 13 for s in stages)

    def test_factor_41_prime_fallback(self):
        """41 is prime and > 13: no exact split exists, so the fallback
        must return stages with product <= 41 and no stage above 13."""
        stages = self.demod._stage_factors(41)
        assert len(stages) >= 1
        assert self._product(stages) <= 41
        assert all(s <= 13 for s in stages)

    def test_factor_100_splits_exactly(self):
        """100 = 10 x 10 factorises exactly with all stages <= 13."""
        stages = self.demod._stage_factors(100)
        assert self._product(stages) == 100
        assert all(s <= 13 for s in stages)

    def test_factor_14_splits_exactly(self):
        """14 is the smallest factor above 13 with an exact safe split."""
        stages = self.demod._stage_factors(14)
        assert self._product(stages) == 14
        assert all(s <= 13 for s in stages)

    def test_no_stage_ever_exceeds_13(self):
        """Structural invariant: every returned stage is IIR-safe."""
        for factor in range(1, 200):
            stages = self.demod._stage_factors(factor)
            assert not stages or max(stages) <= 13

    def test_product_divides_or_falls_below_factor(self):
        """The product equals the factor when an exact split exists;
        the prime-fallback case (e.g. 41) yields a product <= factor."""
        for factor in range(2, 200):
            stages = self.demod._stage_factors(factor)
            product = self._product(stages)
            assert product <= factor
            assert factor % product == 0 or product < factor
