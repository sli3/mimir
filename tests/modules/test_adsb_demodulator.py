"""Tests for AdsbDemodulator — preamble detection and bit extraction."""

import numpy as np

from modules.adsb.constants import (
    DATA_BITS,
    MESSAGE_SAMPLES,
    PREAMBLE_HIGH_INDICES,
    PREAMBLE_LOW_INDICES,
    PREAMBLE_SAMPLES,
)
from modules.adsb.demodulator import AdsbDemodulator


class TestAdsbDemodulator:
    def test_empty_chunk_returns_no_frames(self):
        """A zero-valued chunk produces no frames."""
        demod = AdsbDemodulator()
        result = demod.demodulate(np.zeros(256, dtype=np.complex64))
        assert result == []

    def test_chunk_shorter_than_message_returns_no_frames(self):
        """A chunk shorter than 240 samples cannot hold a full message."""
        demod = AdsbDemodulator()
        result = demod.demodulate(np.zeros(100, dtype=np.complex64))
        assert result == []

    def test_preamble_detection_synthetic(self):
        """A synthetic preamble + alternating data yields one 28-char hex string."""
        demod = AdsbDemodulator()

        # Build a quiet baseline so only the intended preamble fires.
        chunk = np.full(1024, 0.2, dtype=np.float32)

        # Preamble: high indices at 1.0, low indices at 0.2.
        chunk[list(PREAMBLE_HIGH_INDICES)] = 1.0
        chunk[list(PREAMBLE_LOW_INDICES)] = 0.2

        # Data bits: alternating 1/0 pattern using chip_a/chip_b levels.
        data_start = PREAMBLE_SAMPLES
        for k in range(DATA_BITS):
            if k % 2 == 0:
                # bit 1: chip_a > chip_b
                chunk[data_start + k * 2] = 0.8
                chunk[data_start + k * 2 + 1] = 0.2
            else:
                # bit 0: chip_a < chip_b
                chunk[data_start + k * 2] = 0.2
                chunk[data_start + k * 2 + 1] = 0.8

        # Convert to complex IQ (imaginary part is irrelevant for amplitude demod).
        iq = chunk.astype(np.float32) + 0j
        result = demod.demodulate(iq)

        assert len(result) == 1
        assert len(result[0]) == 28

    def test_no_preamble_in_noise(self):
        """Gaussian noise should not produce many false preamble matches."""
        demod = AdsbDemodulator()
        rng = np.random.default_rng(42)
        mag = rng.normal(0.5, 0.1, 2000).astype(np.float32)
        mag = np.clip(mag, 0.01, None)
        iq = mag + 0j
        result = demod.demodulate(iq)
        # Noise can occasionally line up; tolerate a handful of false positives.
        assert len(result) <= 3

    def test_bit_extraction_bit_one(self):
        """chip_a > chip_b should decode to bit 1."""
        demod = AdsbDemodulator()
        mag = np.full(MESSAGE_SAMPLES, 0.2, dtype=np.float32)
        mag[PREAMBLE_SAMPLES + 0] = 1.0  # chip_a
        mag[PREAMBLE_SAMPLES + 1] = 0.2  # chip_b
        bits = demod._extract_bits(mag, 0)
        assert bits[0] == 1

    def test_bit_extraction_bit_zero(self):
        """chip_a < chip_b should decode to bit 0."""
        demod = AdsbDemodulator()
        mag = np.full(MESSAGE_SAMPLES, 0.2, dtype=np.float32)
        mag[PREAMBLE_SAMPLES + 0] = 0.2  # chip_a
        mag[PREAMBLE_SAMPLES + 1] = 1.0  # chip_b
        bits = demod._extract_bits(mag, 0)
        assert bits[0] == 0
