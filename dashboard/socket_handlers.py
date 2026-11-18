"""
Register browser focus-frequency and capture-trigger SocketIO handlers.

Legal: Receive-only. Radiocommunications Act 1992 (Cth).
       No transmission. Jurisdiction: AU/SA. Authority: ACMA.

Registers the set_focus_frequency and set_capture_trigger SocketIO events.
Imported only by the import at the bottom of dashboard/server.py, which
must be the first module imported. Callers import these handlers from
dashboard.server.
"""

import logging

import dashboard.server as _server
import dashboard.shared_state as shared_state
from core.device.profiles import DEVICE_PROFILES

logger = logging.getLogger(__name__)


@_server.socketio.on("set_focus_frequency")
def handle_set_focus(data: dict) -> None:
    """Set or clear the focused frequency filter for scan_result emissions.

    Coerces freq_hz to float. Non-numeric or missing values clear the focus
    (set to None, meaning all frequencies pass through). When a scanner
    reference is available, also calls scanner.set_focus_frequency() to
    retune the SDR and flush any queued results. Known non-HackRF devices
    reject frequencies outside their tuning range or unsupported bands
    before changing focus, the band profile or the scanner. Unknown device
    keys retain the existing behaviour, and clearing focus is always allowed.

    Also updates shared_state.current_band to the matching band profile
    resolved for the active device (via shared_state.resolve_band_profile)
    when freq_hz corresponds to a known band, so the scan loop applies the
    correct per-band signal_threshold_db without a restart. When freq_hz
    is None, current_band is left untouched.

    Args:
        data: Dict from the browser with key "freq_hz". Values accepted:
              numeric (int/float), string numeric, None (clear focus),
              or missing key (clear focus).
    """
    raw = data.get("freq_hz")
    try:
        freq_hz = float(raw) if raw is not None else None
    except (TypeError, ValueError):
        freq_hz = None
    if freq_hz is not None:
        with shared_state.current_device_lock:
            active_device = shared_state.current_device
        if active_device != "hackrf" and active_device in DEVICE_PROFILES:
            # Mirror the scan loop: range first, then device band support.
            device_profile = DEVICE_PROFILES[active_device]
            in_range = (
                device_profile["min_freq_hz"]
                <= freq_hz
                <= device_profile["max_freq_hz"]
            )
            band_key = (
                shared_state.band_key_for_freq(freq_hz) if in_range else None
            )
            if (
                not in_range
                or band_key is None
                or not shared_state.band_supported_by_device(
                    band_key, active_device
                )
            ):
                logger.warning(
                    "Ignoring focus request for %.3f MHz: not receivable on %s",
                    freq_hz / 1e6, active_device,
                )
                return
    with _server._focused_freq_lock:
        _server._focused_freq_hz = freq_hz
    band_key = shared_state.band_key_for_freq(freq_hz)
    if band_key is not None:
        # Resolve the band profile for the ACTIVE device (Phase 65,
        # Finding A): on Pluto sessions this overlays Pluto's calibrated
        # signal_threshold_db/gain_db onto the BAND_PROFILES base; on
        # HackRF it returns the BAND_PROFILES copy unchanged. Use the same
        # locked device snapshot as the focus gate above.
        band_profile = shared_state.resolve_band_profile(
            band_key, active_device
        )
        with shared_state.current_band_lock:
            shared_state.current_band = band_profile
    if _server._scanner_ref is not None:
        _server._scanner_ref.set_focus_frequency(freq_hz)


@_server.socketio.on("set_capture_trigger")
def handle_set_capture_trigger(data):
    """Arm or disarm the SNR-edge auto-capture trigger for a band.

    Independent of set_focus_frequency: this handler does NOT touch
    shared_state.current_band or the scanner focus.
    It only flips the per-band armed flag in shared_state. The scan loop
    (core/pipeline/scanner.py) consults that flag on every cycle and,
    when the band's measured SNR crosses its calibrated
    signal_threshold_db from below, saves a SigMF capture of the raw IQ
    samples.

    Defensive by design, mirroring handle_set_focus: a malformed browser
    message must never crash the socket thread. An unknown or
    non-armable band logs a warning and returns without raising. Only an
    explicit bool is honoured for "armed"; any other type (string, int,
    list, None, missing key) coerces to False, because disarm is the
    safe direction for a malformed message.

    Args:
        data: Dict from the browser with keys "band" (a
              TRIGGER_ARMABLE_BANDS key, e.g. "adsb") and "armed"
              (bool). Non-dict payloads and missing keys are tolerated.
    """
    try:
        band = data.get("band")
    except AttributeError:
        # Non-dict payload (e.g. a bare string) - nothing to parse.
        logger.warning(
            "Ignoring malformed set_capture_trigger payload: %r", data
        )
        return
    # isinstance guard first: `in` on a frozenset raises TypeError for
    # unhashable types (e.g. a list), and this handler must never raise.
    if not isinstance(band, str) or band not in shared_state.TRIGGER_ARMABLE_BANDS:
        logger.warning(
            "Ignoring set_capture_trigger for unknown or non-armable band %r",
            band,
        )
        return
    raw = data.get("armed")
    try:
        # Strict coercion: only an explicit bool passes through. Any
        # other type coerces to False (disarm) rather than raising -
        # mirroring handle_set_focus's "unparseable clears" style.
        armed = raw if isinstance(raw, bool) else False
    except (TypeError, ValueError):
        armed = False
    shared_state.set_trigger_armed(band, armed)
