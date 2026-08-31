"""
fingerprint.py — Band-aware per-chunk fingerprinting helper

Legal: Receive-only. Radiocommunications Act 1992 (Cth).
       No transmission. Jurisdiction: AU/SA. Authority: ACMA.

WHAT THIS MODULE DOES
---------------------
Provides a single source of truth for "given a chunk of IQ samples, the
device's band profile, and a band key, what fingerprint does
fingerprint_spectrum produce?"

This is a thin wrapper that bundles the resolve_band_profile +
compute_psd + fingerprint_spectrum trio into one step parameterised by a
(band_key, device) pair. Both the offline replay path
(core.pipeline.replay) and the live demo producer
(core.pipeline.demo_producer, Phase 76) call this helper so callers do not
repeat the band-resolution dance.

This module is NOT a duplicate of features.fingerprint_spectrum(). The
latter is the low-level spectral fingerprint extractor; this module adds
the device-aware band profile resolution on top.

HARDWARE ISOLATION: this module has no direct core.device.* import. It
only resolves software band profiles and runs the offline FFT/fingerprint
pipeline. TX remains blocked by HardwareTransmitError in
core/legal/compliance_guard.py.
"""

from __future__ import annotations

import logging

from core.pipeline.features import fingerprint_spectrum
from core.pipeline.fft import compute_psd
from dashboard.shared_state import resolve_band_profile

logger = logging.getLogger(__name__)


def fingerprint_samples(
    samples,
    sample_rate_hz: float,
    core_freq_hz: float,
    band_key: str,
    device: str,
) -> dict:
    """Run compute_psd + fingerprint_spectrum over replayed samples.

    All four fingerprint_spectrum() parameters come from the SAME
    device-resolved band profile, resolved via
    resolve_band_profile(band_key, device) — the same helper the live
    scan loop uses to populate shared_state.current_band
    (dashboard/server.py). This matters for Pluto captures: a Pluto
    ADS-B file was fingerprinted at capture time against
    PLUTO_BAND_PROFILES (signal_threshold_db 10.0 dB, calibrated
    2026-08-17), so replaying it against the raw BAND_PROFILES base
    (3.0 dB) would shift occupied_bins / bandwidth_hz and report a
    structural mismatch on a capture that never changed. On "hackrf"
    (or any unknown device string) resolve_band_profile returns the
    BAND_PROFILES base unchanged, matching the pre-fix behaviour.

    fingerprint_trace_key is CRITICAL for ADS-B: that band fingerprints
    the psd_max_hold_db trace, and replaying it against the default
    averaged trace would make every ADS-B comparison structurally
    invalid. resolve_band_profile never overlays the trace key, so the
    BAND_PROFILES value carries through on both devices.
    """
    psd_result = compute_psd(samples, sample_rate_hz, core_freq_hz)
    return fingerprint_from_psd(psd_result, band_key, device)


def fingerprint_from_psd(
    psd_result: dict,
    band_key: str,
    device: str,
) -> dict:
    """Run fingerprint_spectrum on an already-computed PSD result.

    Convenience entry point for callers that already have a compute_psd()
    output — typically because they need the raw PSD for spectrum
    broadcast as well as the fingerprint. Avoids running compute_psd()
    twice on the same samples.

    Args:
        psd_result: Output of compute_psd() — must carry the keys
            fingerprint_spectrum() expects (psd_db, frequencies_hz,
            center_freq_hz, sample_rate_hz, nfft, and optionally
            num_chunks/chunk_peak_db/psd_max_hold_db).
        band_key: BAND_PROFILES key (e.g. "adsb", "fm_broadcast").
        device: DEVICE_PROFILES driver key ("hackrf" or "plutosdr") —
            used by resolve_band_profile() to apply the device-specific
            threshold overlay.

    Returns:
        The fingerprint dict from fingerprint_spectrum().
    """
    profile = resolve_band_profile(band_key, device)
    return fingerprint_spectrum(
        psd_result,
        signal_threshold_db=profile.get("signal_threshold_db"),
        crop_half_width_hz=profile.get("crop_half_width_hz"),
        burst_use_wide_window=profile.get("burst_use_wide_window", False),
        trace_key=profile.get("fingerprint_trace_key", "psd_db"),
    )
