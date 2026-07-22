"""
Shared state module for the Mimir dashboard threads.

This module holds all data that needs to be shared between two separate
threads: Thread A (capture_loop) and Thread B (ai_loop).

Why do we need this?
--------------------
In Python, each thread has its own memory space by default. If we want
Thread A to send signal fingerprints to Thread B for AI classification,
we need a way for them to communicate. We use:

1. A queue - like a conveyor belt where Thread A puts items and Thread B takes them
2. A lock - like a doorman that ensures only one thread touches shared data at a time
3. An event - like an alarm that tells both threads when to shut down
4. A dict with defaults - to store the latest AI annotation so the dashboard can display it

No classes here - everything is at module level for simplicity.
"""

import threading
from queue import Queue


# =============================================================================
# SHARED STATE VARIABLES
# =============================================================================

# -----------------------------------------------------------------------------
# fingerprint_queue
# -----------------------------------------------------------------------------
# Type: queue.Queue
# Purpose: Thread-safe queue that passes signal fingerprints from capture_loop
#          (Thread A) to ai_loop (Thread B).
# How it works: Thread A puts() fingerprints here after extracting features.
#               Thread B gets() them one by one and sends to the AI for classification.
# Why a queue?: It's FIFO (first-in-first-out), handles backpressure if ai_loop
#               falls behind, and is thread-safe so no locking is needed.
fingerprint_queue = Queue()

# -----------------------------------------------------------------------------
# annotation_lock
# -----------------------------------------------------------------------------
# Type: threading.Lock
# Purpose: Ensures only one thread can modify latest_annotation at a time.
# How it works: Before reading or writing to latest_annotation, a thread must
#               acquire this lock. After it's done, it releases the lock.
# Why we need it: The dict below is shared between threads. Without a lock,
#                 two threads modifying it simultaneously could corrupt data.
annotation_lock = threading.Lock()

# -----------------------------------------------------------------------------
# latest_annotation
# -----------------------------------------------------------------------------
# Type: dict (with default values)
# Purpose: Stores the most recent AI classification result so the dashboard
#          can display it immediately without waiting for a new fingerprint.
# Keys explained:
#   - label: The AI's predicted signal type (e.g., "FM broadcast", "noise")
#   - confidence: How sure the AI is (0.0 to 1.0), or None if not classified yet
#   - snr_db: Signal-to-noise ratio in decibels, or None
#   - distance: Estimated distance from source in metres, or None
#   - timestamp: When this annotation was created, as a datetime object
# Why defaults?: So the dashboard always has something to show even before
#                the AI has processed any signals. "Scanning..." tells the user
#                what's happening while we wait for data.
latest_annotation = {
    "label": "Scanning...",
    "confidence": None,
    "snr_db": None,
    "distance": None,
    "timestamp": None,
}

# -----------------------------------------------------------------------------
# shutdown_event
# -----------------------------------------------------------------------------
# Type: threading.Event
# Purpose: Signals both threads to stop when the dashboard should close.
# How it works: When set(), thread loops check this and exit gracefully.
#               The dashboard server sets this on shutdown so capture_loop
#               and ai_loop don't keep running in the background.
# Why an event?: It's a simple, standard way to coordinate shutdown across
#                multiple threads without complex locking or shared flags.
shutdown_event = threading.Event()

# =============================================================================
# WEBSOCKET CLIENT MANAGEMENT
# =============================================================================

# Set of active browser WebSocket connections.
# The capture loop broadcasts to every ws in this set.
# Protected by spectrum_clients_lock.
spectrum_clients: set = set()
spectrum_clients_lock = threading.Lock()

# Band switching — event set by /ws/command when user clicks a band button.
# The capture loop checks this every frame and restarts on the new band.
band_change_event = threading.Event()

# Per-band gain and threshold profiles for the live waterfall dashboard.
# These are independent of the main scan pipeline gain set in
# config/mimir.yaml (lna=24, vga=26, amp=False) and are tuned for
# each band's typical signal strength in Adelaide.
# signal_threshold_db: per-band detection threshold (dB above noise floor).
#   Read live by the scan loop (Phase 11) so switching bands applies the
#   correct threshold without restart.
# All receive-only — AU-legal bands only.
# NOTE: fm_broadcast and adsb are calibrated for the telescopic whip antenna.
# Other bands (aviation, acars, ais, aprs, ism) need revalidation in future phases.
BAND_PROFILES: dict = {
    "fm_broadcast": {
        "center_freq_hz":      98_000_000,
        "lna_gain_db":         24,  # Telescopic whip has poor FM coupling — gain required
        "vga_gain_db":         26,
        "signal_threshold_db": 21.0,   # Calibrated live FM Adelaide, telescopic whip, lna=24/vga=26
        "crop_half_width_hz":  112_500,
        # PLACEHOLDER-VERIFIED: real house capture 2026-07-13 (whip antenna,
        # diagnose_threshold.py --band fm_broadcast) showed true single-station
        # bandwidth converging toward ~200-230 kHz at threshold=27 dB across 4
        # runs (199,219-251,953 Hz range); half-width chosen as midpoint of that
        # observed range. Matches ACMA-confirmed 200 kHz FM channel spacing
        # independently. Revisit if signal_threshold_db (currently 21.0) is ever
        # recalibrated toward 27 dB, since that changes what "true" bandwidth
        # looks like at the new operating threshold.
    },
    "aviation": {
        "center_freq_hz":      127_000_000,
        "lna_gain_db":         16,  # VHF aviation weaker than FM; moderate gain
        "vga_gain_db":         20,
        "signal_threshold_db": 6.0,    # VHF aviation weaker than FM
        "crop_half_width_hz":  12_500,
        # PLACEHOLDER — NOT field-verified. Estimated from 25 kHz VHF voice
        # channel spacing convention. Needs live air-traffic capture to confirm.
    },
    "acars": {
        "center_freq_hz":      129_125_000,
        "lna_gain_db":         16,
        "vga_gain_db":         20,
        "signal_threshold_db": 6.0,
        "crop_half_width_hz":  12_500,
        # PLACEHOLDER — NOT field-verified. Same reasoning as aviation.
    },
    "aprs": {
        "center_freq_hz":      145_175_000,
        "lna_gain_db":         24,
        "vga_gain_db":         26,
        "signal_threshold_db": 18.0,    # Calibrated: telescopic whip, 2026-06-24, diagnose_threshold.py x2 runs
        "crop_half_width_hz":  12_500,
        # PLACEHOLDER-VERIFIED (band plan only, not a live-signal capture): WIA
        # Australian Amateur Band Plan confirms 25 kHz FM channel spacing on 2m.
        # Real house capture 2026-07-13 showed zero occupied bandwidth at the
        # current calibrated threshold (18.0 dB) — likely no APRS traffic was
        # on-air during capture, not a crop-relevant result. Revisit once a real
        # APRS packet is captured live.
    },
    "ais": {
        "center_freq_hz": 162_000_000,  # was 161_975_000 — demodulator centres at 162 MHz, channels at ±25 kHz
        "lna_gain_db":         16,  # VHF maritime — consistent with aviation/ACARS
        "vga_gain_db":         20,
        "signal_threshold_db": 5.0,    # Provisional — needs live calibration with telescopic whip
        "crop_half_width_hz": 50_000,
        # PLACEHOLDER-CORRECTED 2026-07-13 (Phase 30 HIGH-01 fix): center_freq_hz
        # (162.000 MHz) is the MIDPOINT between the two AIS channels, not a
        # channel centre — CH1 161.975 MHz and CH2 162.025 MHz each sit ±25 kHz
        # from it. A 12.5 kHz half-width cropped the dead gap between channels and
        # zeroed both signals. 50 kHz half-width covers 161.950–162.050 MHz,
        # capturing both channels with margin. Still NOT field-verified against a
        # live AIS capture — revisit once a real vessel packet is received.
    },
    "ism": {
        "center_freq_hz":      915_000_000,
        "lna_gain_db":         24,
        "vga_gain_db":         26,
        "signal_threshold_db": 3.0,   # Calibrated: telescopic whip, 2026-06-24, diagnose_threshold.py x2 runs
        "crop_half_width_hz":  250_000,
        # PLACEHOLDER — NOT field-verified, genuinely uncertain. AU915 uses a
        # mix of 125 kHz channels (64 of them) and 500 kHz channels (8 of them);
        # BAND_PROFILES center_freq_hz (915.000 MHz) does not land on a real
        # AU915 channel centre (they start at 915.2 MHz), so the current 2 MHz
        # capture window likely spans 4-5 real channels at once. Real house
        # capture 2026-07-13 showed only noise-level readings (no LoRa device
        # was transmitting nearby) — inconclusive, not a real-signal
        # measurement. Needs a capture during confirmed live LoRa traffic.
    },
    "adsb": {
        "center_freq_hz":      1_090_000_000,
        "lna_gain_db":         24,  # 1090 MHz ADS-B moderate strength
        "vga_gain_db":         24,
        "signal_threshold_db": 3.0,    # Calibrated live ADS-B 1090 MHz, diagnose_threshold.py x3 runs
        "crop_half_width_hz":  900_000,
        # PLACEHOLDER — NOT field-verified, deliberately conservative/wide.
        # Sources disagree on ADS-B/Mode S occupied bandwidth (~1 MHz vs ~2 MHz)
        # and the full capture window is only 2 MHz — an aggressive crop risks
        # clipping real pulse energy. tools/diagnose_threshold.py's own
        # BAND_SWEEP already assumes target_bw_hz=1_000_000 for ADS-B (a prior
        # estimate, not a live measurement) — 900 kHz half-width stays inside
        # that with a small margin. Needs a live-aircraft capture with the
        # spiral discone to confirm or revise.
    },
    "noise_floor": {
        "center_freq_hz":      98_000_000,
        "lna_gain_db":         0,   # Reference measurement — zero gain baseline
        "vga_gain_db":         0,
        "signal_threshold_db": 10.0,   # noise floor baseline dB — not a signal threshold
        "crop_half_width_hz":  None,
        # Reference/baseline profile, not a real receivable band. Cropping does
        # not apply — fingerprint_spectrum() must treat None as "no crop"
        # (full-span behaviour), same as when crop_half_width_hz is absent.
    },
}

# Currently active band. Initialise to FM broadcast.
# Protected by current_band_lock.
current_band: dict = dict(BAND_PROFILES["fm_broadcast"])
current_band_lock = threading.Lock()

# -----------------------------------------------------------------------------
# current_device / current_device_lock
# -----------------------------------------------------------------------------
# Type: str / threading.Lock
# Purpose: Records which SDR driver is currently open so the dashboard can
#          tell the frontend which device is live, and the frontend can use
#          that to grey out bands that device cannot physically receive.
#          The frontend band list is keyed by freq_hz, but the backend
#          support logic (band_supported_by_device, PLUTO_BAND_PROFILES) is
#          keyed by band_key — sharing the device name closes that loop.
# How it works: scan.py writes this once at startup from args.device (which
#               is constrained to {hackrf, plutosdr} via argparse choices=).
#               dashboard/server.py reads it under this lock in emit_stats
#               so the system_stats payload carries the live device name.
# Why we need it: Without this, the frontend cannot know which device is
#                 active and would have to re-derive Pluto's 325 MHz tuning
#                 floor client-side — duplicating hardware-specific logic
#                 in two places and risking drift.
# Default: "hackrf" — matches scan.py's argparse default and means the
#          dashboard reports a sensible value before scan.py has had a
#          chance to overwrite it.
current_device: str = "hackrf"
current_device_lock = threading.Lock()


def get_band_for_freq(freq_hz: float | None) -> dict | None:
    """Return a copy of the BAND_PROFILES entry whose center_freq_hz matches
    freq_hz exactly, or None if no profile matches.

    Used by handle_set_focus (dashboard/server.py) to update current_band
    when the user switches to a known band frequency. Returns a dict copy
    so callers cannot mutate the canonical profile.

    **Ordering dependency:** Both ``fm_broadcast`` and ``noise_floor`` have
    ``center_freq_hz == 98_000_000``. The function iterates ``BAND_PROFILES``
    in definition order and returns the *first* match, so ``fm_broadcast``
    always wins for 98 MHz. This is correct — the dashboard must never switch
    to the ``noise_floor`` profile from a frequency change. If entries are
    reordered or new duplicates are added, this function's behaviour changes
    silently.

    Args:
        freq_hz: Centre frequency in Hz, or None.

    Returns:
        dict copy of the matching BAND_PROFILES entry, or None.
    """
    if freq_hz is None:
        return None
    for profile in BAND_PROFILES.values():
        if profile["center_freq_hz"] == int(freq_hz):
            return dict(profile)
    return None


def get_nearest_band_for_freq(freq_hz: float | None) -> dict | None:
    """Return a copy of the BAND_PROFILES entry whose center_freq_hz is
    closest to freq_hz, excluding the noise_floor profile.

    Used as a fallback by handle_set_focus (dashboard/server.py) when
    get_band_for_freq() returns None — i.e. when the user tunes to a custom
    frequency that is not a canonical band centre. Returns the nearest band
    so the correct signal_threshold_db is applied to the waterfall.

    Example: typing 129 MHz in Custom MHz returns None from get_band_for_freq
    (no exact match), then this function returns the ACARS profile at
    129.125 MHz as the nearest entry — applying the 6.0 dB ACARS threshold
    instead of letting the FM threshold (21.0 dB) bleed through.

    noise_floor is excluded because it is a zero-gain reference measurement,
    not a real receivable band, and should never be applied to live scanning.

    Args:
        freq_hz: Centre frequency in Hz, or None.

    Returns:
        dict copy of the nearest BAND_PROFILES entry, or None if freq_hz is None.
    """
    if freq_hz is None:
        return None
    candidates = {
        k: v for k, v in BAND_PROFILES.items()
        if k != "noise_floor"
    }
    nearest_key = min(
        candidates,
        key=lambda k: abs(candidates[k]["center_freq_hz"] - freq_hz)
    )
    return dict(candidates[nearest_key])


def band_key_for_freq(freq_hz: float | None) -> str | None:
    """Return the BAND_PROFILES KEY (not the profile dict) for freq_hz.

    Returns the key of the profile whose center_freq_hz matches freq_hz
    exactly, or — if there is no exact match — the key of the nearest
    profile, or None if freq_hz is None.

    Key facts:

    - Returns the KEY string (e.g. "fm_broadcast"), not a profile dict.
      This is the lookup band_supported_by_device() needs, since that
      function is keyed by band name.
    - Exact-match iteration order mirrors get_band_for_freq: both
      ``fm_broadcast`` and ``noise_floor`` sit at 98 MHz, and the first
      match in definition order wins, so 98 MHz returns "fm_broadcast",
      never "noise_floor".
    - The nearest-match fallback EXCLUDES ``noise_floor``, mirroring
      get_nearest_band_for_freq: it is a zero-gain reference measurement,
      not a real receivable band, and must never be selected for live
      scanning.
    - This is a pure, read-only helper. It takes no locks and mutates
      nothing.

    Args:
        freq_hz: Centre frequency in Hz, or None.

    Returns:
        A BAND_PROFILES key string, or None if freq_hz is None.
    """
    if freq_hz is None:
        return None
    for key, profile in BAND_PROFILES.items():
        if profile["center_freq_hz"] == int(freq_hz):
            return key
    candidates = {
        k: v for k, v in BAND_PROFILES.items()
        if k != "noise_floor"
    }
    return min(
        candidates,
        key=lambda k: abs(candidates[k]["center_freq_hz"] - freq_hz)
    )


# =============================================================================
# PLUTO BAND SUPPORT — Phase 36 additive override layer
# =============================================================================

from core.device.profiles import DEVICE_PROFILES

# PLUTO_BAND_PROFILES
# -------------------
# ADDITIVE OVERRIDE on top of BAND_PROFILES.
#
# This dict declares which of the eight Mimir bands the ADALM-PLUTO can
# physically receive. Each entry carries ONLY the keys that differ for
# Pluto (supported / gain_db / signal_threshold_db for receivable bands,
# supported / reason for the rest). center_freq_hz and crop_half_width_hz
# are inherited from BAND_PROFILES and must never be restated here.
#
# gain_db (ism, adsb): 30.0 — SWEEP-EVIDENCED, not calibrated against a
#   real signal. Phase 39 gain sweeps (tools/diagnose_pluto_gain.py, run
#   live on both --band ism and --band adsb) measured Pluto's own noise
#   behaviour: flat noise floor 0–40 dB, an AD9363 non-monotonic dip at
#   32 dB, and a spur "picket-fence" wall from ~65 dB. 30.0 sits in the
#   28–40 dB sweet spot, clear of both the 32 dB dip and the 65 dB spur
#   wall, on both bands. This validates gain/noise/spurs ONLY.
#
# signal_threshold_db (ism, adsb): 3.0 — PROVISIONAL, still uncalibrated
#   for Pluto. Neither Phase 39 sweep caught a real in-band target (no
#   LoRa burst, no aircraft), so SNR-above-noise was never measured on
#   Pluto. This value is inherited from the HackRF BAND_PROFILES entries
#   and kept as a placeholder until a live capture with a real signal is
#   available. Do not treat as calibrated.
#
# The six unsupported bands are all below Pluto's 325 MHz tuning floor
# (stock AD9363 firmware); the reason string on each entry states the
# specific cause.
PLUTO_BAND_PROFILES: dict = {
    "fm_broadcast": {
        "supported": False,
        "reason": "Below Pluto's 325 MHz tuning floor (98 MHz)",
    },
    "aviation": {
        "supported": False,
        "reason": "Below Pluto's 325 MHz tuning floor (127 MHz)",
    },
    "acars": {
        "supported": False,
        "reason": "Below Pluto's 325 MHz tuning floor (129.125 MHz)",
    },
    "aprs": {
        "supported": False,
        "reason": "Below Pluto's 325 MHz tuning floor (145.175 MHz)",
    },
    "ais": {
        "supported": False,
        "reason": "Below Pluto's 325 MHz tuning floor (162 MHz)",
    },
    "ism": {
        "supported": True,
        "gain_db": 30.0,
        "signal_threshold_db": 3.0,
    },
    "adsb": {
        "supported": True,
        "gain_db": 30.0,
        "signal_threshold_db": 3.0,
    },
    "noise_floor": {
        "supported": False,
        "reason": "Below Pluto's 325 MHz tuning floor (98 MHz)",
    },
}


def band_supported_by_device(band: str, device: str) -> bool:
    """Return True if the named device can physically receive the named band.

    The "supported" flag in PLUTO_BAND_PROFILES is the source of truth for
    Pluto, by explicit design — this function deliberately does NOT
    re-derive support from DEVICE_PROFILES frequency limits. DEVICE_PROFILES
    is used only to validate that the device key is one Mimir knows about.

    HackRF returns True for all eight bands: its 1 MHz–6 GHz tuning range
    covers every band in the current plan.

    Args:
        band: A BAND_PROFILES key (e.g. "fm_broadcast").
        device: A DEVICE_PROFILES driver key ("hackrf" / "plutosdr").

    Returns:
        True if the device supports the band, False otherwise.

    Raises:
        KeyError: If band is not a known BAND_PROFILES key, or device is
            not a known DEVICE_PROFILES driver key.
    """
    if band not in BAND_PROFILES:
        raise KeyError(f"Unknown band {band!r} — not a BAND_PROFILES key")
    if device not in DEVICE_PROFILES:
        raise KeyError(f"Unknown device {device!r} — not a DEVICE_PROFILES key")
    if device == "hackrf":
        return True
    return bool(PLUTO_BAND_PROFILES[band]["supported"])


def unsupported_bands_for_device(device: str) -> dict[str, str]:
    """Return {band_key: reason} for every band the named device cannot
    physically receive.

    Iterates BAND_PROFILES, skips ``noise_floor`` (it is a zero-gain
    reference, never a user-facing band — consistent with
    ``get_nearest_band_for_freq`` / ``band_key_for_freq``), and calls the
    existing ``band_supported_by_device(band, device)`` for each. For the
    unsupported bands, reads the reason string directly out of
    ``PLUTO_BAND_PROFILES[band]["reason"]`` — no hard-coding here. The map
    is keyed by band_key (e.g. "fm_broadcast"), not freq_hz, because the
    frontend has the freq_hz -> band_key mapping and the backend has the
    reverse; the shared device value flows through unchanged.

    Empty dict means the device supports every band. HackRF returns {}
    because its 1 MHz–6 GHz tuning range covers the entire current plan.

    This is a pure, read-only helper. It takes no locks and mutates
    nothing. Used by ``dashboard/server.py`` ``emit_stats()`` to populate
    the ``unsupported_bands`` field of the system_stats payload, which the
    frontend ``FrequencyList`` and App band buttons consume to grey out
    rows the active device cannot receive.

    Args:
        device: A DEVICE_PROFILES driver key ("hackrf" / "plutosdr").

    Returns:
        Dict mapping band_key to its PLUTO_BAND_PROFILES reason string for
        every band the device does not support. Empty dict if the device
        supports all bands.

    Raises:
        KeyError: If device is not a known DEVICE_PROFILES driver key —
            propagated from ``band_supported_by_device``.
    """
    unsupported: dict[str, str] = {}
    for band_key, _profile in BAND_PROFILES.items():
        if band_key == "noise_floor":
            continue
        if not band_supported_by_device(band_key, device):
            # band_supported_by_device has already validated that the
            # device is a known DEVICE_PROFILES key; the device-specific
            # reason string lives on PLUTO_BAND_PROFILES.
            unsupported[band_key] = PLUTO_BAND_PROFILES[band_key]["reason"]
    return unsupported
