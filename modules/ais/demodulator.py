"""AIS demodulator — frequency shift, GMSK differential detection, HDLC frame extraction.

Pure-Python DSP using NumPy + SciPy.  No live hardware required.

Legal: passive receive only.  Radiocommunications Act 1992 (Cth).
Jurisdiction: AU / SA.  Authority: ACMA.
"""

import logging

import numpy as np
from scipy import signal

from modules.ais.constants import AIS_BAUD_RATE, CH1_OFFSET_HZ, CH2_OFFSET_HZ

logger = logging.getLogger(__name__)

# Decimation factor: 2 MHz → 50 kHz (clean integer, well above Nyquist for 25 kHz channel)
_DECIMATION_FACTOR = 40
_INTERMEDIATE_RATE = 2_000_000 // _DECIMATION_FACTOR  # 50_000 Hz

# Resample 50 kHz → 48 kHz (5 samples per symbol at 9600 baud)
_RESAMPLE_UP = 24
_RESAMPLE_DOWN = 25
_TARGET_RATE = _INTERMEDIATE_RATE * _RESAMPLE_UP // _RESAMPLE_DOWN  # 48_000 Hz

# FIR low-pass filter for channel isolation after frequency shift
# Cutoff ~10 kHz at 50 kHz sample rate, 64 taps
_FIR_TAPS = 64
_FIR_CUTOFF = 10_000.0 / (_INTERMEDIATE_RATE / 2)  # Normalised cutoff

# Phase-diff low-pass filter cutoff (~6 kHz at 48 kHz)
_PHASE_LP_CUTOFF = 6_000.0 / (_TARGET_RATE / 2)

# CRC-16 CCITT parameters for AIS/HDLC (reflected, init 0xFFFF)
CRC16_REFLECTED_POLY = 0x8408  # 0x1021 reflected


def _crc16_reflected(data: bytes) -> int:
    """Compute CRC-16 CCITT with init 0xFFFF and reflected input."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ CRC16_REFLECTED_POLY
            else:
                crc >>= 1
    return crc & 0xFFFF


def _find_flags_in_nrzi(nrzi_bits: list[int]) -> list[int]:
    """Find HDLC flag positions in the NRZI bit stream.

    A flag is 7 consecutive identical bits followed by a different bit.
    """
    positions: list[int] = []
    run_start = 0
    for i in range(1, len(nrzi_bits)):
        if nrzi_bits[i] != nrzi_bits[i - 1]:
            if i - run_start >= 7:
                positions.append(run_start)
            run_start = i
    return positions


def _nrzi_decode(nrzi_bits: list[int], initial_state: int = 1) -> list[int]:
    """NRZI decode for AIS/HDLC.

    AIS convention: binary 0 = transition, binary 1 = no transition.
    The initial_state is the last bit of the preceding flag and serves as
    the reference for the first data bit.
    """
    decoded: list[int] = []
    prev = initial_state
    for b in nrzi_bits:
        if b == prev:
            decoded.append(1)  # No transition = binary 1
        else:
            decoded.append(0)  # Transition = binary 0
        prev = b
    return decoded


def _remove_bit_stuffing(bits: list[int]) -> list[int]:
    """Remove HDLC zero-bit stuffing after five consecutive 1s."""
    result: list[int] = []
    ones_run = 0
    for b in bits:
        if b == 1:
            ones_run += 1
            result.append(b)
        else:
            if ones_run == 5:
                # This 0 is a stuffed bit — drop it
                ones_run = 0
                continue
            result.append(b)
            ones_run = 0
    return result


def _bits_to_bytes(bits: list[int]) -> bytes:
    """Pack bits into bytes (MSB first)."""
    bytes_: list[int] = []
    for i in range(0, len(bits) - 7, 8):
        byte = 0
        for j in range(8):
            byte |= bits[i + j] << (7 - j)
        bytes_.append(byte)
    return bytes(bytes_)


def _extract_hdlc_frames(nrzi_bits: list[int]) -> list[bytes]:
    """Extract valid HDLC frames from an NRZI bit stream.

    Returns a list of raw payload bytes (one per valid packet found).
    """
    payloads: list[bytes] = []
    flag_positions = _find_flags_in_nrzi(nrzi_bits)

    for start_idx, end_idx in zip(flag_positions, flag_positions[1:]):
        if end_idx - start_idx <= 8:
            continue
        # Extract NRZI bits between flags
        frame_nrzi = nrzi_bits[start_idx + 8 : end_idx]

        # NRZI decode using the last bit of the opening flag as the initial state
        # The flag is [x, x, x, x, x, x, x, y] where y is the last bit
        flag_end = nrzi_bits[start_idx + 7]  # last bit of the opening flag
        decoded_bits = _nrzi_decode(frame_nrzi, initial_state=flag_end)

        # Remove bit stuffing
        decoded_bits = _remove_bit_stuffing(decoded_bits)

        if len(decoded_bits) < 16:
            continue

        frame_bytes = _bits_to_bytes(decoded_bits)
        if len(frame_bytes) < 2:
            continue

        # CRC-16 residual check: CRC over the entire frame (including FCS)
        # should equal 0x0000 for the reflected CRC with init 0xFFFF.
        residual = _crc16_reflected(frame_bytes)
        if residual == 0x0000:
            # FCS is the last 2 bytes — strip them
            payload = frame_bytes[:-2]
            # Sanity check: minimum AIS payload is 3 bytes (HDLC header) + 1 byte
            if len(payload) >= 4:
                payloads.append(payload)

    return payloads


def _demodulate_channel(iq: np.ndarray, sample_rate_hz: float, channel: str) -> list[tuple[bytes, str]]:
    """Demodulate a single AIS channel (already frequency-shifted to baseband).

    Returns:
        List of (payload_bytes, channel) tuples.
    """
    # Guard against very short input that could confuse scipy
    factor = int(sample_rate_hz / _INTERMEDIATE_RATE)
    if len(iq) < factor:
        return []

    if factor <= 1:
        decimated = iq
    else:
        decimated = signal.decimate(iq, factor)

    # Channel isolation low-pass filter
    fir = signal.firwin(_FIR_TAPS, _FIR_CUTOFF)
    filtered = signal.lfilter(fir, 1.0, decimated)

    # GMSK differential phase detection
    phase_diff = np.angle(filtered[1:] * np.conj(filtered[:-1]))

    # Resample to target rate (48 kHz = 5 samples per symbol)
    if len(phase_diff) > 0:
        phase_diff = signal.resample_poly(phase_diff, _RESAMPLE_UP, _RESAMPLE_DOWN)

    # Low-pass filter the phase_diff signal
    phase_fir = signal.firwin(_FIR_TAPS, _PHASE_LP_CUTOFF)
    phase_diff = signal.lfilter(phase_fir, 1.0, phase_diff)

    # Hard-decision threshold at zero
    # Invert the threshold so that the output is the NRZI bits
    # (NRZI: 0 = transition, 1 = no transition)
    nrzi_bits = (phase_diff <= 0).astype(int).tolist()

    # HDLC frame extraction with FCS verification
    payloads = _extract_hdlc_frames(nrzi_bits)
    return [(p, channel) for p in payloads]


class AisDemodulator:
    """Extract AIS HDLC payloads from raw IQ samples."""

    def demodulate(self, iq_chunk: np.ndarray, sample_rate_hz: float) -> list[tuple[bytes, str]]:
        """Demodulate both AIS channels and return valid HDLC payloads.

        Args:
            iq_chunk: Complex64 IQ samples at 162.000 MHz centre.
            sample_rate_hz: Sample rate of the input (typically 2 MHz).

        Returns:
            List of (payload_bytes, channel) tuples, where channel is "A" or "B".
        """
        if len(iq_chunk) == 0:
            return []

        t = np.arange(len(iq_chunk)) / sample_rate_hz
        payloads: list[tuple[bytes, str]] = []

        # Process both channels
        for offset_hz, channel in ((CH1_OFFSET_HZ, "A"), (CH2_OFFSET_HZ, "B")):
            shifted = iq_chunk * np.exp(-2j * np.pi * offset_hz * t)
            channel_payloads = _demodulate_channel(shifted, sample_rate_hz, channel)
            payloads.extend(channel_payloads)

        return payloads
