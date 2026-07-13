"""
Tests for dashboard/capture_loop.py

Verifies that run_shared_capture_loop forwards the per-band
``signal_threshold_db`` (snapshotted from ``current_band``) into
``fingerprint_spectrum()``. Without the kwarg, fingerprint_spectrum()
falls back to the module-level SIGNAL_THRESHOLD_DB (24.0 dB) regardless
of band.

These tests use asyncio.run() directly (no pytest-asyncio dependency).
The real event loop and default ThreadPoolExecutor drive the mocked I/O
(HackRFReceiver / compute_psd / fingerprint_spectrum); no asyncio module
patching is required because the mocks are safe to call from executor
threads. After the first fingerprint call, band_change_event and
shutdown_event are set so the loop exits cleanly.

All receive-only. No TX surfaces.
"""

import asyncio
from unittest.mock import MagicMock, patch

import numpy as np

from dashboard import capture_loop
from dashboard.shared_state import (
    BAND_PROFILES,
    band_change_event,
    current_band,
    current_band_lock,
    fingerprint_queue,
    shutdown_event,
)


def _run_one_fingerprint_iteration(band_key: str) -> list:
    """
    Drive run_shared_capture_loop through exactly one fingerprint call,
    with current_band snapshotted to BAND_PROFILES[band_key].

    Returns the list of ``signal_threshold_db`` values captured by the
    fingerprint_spectrum side_effect. Restores current_band afterwards.

    Uses the real event loop + default executor (asyncio.run). The three
    I/O touch points (HackRFReceiver, compute_psd, fingerprint_spectrum)
    are patched; the executor runs the mock callables in worker threads,
    which is safe for MagicMock instances.
    """
    saved_band = dict(current_band)
    try:
        with current_band_lock:
            current_band.clear()
            current_band.update(BAND_PROFILES[band_key])
        band_change_event.clear()
        shutdown_event.clear()

        # Drain any leftovers from a previous test so the queue never
        # accumulates state across tests in the same session.
        while not fingerprint_queue.empty():
            fingerprint_queue.get_nowait()

        seen_thresholds: list = []

        def side_effect(
            psd_result,
            signal_threshold_db=None,
            trace_key="psd_db",
        ):
            seen_thresholds.append(signal_threshold_db)
            # First call only: break the inner loop, then the outer loop.
            band_change_event.set()
            shutdown_event.set()
            # Return a well-formed fingerprint dict so the queue put succeeds.
            return {
                "center_freq_hz": psd_result.get("center_freq_hz", 0.0),
                "peak_freq_hz": 0.0,
                "peak_power_db": -50.0,
                "noise_floor_db": -80.0,
                "snr_db": 30.0,
                "bandwidth_hz": 0.0,
                "occupied_bins": 0,
                "spectral_flatness": 0.0,
                "signal_threshold_db": float(signal_threshold_db or 24.0),
                "snr_margin_db": 30.0,
                "peak_bin_power_db": -50.0,
            }

        synthetic_psd = {
            "psd_db": np.full(16, -70.0, dtype=np.float64),
            "frequencies_hz": np.linspace(98e6 - 1e6, 98e6 + 1e6, 16),
            "center_freq_hz": BAND_PROFILES[band_key]["center_freq_hz"],
            "sample_rate_hz": 2_000_000,
            "nfft": 1024,
        }

        # Mock the HackRFReceiver class so HackRFReceiver(...).__enter__()
        # yields a context whose read_samples returns a small samples array.
        sdr_instance = MagicMock()
        sdr_instance.read_samples = MagicMock(
            return_value=np.zeros(1024, dtype=np.complex64)
        )
        enter_mock = MagicMock(return_value=sdr_instance)
        exit_mock = MagicMock(return_value=False)
        receiver_class = MagicMock()
        receiver_class.return_value.__enter__ = enter_mock
        receiver_class.return_value.__exit__ = exit_mock

        with (
            patch("dashboard.capture_loop.HackRFReceiver", receiver_class),
            patch(
                "dashboard.capture_loop.compute_psd",
                return_value=synthetic_psd,
            ),
            patch(
                "dashboard.capture_loop.fingerprint_spectrum",
                side_effect=side_effect,
            ),
        ):
            asyncio.run(capture_loop.run_shared_capture_loop())

        return seen_thresholds
    finally:
        with current_band_lock:
            current_band.clear()
            current_band.update(saved_band)
        band_change_event.clear()
        shutdown_event.clear()


def test_fm_band_threshold_forwarded_to_fingerprint_spectrum():
    """The FM broadcast per-band threshold (21.0 dB) is forwarded.

    Old code (bare fingerprint_spectrum(psd_result)) would capture None
    here because the signal_threshold_db kwarg was never passed, causing
    fingerprint_spectrum to fall back to the module-level 24.0 dB.
    New code forwards band.get("signal_threshold_db") -> 21.0.
    """
    seen = _run_one_fingerprint_iteration("fm_broadcast")
    expected = BAND_PROFILES["fm_broadcast"]["signal_threshold_db"]

    assert seen == [expected], (
        f"expected fingerprint_spectrum to be called once with "
        f"signal_threshold_db={expected} (from BAND_PROFILES['fm_broadcast']); "
        f"got {seen!r}"
    )


def test_adsb_band_threshold_forwarded_to_fingerprint_spectrum():
    """The ADS-B per-band threshold (3.0 dB) is forwarded, proving the
    forwarding is per-band rather than a single hardcoded value.

    Old code captured None (24.0 dB fallback). New code captures 3.0.
    """
    seen = _run_one_fingerprint_iteration("adsb")
    expected = BAND_PROFILES["adsb"]["signal_threshold_db"]

    assert seen == [expected], (
        f"expected fingerprint_spectrum to be called once with "
        f"signal_threshold_db={expected} (from BAND_PROFILES['adsb']); "
        f"got {seen!r}"
    )
