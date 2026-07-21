"""ACARS demodulator — AM envelope detection, decimation, FFSK tone detection, NRZI decode.

All DSP is pure Python + NumPy + SciPy.  No live hardware required.

Legal: passive receive only.  Radiocommunications Act 1992 (Cth).
Jurisdiction: AU / SA.  Authority: ACMA.
"""

import logging
from functools import reduce

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

    def _stage_factors(self, factor: int) -> list[int]:
        """Split a decimation factor into IIR-safe stages (each <= 13).

        SciPy's ``signal.decimate`` uses an IIR anti-alias filter that is only
        numerically stable when the decimation factor per call is 13 or less.
        A single-stage factor above 13 destroys the anti-alias filter and
        mangles the signal. Multiple sequential calls keep each stage within
        the safe range.

        This method returns a list of integer stage factors whose product
        equals ``factor`` whenever possible, using a greedy largest-first
        trial division in the range 2..13. If ``factor`` has a prime factor
        above 13 (e.g. 41), exact factorisation is impossible; the method then
        scans downward from ``factor - 1`` for the largest candidate that can
        be factorised entirely into stages of 2..13, and returns those stages.
        The resulting product may be slightly below ``factor``; the shortfall
        is absorbed by the returned actual audio rate so downstream callers
        use the true achieved sample rate.

        Structural invariant: no returned stage ever exceeds 13.

        Examples:
            - factor=40 returns [10, 4] (product 40, exact)
            - factor=41 returns [10, 4] (product 40, prime factor 41 forces a
              slight shortfall)
        """
        if factor <= 1:
            return []

        def _exact_split(value: int) -> list[int] | None:
            """Greedily peel divisors in 2..13 (largest first) off ``value``.

            Returns the stage list when the factorisation is exact, or
            ``None`` when ``value`` has a prime factor above 13.
            """
            stages: list[int] = []
            remainder = value
            for divisor in range(13, 1, -1):
                while remainder % divisor == 0:
                    stages.append(divisor)
                    remainder //= divisor
            return stages if remainder == 1 else None

        stages = _exact_split(factor)
        if stages is not None:
            return stages
        # factor has a prime factor above 13 (e.g. 41): fall back to the
        # largest achievable product at or below factor using only
        # IIR-safe stages, and let the actual achieved rate propagate.
        for candidate in range(factor - 1, 1, -1):
            stages = _exact_split(candidate)
            if stages is not None:
                return stages
        return []

    def decimate_to_audio(
        self,
        envelope: np.ndarray,
        input_sample_rate: float,
        target_audio_rate: float = 50_000.0,
    ) -> tuple[np.ndarray, float]:
        """Down-sample an AM envelope to approximately ``target_audio_rate``.

        The decimation is performed in multiple IIR-safe stages (each factor
        <= 13) via SciPy's ``signal.decimate``. Because the stage factors are
        chosen by integer trial division, the achieved rate may differ
        slightly from the nominal target when the input sample rate is not
        exactly divisible by the target (e.g. a prime factor > 13 forces a
        fallback product that is a few kHz below the target).

        The returned actual audio rate is ``input_sample_rate / product(stages)``
        — this is the rate downstream tone detection must use for correlation,
        not the nominal target. Callers such as ``AcarsSubscriber._decode_loop``
        pass the returned rate to ``detect_tones``, which computes per-symbol
        windows from it.

        Default target rationale: 50 kHz is chosen because 2 MHz / 50 kHz = 40,
        and 40 factorises exactly into IIR-safe stages (10 x 4). A 48 kHz
        target would imply a factor of 41 (prime), which falls back to product
        40 anyway, yielding the same 50 kHz actual rate. Fifty kilohertz is
        therefore the natural default for a 2 MHz input.

        Returns:
            A ``(signal, rate)`` tuple where ``signal`` is the decimated
            envelope array and ``rate`` is the true achieved sample rate in Hz.
        """
        factor = int(input_sample_rate / target_audio_rate)
        if factor <= 1:
            return envelope, input_sample_rate
        stages = self._stage_factors(factor)
        decimated = envelope
        for stage in stages:
            decimated = signal.decimate(decimated, stage)
        product = reduce(lambda a, b: a * b, stages, 1)
        return decimated, input_sample_rate / product

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
