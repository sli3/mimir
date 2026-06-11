"""ACARS demodulator — AM envelope detection, decimation, FFSK tone detection, NRZI decode.

All DSP is pure Python + NumPy + SciPy.  No live hardware required.

Legal: passive receive only.  Radiocommunications Act 1992 (Cth).
Jurisdiction: AU / SA.  Authority: ACMA.
"""

import logging

import numpy as np
from scipy import signal

logger = logging.getLogger(__name__)


class AcarsDemodulator:
    """Extract ACARS bit stream from raw IQ samples."""

    def envelope_detect(self, iq_chunk: np.ndarray) -> np.ndarray:
        """Return AM envelope (magnitude) with DC removed and normalised.

        Args:
            iq_chunk: Complex64 IQ samples from the SDR.

        Returns:
            Normalised real envelope array.
        """
        envelope = np.abs(iq_chunk)
        envelope = envelope - np.mean(envelope)
        std = np.std(envelope)
        if std > 1e-12:
            envelope = envelope / std
        return envelope

    def decimate_to_audio(
        self,
        envelope: np.ndarray,
        input_sample_rate: float,
        target_audio_rate: float = 48_000.0,
    ) -> np.ndarray:
        """Down-sample envelope to audio rate suitable for tone detection.

        Args:
            envelope: AM envelope samples at ``input_sample_rate``.
            input_sample_rate: Sample rate of the input envelope (Hz).
            target_audio_rate: Desired output rate (Hz).  Default 48 kHz.

        Returns:
            Decimated envelope at ``target_audio_rate``.
        """
        factor = int(input_sample_rate / target_audio_rate)
        if factor <= 1:
            return envelope
        return signal.decimate(envelope, factor)

    def detect_tones(
        self,
        audio: np.ndarray,
        audio_rate: float = 48_000.0,
        baud_rate: float = 2_400.0,
    ) -> list[int]:
        """Correlate audio with 1200 Hz and 2400 Hz references to decide bits.

        Args:
            audio: Audio-rate envelope samples.
            audio_rate: Sample rate of ``audio`` (Hz).
            baud_rate: ACARS symbol rate (Hz).  Default 2400.

        Returns:
            List of tone decisions (0 = 1200 Hz wins, 1 = 2400 Hz wins).
        """
        bit_samples = int(audio_rate / baud_rate)
        decisions: list[int] = []
        for i in range(0, len(audio) - bit_samples + 1, bit_samples):
            window = audio[i : i + bit_samples]
            n = len(window)
            t = np.arange(n) / audio_rate
            corr_1200_sin = np.sum(window * np.sin(2.0 * np.pi * 1_200.0 * t))
            corr_1200_cos = np.sum(window * np.cos(2.0 * np.pi * 1_200.0 * t))
            energy_1200 = corr_1200_sin ** 2 + corr_1200_cos ** 2
            corr_2400_sin = np.sum(window * np.sin(2.0 * np.pi * 2_400.0 * t))
            corr_2400_cos = np.sum(window * np.cos(2.0 * np.pi * 2_400.0 * t))
            energy_2400 = corr_2400_sin ** 2 + corr_2400_cos ** 2
            decisions.append(0 if energy_1200 > energy_2400 else 1)
        return decisions

    def nrzi_decode(self, tone_decisions: list[int]) -> list[int]:
        """Decode NRZI tone decisions into raw data bits.

        NRZI rule: a tone change (1200 Hz) toggles the current bit;
        no change (2400 Hz) keeps it the same.

        Args:
            tone_decisions: List of 0/1 from ``detect_tones``.

        Returns:
            List of decoded 0/1 bits.
        """
        bits: list[int] = []
        bit = 1
        for tone in tone_decisions:
            if tone == 0:
                bit ^= 1
            bits.append(bit)
        return bits
