"""ADS-B demodulator — amplitude-only preamble detection and PPM bit extraction.

All DSP is pure Python + NumPy.  No live hardware required.

ADS-B uses Pulse Position Modulation (PPM) at 1 Mbit/s on a 1090 MHz carrier.
At 2 MSa/s each bit period is 2 samples; the first half is chip A and the
second half is chip B.  A bit is 1 if chip A is the larger pulse, 0 if chip
B is larger.

Legal: passive receive only.  Radiocommunications Act 1992 (Cth).
Jurisdiction: AU / SA.  Authority: ACMA.
"""

import logging

import numpy as np

from modules.adsb.constants import (
    DATA_BITS,
    MESSAGE_SAMPLES,
    PREAMBLE_HIGH_INDICES,
    PREAMBLE_LOW_INDICES,
    PREAMBLE_SAMPLES,
    PREAMBLE_THRESHOLD,
)

logger = logging.getLogger(__name__)


class AdsbDemodulator:
    """Extract ADS-B Mode S extended squitter frames from raw IQ samples."""

    def demodulate(self, iq_chunk: np.ndarray) -> list[str]:
        """Convert an IQ chunk into a list of candidate ADS-B hex strings.

        The demodulator is intentionally simple: it scans the amplitude
        envelope for the 8 us ADS-B preamble and then extracts 112 PPM
        bits.  CRC validation is left to the decoder.

        Args:
            iq_chunk: Complex64 IQ samples.

        Returns:
            List of 28-character hex strings (one per candidate frame).
        """
        if len(iq_chunk) < MESSAGE_SAMPLES:
            return []

        mag = np.abs(iq_chunk).astype(np.float32)
        frames: list[str] = []

        # Vectorised preamble high/low extraction.  For each candidate
        # starting sample i we need the mean of the high indices and the
        # mean of the low indices in mag[i:i+PREAMBLE_SAMPLES].  We build
        # two shifted views and then sweep with a 1-D convolution.
        high_sum = np.zeros(len(mag), dtype=np.float32)
        low_sum = np.zeros(len(mag), dtype=np.float32)
        for idx in PREAMBLE_HIGH_INDICES:
            high_sum[:-idx or None] += mag[idx:]
        for idx in PREAMBLE_LOW_INDICES:
            low_sum[:-idx or None] += mag[idx:]

        high_mean = high_sum / len(PREAMBLE_HIGH_INDICES)
        low_mean = low_sum / len(PREAMBLE_LOW_INDICES)

        # Valid preamble region: low_mean > 0 and ratio >= threshold.
        ratio = np.divide(
            high_mean,
            low_mean,
            out=np.zeros_like(high_mean),
            where=low_mean > 1e-12,
        )
        candidates = np.where(
            (low_mean > 1e-12) & (ratio >= PREAMBLE_THRESHOLD)
        )[0]

        # Skip candidates that overlap an already-decoded frame.
        last_end = -1
        for i in candidates:
            if i < last_end:
                continue
            if i + MESSAGE_SAMPLES > len(mag):
                continue

            bits = self._extract_bits(mag, i)
            hex_str = self._bits_to_hex(bits)
            if hex_str is not None:
                frames.append(hex_str)
                last_end = i + MESSAGE_SAMPLES

        return frames

    def _extract_bits(self, mag: np.ndarray, start: int) -> list[int]:
        """Extract 112 PPM bits starting immediately after the preamble.

        Args:
            mag: Amplitude envelope.
            start: Sample index where the preamble begins.

        Returns:
            List of 112 bits (0/1).
        """
        data = mag[start + PREAMBLE_SAMPLES : start + MESSAGE_SAMPLES]
        bits: list[int] = []
        for k in range(DATA_BITS):
            chip_a = data[k * 2]
            chip_b = data[k * 2 + 1]
            bits.append(1 if chip_a > chip_b else 0)
        return bits

    def _bits_to_hex(self, bits: list[int]) -> str | None:
        """Pack 112 bits into 14 bytes and return as a 28-char hex string.

        Args:
            bits: List of 0/1 bits, length 112.

        Returns:
            Lowercase hex string, or None if the bit count is wrong.
        """
        if len(bits) != DATA_BITS:
            return None
        byte_vals = []
        for i in range(0, DATA_BITS, 8):
            byte = 0
            for j in range(8):
                byte |= bits[i + j] << (7 - j)
            byte_vals.append(byte)
        return bytes(byte_vals).hex()
