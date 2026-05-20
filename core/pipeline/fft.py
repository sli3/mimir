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
    Hann window to reduce spectral leakage, splits samples into chunks, and
    averages the power across all chunks for a smoother estimate.

    The output shows absolute frequencies (not offsets from center), starting
    from 0 Hz up to the Nyquist frequency (sample_rate_hz / 2).

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
              ~97.6 Hz apart at 2 MHz sample rate) but require more samples.

    Returns:
        Dictionary containing:
          - frequencies_hz: Array of absolute frequencies for each bin
          - psd_db: Power spectral density in dBFS for each frequency
          - center_freq_hz: The centre frequency parameter (passed through)
          - sample_rate_hz: The sample rate parameter (passed through)
          - nfft: FFT size parameter (passed through)
          - num_chunks: Number of chunks that were averaged

    Note:
        dBFS is decibels relative to full scale. 0 dBFS = maximum possible
        digital value. Negative values indicate power below full scale.
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
            "center_freq_hz": center_freq_hz,
            "sample_rate_hz": sample_rate_hz,
            "nfft": nfft,
            "num_chunks": 0,
        }

    # Split samples into non-overlapping chunks of size nfft
    num_chunks = len(samples) // nfft
    if num_chunks == 0:
        logger.warning(
            "Not enough samples to form a complete chunk. Need at least %d.",
            nfft,
        )
        return {
            "frequencies_hz": np.array([], dtype=np.float64),
            "psd_db": np.array([], dtype=np.float64),
            "center_freq_hz": center_freq_hz,
            "sample_rate_hz": sample_rate_hz,
            "nfft": nfft,
            "num_chunks": 0,
        }

    # Apply Hann window to each chunk to reduce spectral leakage
    hann_window = np.hanning(nfft)

    chunk_psd_list = []
    for i in range(num_chunks):
        chunk = samples[i * nfft : (i + 1) * nfft]
        # Apply window and FFT
        windowed_chunk = chunk * hann_window
        fft_result = np.fft.fft(windowed_chunk)
        # Shift so DC component is centered
        shifted_fft = np.fft.fftshift(fft_result)
        # Compute magnitude squared (power)
        power = np.abs(shifted_fft) ** 2
        chunk_psd_list.append(power)

    # Average across all chunks
    averaged_power = np.mean(chunk_psd_list, axis=0)

    # Normalize by maximum power and convert to dBFS (decibels relative to full scale)
    max_power = np.max(averaged_power)
    psd_db = 10 * np.log10(averaged_power / max_power + 1e-12)

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
        "center_freq_hz": center_freq_hz,
        "sample_rate_hz": sample_rate_hz,
        "nfft": nfft,
        "num_chunks": num_chunks,
    }
