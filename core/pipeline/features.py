"""
features.py — Spectral feature extraction for the Mimir RF Scanner

Legal: Receive-only. Radiocommunications Act 1992 (Cth).
       No transmission. Jurisdiction: AU/SA. Authority: ACMA.
"""

import logging

import numpy as np

# Percentile used to estimate the noise floor from the PSD
NOISE_FLOOR_PERCENTILE: float = 10.0

# Minimum SNR above the noise floor for a bin to be considered a signal
# Calibrated against live FM Adelaide capture (98.9 MHz).
# Value of 27 dB produces ~185 kHz bandwidth — closest to the
# expected ~200 kHz for Australian FM broadcast.
SIGNAL_THRESHOLD_DB: float = 27.0

logger = logging.getLogger(__name__)


def fingerprint_spectrum(
    psd_result: dict,
) -> dict[str, float | int]:
    """
    Extract spectral fingerprint features from a PSD result dictionary.

    This function analyses the power spectral density output from
    ``compute_psd`` to identify the dominant signal, estimate the
    background noise floor, and compute derived metrics such as SNR
    and occupied bandwidth.

    The noise floor is estimated using the 10th percentile of all PSD
    values, which ignores strong signals and gives a stable estimate
    of the background noise level. Signal bins are identified as those
    exceeding the noise floor by at least SIGNAL_THRESHOLD_DB.

    Args:
        psd_result: Dictionary returned by ``compute_psd`` containing
                    at minimum the keys ``frequencies_hz``, ``psd_db``,
                    ``center_freq_hz``, ``sample_rate_hz``, and ``nfft``.

    Returns:
        Dictionary containing:
          - center_freq_hz: Centre frequency (passed through)
          - peak_freq_hz: Frequency of the strongest spectral bin
          - peak_power_db: Power at the peak bin (dBFS)
          - noise_floor_db: Estimated noise floor (10th percentile of psd_db)
          - snr_db: Signal-to-noise ratio (peak_power_db - noise_floor_db)
          - bandwidth_hz: Occupied bandwidth above noise floor + SIGNAL_THRESHOLD_DB
          - occupied_bins: Number of bins above noise floor + SIGNAL_THRESHOLD_DB
    """
    psd_db = psd_result["psd_db"]

    # Edge case: empty PSD — not enough samples were captured
    if len(psd_db) == 0:
        logger.warning("Empty psd_db received — returning zeroed fingerprint.")
        return {
            "center_freq_hz": psd_result.get("center_freq_hz", 0.0),
            "peak_freq_hz": 0.0,
            "peak_power_db": 0.0,
            "noise_floor_db": 0.0,
            "snr_db": 0.0,
            "bandwidth_hz": 0.0,
            "occupied_bins": 0,
        }

    frequencies_hz = psd_result["frequencies_hz"]
    center_freq_hz = psd_result["center_freq_hz"]
    sample_rate_hz = psd_result["sample_rate_hz"]
    nfft = psd_result["nfft"]

    # Peak bin — the index where psd_db is highest
    peak_idx = int(np.argmax(psd_db))
    peak_freq_hz = float(frequencies_hz[peak_idx])
    peak_power_db = float(psd_db[peak_idx])

    # Noise floor — 10th percentile of all psd_db values
    noise_floor_db = float(np.percentile(psd_db, NOISE_FLOOR_PERCENTILE))

    # Signal-to-noise ratio
    snr_db = float(peak_power_db - noise_floor_db)

    # Bandwidth and occupied bin count
    # Bins are "occupied" when their power exceeds noise floor + 3 dB
    threshold = noise_floor_db + SIGNAL_THRESHOLD_DB
    occupied_mask = psd_db > threshold
    occupied_bins = int(np.sum(occupied_mask))
    hz_per_bin = sample_rate_hz / nfft
    bandwidth_hz = float(occupied_bins * hz_per_bin)

    logger.info(
        "Spectral fingerprint: peak=%.1f Hz, SNR=%.1f dB, BW=%.0f Hz, bins=%d",
        peak_freq_hz,
        snr_db,
        bandwidth_hz,
        occupied_bins,
    )

    return {
        "center_freq_hz": float(center_freq_hz),
        "peak_freq_hz": peak_freq_hz,
        "peak_power_db": peak_power_db,
        "noise_floor_db": noise_floor_db,
        "snr_db": snr_db,
        "bandwidth_hz": bandwidth_hz,
        "occupied_bins": occupied_bins,
    }
