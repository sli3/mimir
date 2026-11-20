"""
fft.py — Power spectral density computation for the Mimir RF Scanner

Legal: Receive-only. Radiocommunications Act 1992 (Cth).
       No transmission. Jurisdiction: AU/SA. Authority: ACMA.
"""

import logging

import numpy as np

# Default FFT size for spectral analysis
DEFAULT_NFFT: int = 2048

logger = logging.getLogger(__name__)


def compute_psd(
    samples: np.ndarray,
    sample_rate_hz: float,
    center_freq_hz: float,
    nfft: int = DEFAULT_NFFT,
) -> dict:
    """
    Compute power spectral density (PSD) from IQ samples using FFT.

    This function transforms time-domain IQ samples into the frequency domain
    to show how signal power is distributed across frequencies. It applies a
    float32 Hann window to complete chunks and transforms them in one batched
    FFT, averaging their power in float64 for a smoother estimate. Complex64
    samples stay complex64 through the FFT; complex128 samples stay complex128.
    The float32 FFT path introduces small numerical differences from the old
    complex128 path. A trailing partial chunk is discarded after DC removal.

    The output shows absolute frequencies: center_freq_hz plus fftshifted
    fftfreq offsets, from about centre minus sample_rate_hz / 2 up to centre
    plus sample_rate_hz / 2, lowest frequency first.

    Args:
        samples: Array of complex IQ samples. Length must be at least nfft.
                 These are time-domain samples where each element represents
                 one sample point (real and imaginary parts encode amplitude
                 and phase of the RF signal).
        sample_rate_hz: Sample rate in Hz. This determines the frequency
                        resolution and the maximum detectable frequency
                        (Nyquist limit = sample_rate_hz / 2).
        center_freq_hz: Centre frequency at which samples were captured.
                        Used to compute absolute frequencies for each FFT bin.
        nfft: FFT size, must be a power of 2. Default is 2048. Larger values
              give better frequency resolution (e.g., nfft=2048 gives bins
              ~976.6 Hz apart at 2 MHz sample rate) but require more samples.

    Returns:
        Dictionary containing:
          - frequencies_hz: Array of absolute frequencies for each bin
          - psd_db: Power spectral density in dBFS for each frequency
                    (averaged across chunks; correct for continuous signals)
          - psd_max_hold_db: Per-bin maximum power across chunks in dBFS,
                             used for burst signals where averaging would
                             dilute a short transmission
          - center_freq_hz: The centre frequency parameter (passed through)
          - sample_rate_hz: The sample rate parameter (passed through)
          - nfft: FFT size parameter (passed through)
          - num_chunks: Number of chunks that were averaged; 0 on empty-result paths
          - chunk_peak_db: Hottest single-chunk peak power in dBFS before averaging;
                           0.0 on empty-result paths

    Note:
        dBFS is decibels relative to full scale. 0 dBFS represents the ADC
        full-scale (maximum possible digital value). Real signals will be
        significantly below 0 dBFS because a full-scale sinusoid would clip
        the ADC. The Hann window processing loss means a perfectly aligned
        full-scale tone peaks at approximately -1.76 dBFS.
    """
    # Ensure we have enough samples for at least one FFT chunk
    if len(samples) < nfft:
        logger.warning(
            "Number of samples (%d) is less than nfft (%d). Returning empty result.",
            len(samples),
            nfft,
        )
        return {
            "frequencies_hz": np.array([], dtype=np.float64),
            "psd_db": np.array([], dtype=np.float64),
            "psd_max_hold_db": np.array([], dtype=np.float64),
            "center_freq_hz": center_freq_hz,
            "sample_rate_hz": sample_rate_hz,
            "nfft": nfft,
            "num_chunks": 0,
            "chunk_peak_db": 0.0,
        }

    # Remove DC offset (HackRF One produces false spike at centre frequency)
    samples = samples - np.mean(samples)

    # Count complete, non-overlapping chunks of size nfft
    num_chunks = len(samples) // nfft
    if num_chunks == 0:
        logger.warning(
            "Not enough samples to form a complete chunk. Need at least %d.",
            nfft,
        )
        return {
            "frequencies_hz": np.array([], dtype=np.float64),
            "psd_db": np.array([], dtype=np.float64),
            "psd_max_hold_db": np.array([], dtype=np.float64),
            "center_freq_hz": center_freq_hz,
            "sample_rate_hz": sample_rate_hz,
            "nfft": nfft,
            "num_chunks": 0,
            "chunk_peak_db": 0.0,
        }

    # Batch complete chunks; preserve float64 Hann power for normalisation.
    chunks = samples[: num_chunks * nfft].reshape(num_chunks, nfft)
    hann_window = np.hanning(nfft)
    # A float32 window keeps complex64 input on the float32 FFT path, with
    # small rounding differences from the previous complex128 calculation.
    windowed_chunks = chunks * hann_window.astype(np.float32)
    fft_result = np.fft.fft(windowed_chunks, axis=1)
    # Shift only frequency bins, leaving the chunk axis unchanged.
    shifted_fft = np.fft.fftshift(fft_result, axes=1)
    power = np.abs(shifted_fft) ** 2

    # Reduce across chunks and promote to float64 before normalisation.
    averaged_power = power.mean(axis=0, dtype=np.float64)
    max_hold_power = power.max(axis=0).astype(np.float64)
    max_single_chunk_power = float(power.max())

    # Normalise against window power — produces true dBFS referenced to ADC full scale.
    # Dividing by (nfft * window_power) is the standard Welch periodogram normalisation.
    # This replaces the previous /max_power approach which forced peak to 0.0 dBFS and
    # prevented SIGNAL_THRESHOLD_DB from ever being met.
    window_power = np.sum(hann_window ** 2)
    # Compute the hottest single-chunk peak before averaging, in dBFS
    chunk_peak_db = 10 * np.log10(max_single_chunk_power / (nfft * window_power) + 1e-12)
    psd_db = 10 * np.log10(averaged_power / (nfft * window_power) + 1e-12)
    psd_max_hold_db = 10 * np.log10(max_hold_power / (nfft * window_power) + 1e-12)

    # Compute frequency array with absolute frequencies
    # fftfreq gives offsets from 0, fftshift centers them around 0
    freq_offsets = np.fft.fftshift(np.fft.fftfreq(nfft, d=1 / sample_rate_hz))
    # Add center frequency to get absolute frequencies
    frequencies_hz = center_freq_hz + freq_offsets

    logger.debug(
        "Computed PSD: %d chunks averaged over %d frequency bins",
        num_chunks,
        nfft,
    )

    return {
        "frequencies_hz": frequencies_hz,
        "psd_db": psd_db,
        "psd_max_hold_db": psd_max_hold_db,
        "center_freq_hz": center_freq_hz,
        "sample_rate_hz": sample_rate_hz,
        "nfft": nfft,
        "num_chunks": num_chunks,
        "chunk_peak_db": float(chunk_peak_db),
    }
