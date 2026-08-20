"""
features.py — Spectral feature extraction for the Mimir RF Scanner

Legal: Receive-only. Radiocommunications Act 1992 (Cth).
       No transmission. Jurisdiction: AU/SA. Authority: ACMA.
"""

import logging

import numpy as np

# Percentile used to estimate the noise floor from the PSD
NOISE_FLOOR_PERCENTILE: float = 10.0

# Burst-detection margin (Phase 45). This is the measured margin above the
# statistical noise floor of the per-bin max-hold ratio (max-hold power minus
# averaged power at the peak bin, in dB). For pure Gaussian noise the expected
# ratio over N chunks is 10*log10(ln(N) + 0.5772) — only an excess beyond this
# margin is flagged as a genuine burst.
# Validation: 127 MHz aviation band capture, 2026-07. At 976 chunks the
# measured burst_ratio_db was 8.97 dB against an expected_noise_ratio_db of
# 8.73 dB — an excess of 0.25 dB, i.e. no burst. With the 6.0 dB margin this
# is correctly suppressed. Continuous signals (FM and other continuous
# carriers) stay well below the margin.
# TODO(tech-debt TD-45-1): This margin sets a conservative duty-cycle ceiling of
# ~3.4% at 976 chunks, which may suppress the tag on heavy multi-aircraft ADS-B
# traffic. Not yet validated against real ADS-B.
# TODO(tech-debt TD-46-1): The Phase 46 wide-window burst metric is FM-only,
# gated per-band by the ``burst_use_wide_window`` BAND_PROFILES key. Attempt 1
# (np.max of per-bin max-hold/average gaps across the window) was proven
# mathematically incapable of suppressing the FM false positive and was rolled
# back without a commit. The surviving power-sum approach inherits a second
# unknown: expected_noise_ratio_db (10*log10(ln(N)+0.5772)) was derived for
# single-bin max-hold behaviour and has NOT been re-derived for the multi-bin
# power-sum case. The 6.0 dB BURST_MARGIN_DB margin is unvalidated for this
# new metric and may need retuning once live FM data is checked.
BURST_MARGIN_DB: float = 6.0

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
    crop_half_width_hz: float | None = None,
    burst_use_wide_window: bool = False,
) -> dict[str, float | int | bool]:
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
        crop_half_width_hz: Per-band crop window half-width in Hz. When set,
                            peak search (``peak_freq_hz`` / ``peak_power_db``)
                            and occupied-bin counting (``occupied_bins`` /
                            ``bandwidth_hz``) are restricted to bins within
                            ``+/- crop_half_width_hz`` of ``center_freq_hz``.
                            This prevents a second, off-centre signal in the
                            same 2 MHz capture span from contaminating the
                            reported bandwidth or stealing the peak bin
                            (Phase 30). When ``None`` (default), full-span
                            behaviour is preserved — identical to pre-Phase 30.
                            The noise floor is ALWAYS computed on the full,
                            uncropped ``psd_db`` so a narrow window does not
                            bias it upward.
        burst_use_wide_window: When True AND ``crop_half_width_hz`` is not None,
                               the burst metric is computed by summing linear power
                               across all bins in the crop window for both the
                               max-hold and averaged traces, then expressing the
                               ratio in dB. This distinguishes
                               continuous-but-frequency-agile signals (e.g. FM with
                               a carrier sweep wider than the per-bin dwell time)
                               from genuine time-bursty signals (e.g. ADS-B
                               squitters). When False (default), the single-bin
                               narrow metric is used. Default False preserves
                               byte-identical Phase 45 behaviour for every band
                               that does not explicitly opt in via its BAND_PROFILES
                               entry.

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
                               higher. Retained unchanged for backwards compatibility with
                               downstream consumers — only the burst DECISION has moved to
                               the new keys below (Phase 45).
          - burst_ratio_db: psd_max_hold_db[peak_idx] - psd_db[peak_idx] at the peak bin,
                            in dB. For pure noise this approximates the statistical
                            max-over-chunks gap; a genuine burst sits far above it.
          - expected_noise_ratio_db: Statistical expectation of burst_ratio_db for pure
                            Gaussian noise over num_chunks chunks:
                            10*log10(ln(num_chunks) + 0.5772), where 0.5772 is the
                            Euler-Mascheroni constant. 0.0 when num_chunks < 2 (a single
                            chunk has no max-hold meaning).
          - burst_excess_db: burst_ratio_db - expected_noise_ratio_db. Positive values
                            indicate more max-hold excursion than noise alone explains.
          - is_burst: True only when burst_excess_db > BURST_MARGIN_DB. Always False
                            when num_chunks < 2 or psd_max_hold_db is unavailable.
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
            "burst_ratio_db": 0.0,
            "expected_noise_ratio_db": 0.0,
            "burst_excess_db": 0.0,
            "is_burst": False,
        }

    frequencies_hz = psd_result["frequencies_hz"]
    center_freq_hz = psd_result["center_freq_hz"]
    sample_rate_hz = psd_result["sample_rate_hz"]
    nfft = psd_result["nfft"]

    # Crop mask (Phase 30) — restrict peak search and occupied-bin counting
    # to a per-band window around the tuned centre frequency. The noise
    # floor calculation further down still uses the full, uncropped psd_db
    # — a narrow window would bias it upward since it would be dominated
    # by signal-adjacent bins, not by open noise.
    crop_mask = None
    if crop_half_width_hz is not None:
        crop_mask = np.abs(frequencies_hz - center_freq_hz) <= crop_half_width_hz
        if not np.any(crop_mask):
            logger.warning(
                "crop_half_width_hz=%.1f Hz selected zero bins around centre "
                "%.1f Hz — returning zeroed fingerprint",
                crop_half_width_hz,
                center_freq_hz,
            )
            return {
                "center_freq_hz": float(center_freq_hz),
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
                "burst_ratio_db": 0.0,
                "expected_noise_ratio_db": 0.0,
                "burst_excess_db": 0.0,
                "is_burst": False,
            }

    # Peak bin (cropped if crop_mask is set, else full-span)
    psd_for_peak = psd_db[crop_mask] if crop_mask is not None else psd_db
    peak_idx_local = int(np.argmax(psd_for_peak))
    peak_idx = (
        int(np.flatnonzero(crop_mask)[peak_idx_local])
        if crop_mask is not None
        else peak_idx_local
    )
    peak_freq_hz = float(frequencies_hz[peak_idx])
    peak_power_db = float(psd_db[peak_idx])

    # Peak bin power from single chunk before averaging — fallback to peak_power_db
    # if key absent (for backwards compatibility with synthetic PSD dicts in tests)
    chunk_peak_db = float(psd_result.get("chunk_peak_db", peak_power_db))

    # Burst detection (Phase 45) — per-bin max-hold ratio at the peak bin.
    # The measured gap between max-hold and averaged power at the peak bin is
    # compared against the statistically expected gap for pure Gaussian noise
    # over num_chunks chunks (10*log10(ln(N) + 0.5772), the extreme-value
    # expectation for exponential noise powers). Only an excess beyond
    # BURST_MARGIN_DB counts as a genuine burst. This replaces the previous
    # single-chunk extreme vs averaged mean comparison, which produced a
    # positive gap on pure noise that grew with num_chunks.
    # BUGFIX (verified 2026-08-20): burst detection compares max-hold
    # power against AVERAGED power at the peak bin. Both sides of that
    # comparison must come from psd_result's raw traces by their real
    # keys, independent of trace_key. Previously this block reused the
    # function-local psd_db variable (bound to psd_result[trace_key]) as
    # the "averaged" side. Harmless for every band except adsb, whose
    # BAND_PROFILES entry sets trace_key='psd_max_hold_db' — which
    # silently made psd_db and max_hold_db the SAME array, collapsing
    # burst_ratio_db to exactly 0.0 on every ADS-B call regardless of
    # real signal content, making is_burst permanently unreachable for
    # ADS-B (live scan, Record-mode, and replay all affected).
    true_avg_db = psd_result.get("psd_db", psd_db)
    max_hold_db = psd_result.get("psd_max_hold_db", true_avg_db)
    if len(max_hold_db) != len(true_avg_db):
        logger.warning(
            "psd_max_hold_db length (%d) does not match psd_db length (%d) "
            "— falling back to averaged trace for burst ratio",
            len(max_hold_db),
            len(true_avg_db),
        )
        max_hold_db = true_avg_db
    if burst_use_wide_window and crop_mask is not None:
        # Phase 46: total-power ratio across the crop window.
        # Distinguishes continuous-but-frequency-agile signals (FM sweep)
        # from genuine time-bursty signals. For FM, every bin in the window
        # has been "hot" at some point in some chunk (sweeping carrier), so
        # max_hold is roughly uniform across the window while psd is roughly
        # uniform at a lower level — the noise floor dilutes the sum, so the
        # ratio is small. For a narrow burst that is on for only a small
        # fraction of chunks, max_hold at the burst bins is high while psd
        # at the burst bins is low, AND the rest of the window is noise on
        # both traces — the sum is dominated by the burst contrast.
        #
        # Tech debt: expected_noise_ratio_db (10*log10(ln(N)+0.5772)) was
        # derived for single-bin max-hold behaviour and has NOT been
        # re-derived for this multi-bin power-sum case. The 6.0 dB
        # BURST_MARGIN_DB margin is unvalidated for this new metric and
        # may need retuning once live FM data is checked.
        max_hold_lin = np.power(10.0, max_hold_db[crop_mask] / 10.0)
        avg_lin = np.power(10.0, true_avg_db[crop_mask] / 10.0)
        total_max_hold = float(np.sum(max_hold_lin))
        total_avg = float(np.sum(avg_lin))
        burst_ratio_db = float(
            10 * np.log10(total_max_hold / (total_avg + 1e-12))
        )
    else:
        # Phase 45 single-bin narrow metric (unchanged).
        burst_ratio_db = float(max_hold_db[peak_idx] - true_avg_db[peak_idx])

    # num_chunks guards: missing falls back to 1; a single chunk has no
    # max-hold meaning, and the guard also prevents log of zero or negative.
    num_chunks = int(psd_result.get("num_chunks", 1))
    if num_chunks < 2:
        expected_noise_ratio_db = 0.0
        is_burst = False
    else:
        expected_noise_ratio_db = float(
            10 * np.log10(np.log(num_chunks) + 0.5772)
        )
        # TODO(tech-debt TD-45-1): This margin sets a conservative duty-cycle ceiling of
        # ~3.4% at 976 chunks, which may suppress the tag on heavy multi-aircraft ADS-B
        # traffic. Not yet validated against real ADS-B.
        is_burst = bool(burst_ratio_db - expected_noise_ratio_db > BURST_MARGIN_DB)
    burst_excess_db = float(burst_ratio_db - expected_noise_ratio_db)

    # Noise floor — 10th percentile of all psd_db values
    noise_floor_db = float(np.percentile(psd_db, NOISE_FLOOR_PERCENTILE))

    # Signal-to-noise ratio
    snr_db = float(peak_power_db - noise_floor_db)

    # Bandwidth and occupied bin count
    # Bins are "occupied" when their power exceeds noise floor + effective_threshold dB
    # (Phase 30: cropped to per-band window when crop_half_width_hz is set;
    # noise floor above stays full-span).
    threshold = noise_floor_db + effective_threshold
    threshold_mask = psd_db > threshold
    if crop_mask is not None:
        occupied_mask = threshold_mask & crop_mask
    else:
        occupied_mask = threshold_mask
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
        "burst_ratio_db": burst_ratio_db,
        "expected_noise_ratio_db": expected_noise_ratio_db,
        "burst_excess_db": burst_excess_db,
        "is_burst": is_burst,
    }
