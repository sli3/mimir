"""
core/device/detect.py
Mimir RF Scanner — SDR Detection and Selection

WHAT THIS FILE DOES
───────────────────
Answers two questions WITHOUT opening any hardware:

  1. Which supported SDRs are plugged into this machine right now?
     -> enumerate_devices()
  2. Which one should Mimir use for this session?
     -> detect_device()

This module knows nothing about frequency bands — band capability lives
in dashboard/shared_state.py. This layer only knows which physical
devices are present and what their datasheet capabilities are
(core/device/profiles.py).

WHY PLUTO IS THE DEFAULT WHEN BOTH ARE CONNECTED
────────────────────────────────────────────────
Mimir supports exactly one device at a time (either/or, never both at
once). When no preference is stated and both devices are present, Pluto
is the no-preference default (per the 2026-07-15 multi-device decision).
The manual override for the six sub-325 MHz bands is `--device hackrf`
on scan.py — switching is a manual physical replug + flag, NOT an
auto-fallback path.

Calibration state of PLUTO_BAND_PROFILES (dashboard/shared_state.py):
  - gain_db (30.0) is SWEEP-EVIDENCED (Phase 39b): the live gain-sweep
    on both 915 MHz ISM and 1090 MHz ADS-B measured the noise floor
    flat from 0-40 dB with an AD9363 dip near 32 dB, and a spur wall
    above ~65 dB; 30.0 sits mid sweet-spot (28-40 dB), clear of both.
  - signal_threshold_db (3.0) is still PROVISIONAL / uncalibrated —
    inherited from HackRF, because no live in-band signal (LoRa burst,
    aircraft squitter) has been captured on Pluto yet to measure SNR.
    The threshold stays at 3.0 until a live capture provides a real
    measurement.

The previous choice of HackRF-as-default was driven by the fact that
its BAND_PROFILES were calibrated while Pluto's were not. That
rationale is no longer decisive: a calibrated gain does not require a
calibrated threshold to start, and an uncalibrated default does not
raise — it silently produces detections that look plausible. The
threshold provisional marker in dashboard/shared_state.py already
flags the open half honestly; this rewrite aligns the docstring with
that marker instead of repeating the over-claim Phase 39b removed.

LEGAL NOTE
──────────
Both supported SDRs are TX-CAPABLE hardware operating under a
zero-transmit legal constraint (Radiocommunications Act 1992 (Cth)).
This module performs enumeration and capability lookup only. It never
opens a stream, never calls any TX-direction SoapySDR API
(setupTxStream, writeStream, or any TX-direction call), and never
instantiates a device wrapper — detect_device returns the wrapper CLASS
object, not an instance.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from core.device.profiles import DEVICE_PROFILES

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DetectedDevice:
    """An immutable capability record for one detected SDR.

    wrapper_class is the device wrapper CLASS (e.g. HackRFReceiver), never
    an instance — detection must not open hardware.
    """

    driver: str
    display_name: str
    min_freq_hz: int
    max_freq_hz: int
    gain_model: str
    max_gain_db: float
    wrapper_class: type


def enumerate_devices() -> list[str]:
    """Return the driver keys of all supported SDRs present on this machine.

    Enumerates via SoapySDR once, with no driver filter, then keeps only
    drivers that appear in DEVICE_PROFILES. Any other driver (for example
    an rtl-sdr dongle) is ignored silently rather than raising — Mimir
    simply has no profile for it.

    SoapySDR is imported inside this function (matching the pattern in
    hackrf_rx.open() and pluto_rx.open()) so that importing this module
    never requires SoapySDR to be installed.

    Returns:
        A list of driver keys, e.g. ["hackrf"], ["plutosdr"],
        ["hackrf", "plutosdr"], or [] when nothing supported is present.

    Raises:
        RuntimeError: If the SoapySDR Python bindings are not installed.
    """
    try:
        import SoapySDR
    except ImportError as e:
        raise RuntimeError(
            "SoapySDR Python bindings not found. "
            "Install with: sudo dnf install python3-SoapySDR"
        ) from e

    # SoapySDR returns SoapySDRKwargs objects — SWIG wrappers around a C++
    # map, not dicts. They have no .get() method. Convert once here at the
    # boundary so everything below works with ordinary Python dicts.
    results = [dict(r) for r in SoapySDR.Device.enumerate()]
    found: list[str] = []
    for result in results:
        driver = result.get("driver")
        if driver in DEVICE_PROFILES and driver not in found:
            found.append(driver)
    logger.debug("Detected supported SDR drivers: %s", found)
    return found


def detect_device(preferred: str | None = None) -> DetectedDevice:
    """Select one SDR for this session and return its capability record.

    This returns a capability record built from DEVICE_PROFILES — the
    wrapper CLASS, not an instance. No hardware is opened.

    Preference order:
        1. If preferred is given and that driver is present, select it.
        2. If preferred is given but NOT present, raise RuntimeError
           naming both what was asked for and what was actually found.
        3. If preferred is None, select Pluto when present (the
           no-preference default per the 2026-07-15 decision — see the
           module docstring for the calibration state).
        4. Otherwise select HackRF when present.
        5. If nothing supported is present, raise RuntimeError.

    Args:
        preferred: An optional DEVICE_PROFILES driver key
            ("hackrf" / "plutosdr"), or None for automatic selection.

    Returns:
        A DetectedDevice describing the selected device.

    Raises:
        RuntimeError: If the requested device is absent, no supported
            device is present, or SoapySDR is not installed.
    """
    present = enumerate_devices()

    if preferred is not None:
        if preferred not in present:
            raise RuntimeError(
                f"Requested SDR driver {preferred!r} was not found. "
                f"Supported devices actually present: {present or 'none'}. "
                "Check the USB connection, or call with preferred=None "
                "to auto-select."
            )
        selected = preferred
    elif "plutosdr" in present:
        # Pluto is the no-preference default — see module docstring.
        selected = "plutosdr"
    elif "hackrf" in present:
        selected = "hackrf"
    else:
        raise RuntimeError(
            "No supported SDR device found. "
            "Connect a HackRF One or ADALM-PLUTO via USB."
        )

    profile = DEVICE_PROFILES[selected]
    logger.info(
        "Selected SDR: %s (driver=%s)", profile["display_name"], selected
    )
    return DetectedDevice(
        driver=profile["driver"],
        display_name=profile["display_name"],
        min_freq_hz=profile["min_freq_hz"],
        max_freq_hz=profile["max_freq_hz"],
        gain_model=profile["gain_model"],
        max_gain_db=profile["max_gain_db"],
        wrapper_class=profile["wrapper_class"],
    )
