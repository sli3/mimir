"""
features.py — Spectral feature extraction for the Mimir RF Scanner

Legal: Receive-only. Radiocommunications Act 1992 (Cth).
       No transmission. Jurisdiction: AU/SA. Authority: ACMA.
"""

import logging

import numpy as np

# Percentile used to estimate the noise floor from the PSD
NOISE_FLOOR_PERCENTILE: float = 10.0

# Gap threshold for detecting pulsed or burst signals.
# A gap >= 10 dB between single-chunk peak and averaged peak indicates a
# pulsed or burst signal (e.g. ADS-B). Continuous signals (FM, APRS, AIS)
# will show near-zero gap.
PEAK_BURST_MARGIN_DB: float = 10.0

# Minimum SNR above the noise floor for a bin to be considered a signal.
# Calibrated value. Hardware: HackRF One + telescopic whip SMA antenna
# (~1 GHz optimised). Gain: lna=24 dB / vga=26 dB. Frequency: 98.9 MHz
# (FM Adelaide). Method: tools/diagnose_threshold.py sweep, target 200 kHz
# FM channel width. Result: 24 dB -> 196,289 Hz. Must be re-run if antenna
# or gain settings change.
# NOTE: This is now a conservative fallback. Per-band thresholds live in
# BAND_PROFILES (dashboard/shared_state.py) and are passed via the optional
# signal_threshold_db parameter to fingerprint_spectrum() (Phase 11).
SIGNAL_THRESHOLD_DB: float = 24.0

logger = logging.getLogger(__name__)


def fingerprint_spectrum(
    psd_result: dict,
    signal_threshold_db: float | None = None,
    trace_key: str = 'psd_db',
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
    exceeding the noise floor by at least the effective threshold.

    Args:
        psd_result: Dictionary returned by ``compute_psd`` containing
                    at minimum the keys ``frequencies_hz``, the trace selected
                    by ``trace_key`` (default ``psd_db``), ``center_freq_hz``,
                    ``sample_rate_hz``, and ``nfft``.
        signal_threshold_db: Per-band threshold override. If ``None``,
                             the module-level ``SIGNAL_THRESHOLD_DB``
                             (24.0 dB) is used as the fallback.
        trace_key: Key in ``psd_result`` to use as the input PSD. Default is
                   ``'psd_db'`` (averaged trace, correct for continuous signals).
                   Pass ``'psd_max_hold_db'`` for burst signals such as ADS-B.

    Returns:
        Dictionary containing:
          - center_freq_hz: Centre frequency (passed through)
          - peak_freq_hz: Frequency of the strongest spectral bin
          - peak_power_db: Power at the peak bin (dBFS)
          - noise_floor_db: Estimated noise floor (10th percentile of psd_db)
          - snr_db: Signal-to-noise ratio (peak_power_db - noise_floor_db)
          - bandwidth_hz: Occupied bandwidth above noise floor + effective threshold
          - occupied_bins: Number of bins above noise floor + effective threshold
          - spectral_flatness: Wiener entropy (0.0 = pure tone, 1.0 = white noise)
          - signal_threshold_db: The effective threshold used for this fingerprint
          - snr_margin_db: SNR minus the effective threshold (positive = above threshold)
          - peak_bin_power_db: Maximum peak power seen in any single FFT chunk before
                              averaging, in dBFS. For continuous signals this approximates
                              peak_power_db. For pulsed signals it will be significantly
                              higher (gap >= PEAK_BURST_MARGIN_DB indicates bursty signal).
    """
    psd_db = psd_result[trace_key]

    # Resolve the effective threshold — per-band override or global fallback
    effective_threshold = (
        signal_threshold_db
        if signal_threshold_db is not None
        else SIGNAL_THRESHOLD_DB
    )

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
            "spectral_flatness": 0.0,
            "signal_threshold_db": float(effective_threshold),
            "snr_margin_db": 0.0,
            "peak_bin_power_db": 0.0,
        }

    frequencies_hz = psd_result["frequencies_hz"]
    center_freq_hz = psd_result["center_freq_hz"]
    sample_rate_hz = psd_result["sample_rate_hz"]
    nfft = psd_result["nfft"]

    # Peak bin — the index where psd_db is highest
    peak_idx = int(np.argmax(psd_db))
    peak_freq_hz = float(frequencies_hz[peak_idx])
    peak_power_db = float(psd_db[peak_idx])

    # Peak bin power from single chunk before averaging — fallback to peak_power_db
    # if key absent (for backwards compatibility with synthetic PSD dicts in tests)
    chunk_peak_db = float(psd_result.get("chunk_peak_db", peak_power_db))

    # Noise floor — 10th percentile of all psd_db values
    noise_floor_db = float(np.percentile(psd_db, NOISE_FLOOR_PERCENTILE))

    # Signal-to-noise ratio
    snr_db = float(peak_power_db - noise_floor_db)

    # Bandwidth and occupied bin count
    # Bins are "occupied" when their power exceeds noise floor + effective_threshold dB
    threshold = noise_floor_db + effective_threshold
    occupied_mask = psd_db > threshold
    occupied_bins = int(np.sum(occupied_mask))
    hz_per_bin = sample_rate_hz / nfft
    bandwidth_hz = float(occupied_bins * hz_per_bin)

    # Spectral flatness — Wiener entropy (geometric mean / arithmetic mean)
    # Measures how tone-like vs noise-like a signal is.
    # 0.0 = pure tone, 1.0 = white noise.
    linear_power = np.power(10.0, psd_db / 10.0)
    geometric_mean = np.exp(np.mean(np.log(linear_power + 1e-12)))
    arithmetic_mean = np.mean(linear_power)
    spectral_flatness = float(geometric_mean / (arithmetic_mean + 1e-12))
    spectral_flatness = float(np.clip(spectral_flatness, 0.0, 1.0))

    snr_margin_db = float(snr_db - effective_threshold)

    logger.info(
        "Spectral fingerprint: peak=%.1f Hz, SNR=%.1f dB, BW=%.0f Hz, bins=%d, flatness=%.3f, threshold=%.1f dB",
        peak_freq_hz,
        snr_db,
        bandwidth_hz,
        occupied_bins,
        spectral_flatness,
        effective_threshold,
    )

    return {
        "center_freq_hz": float(center_freq_hz),
        "peak_freq_hz": peak_freq_hz,
        "peak_power_db": peak_power_db,
        "noise_floor_db": noise_floor_db,
        "snr_db": snr_db,
        "bandwidth_hz": bandwidth_hz,
        "occupied_bins": occupied_bins,
        "spectral_flatness": spectral_flatness,
        "signal_threshold_db": float(effective_threshold),
        "snr_margin_db": snr_margin_db,
        "peak_bin_power_db": chunk_peak_db,
    }
