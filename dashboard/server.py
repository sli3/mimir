"""
dashboard/server.py — Flask + SocketIO Backend for the Mimir Dashboard

Legal: Receive-only. Radiocommunications Act 1992 (Cth).
       No transmission. Jurisdiction: AU/SA. Authority: ACMA.

WHAT THIS FILE DOES
───────────────────
Provides the HTTP and WebSocket backend that the cyberpunk React
dashboard connects to. Serves three roles:

1. Static file serving — the Vite build output in dashboard/static/
   is served at the root URL.

2. Real-time data — Flask-SocketIO pushes scan_result, spectrum_update,
   and system_stats events to connected browsers. Also accepts
   set_focus_frequency events from the browser to change which frequency
   the scanner dwells on.

3. REST API: GET /api/frequencies is served here and returns ACMA frequency
   reference entries with optional query-parameter filtering (min_mhz,
   max_mhz, tagged_only). Other HTTP routes live in dashboard/routes_pages.py,
   dashboard/routes_radar.py, dashboard/routes_capture.py,
   dashboard/routes_replay.py and dashboard/routes_vectorstore.py. The import
   at the bottom of this file registers those routes on app.

The ACARS, AIS and ADS-B aircraft emitters live in dashboard/emitters.py
and the SocketIO handlers in dashboard/socket_handlers.py. The import block
at the bottom of this file registers the handlers and re-exports the emitters
and handlers. start_server (with emit_stats and broadcast),
emit_adsb_scan_result and /api/frequencies stay here.

Pure helpers live in dashboard/adsb_field_tracker.py,
dashboard/reason_validation.py and dashboard/capture_listing.py.

CONSTRAINTS
───────────
- async_mode='threading' — do not change to eventlet or gevent.
- broadcast() and broadcast_spectrum() are defined inside start_server()
  and are not importable directly. Retrieve via start_server._broadcast_fn
  and start_server._broadcast_spectrum_fn after calling start_server().
  Spectrum updates are capped at 30 Hz and rounded to one decimal place.
"""

import json
import logging
import os
import threading
import time
from pathlib import Path

from flask import Flask, jsonify, request
from flask_socketio import SocketIO

from core.pipeline.frequency import freq_matches
from core.pipeline.scan_result import ScanResult
from dashboard.adsb_field_tracker import AdsbFieldTracker
# Re-export moved helpers for existing importers and the contract test.
from dashboard.reason_validation import (
    _REASON_CALLSIGN_RE,  # noqa: F401
    _REASON_SQUAWK_RE,  # noqa: F401
    _REASON_ICAO_RE,  # noqa: F401
    _REASON_NUMERIC_RANGES,  # noqa: F401
    _REASON_NULLABLE_NUMERIC_RANGES,  # noqa: F401
    _coerce_finite_float,  # noqa: F401
    _validate_reason_payload,  # noqa: F401
)
from dashboard.capture_listing import (
    _CAPTURE_FILENAME_RE,  # noqa: F401
    _parse_capture_meta_entry,  # noqa: F401
    _parse_capture_timestamp,  # noqa: F401
    _capture_sort_key,  # noqa: F401
)
from embeddings.store import SignalStore
from llm.path_reasoner import PathReasoner
from modules.adsb.message import AdsbMessage
from modules.adsb.constants import (
    AU_ADSB_FREQUENCY_HZ,
    FREQ_TOLERANCE_HZ,
)
import dashboard.shared_state as shared_state

logger = logging.getLogger(__name__)

# Prin's 2026-11-20 logs measured live scanning at about 15-20 updates per
# second with dwell_time_sec 0.0, below this cap. The cap guards against a
# faster path flooding the browser and is global across centre frequencies.
SPECTRUM_MAX_RATE_HZ = 30.0
# 0.1 dB is below what the waterfall colourmap or spectrum bar can show.
SPECTRUM_DB_DECIMALS = 1


app = Flask(__name__, static_folder="static", static_url_path="")
socketio = SocketIO(
    app,
    async_mode="threading",
    cors_allowed_origins=[
        "http://localhost:5000",
        "http://127.0.0.1:5000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
)

_device_ref = None
_scanner_ref = None
_last_hw_error_time = 0.0
_focused_freq_hz: float | None = None
_focused_freq_lock = threading.Lock()

# In-process cache for the vector-space 3D projection.  Keyed on record count
# so repeated page loads don't recompute t-SNE, which is CPU-intensive.
_VECTORSTORE_CACHE = {
    "count": -1,
    "points": None,
    "method": None,
}
_VECTORSTORE_CACHE_LOCK = threading.Lock()

_signal_store = None
_signal_store_lock = threading.Lock()

# Lazily-created singleton PathReasoner for POST /api/radar/reason (Phase
# 53). Follows the same lazy-with-lock pattern as _signal_store below: one
# instance per process, configured from MimirConfig on first use, never
# spawned per request. The reasoner is effectively immutable across
# requests — reason() only ever mutates the single float _offline_until
# (a GIL-atomic assignment), so no lock is held around the call itself;
# the worst case of two concurrent requests is a duplicate LLM call.
_path_reasoner = None
_path_reasoner_lock = threading.Lock()

# Per-ICAO ADS-B field-merge tracker for the AI Reasoning panel.  See
# AdsbFieldTracker in dashboard/adsb_field_tracker.py; mirrors the design of
# modules/adsb/bearing_tracker.py:BearingTracker.  Lightweight in-memory
# dict, so direct instantiation with no lazy-with-lock needed.
_field_tracker = AdsbFieldTracker()


def _get_signal_store():
    """Return the shared SignalStore instance, creating it lazily.

    The dashboard and scan.py run in the same process and share the same
    ChromaDB path.  Using a single PersistentClient avoids re-opening the
    SQLite backing store on every request and reduces "database is locked"
    pressure during live capture.

    Returns:
        SignalStore: The singleton SignalStore instance.
    """
    global _signal_store
    if _signal_store is None:
        with _signal_store_lock:
            if _signal_store is None:
                _signal_store = SignalStore()
    return _signal_store


def _get_path_reasoner() -> PathReasoner:
    """Return the shared PathReasoner instance, creating it lazily.

    Configured from load_config() on first use (LLM URL plus the Phase 53
    llm_reason_timeout_sec / llm_reason_cooldown_sec keys). If the config
    file cannot be loaded, falls back to PathReasoner's own defaults so
    the endpoint still serves a well-formed "unavailable" answer instead
    of failing at import or startup time.

    Returns:
        PathReasoner: The singleton reasoner instance.
    """
    global _path_reasoner
    if _path_reasoner is None:
        with _path_reasoner_lock:
            if _path_reasoner is None:
                try:
                    from core.config.loader import load_config
                    cfg = load_config()
                    _path_reasoner = PathReasoner(
                        base_url=cfg.llm_url,
                        cooldown_sec=cfg.llm_reason_cooldown_sec,
                        timeout_sec=cfg.llm_reason_timeout_sec,
                    )
                except Exception as exc:
                    logger.warning(
                        "Config load failed for PathReasoner (%s) — "
                        "using constructor defaults", exc,
                    )
                    _path_reasoner = PathReasoner()
    return _path_reasoner


def record_hw_error() -> None:
    """Record the current time for the dashboard's hardware-error window."""
    global _last_hw_error_time
    _last_hw_error_time = time.time()


def _compute_hackrf_status() -> str:
    """Return DISCONNECTED, NOT_RESPONDING or CONNECTED for the SDR.

    A missing or closed device is DISCONNECTED. An open device is
    NOT_RESPONDING while the scanner reports a read outage or a hardware
    error occurred within the last five seconds; otherwise it is CONNECTED.
    """
    if _device_ref is None or not _device_ref.is_open:
        return "DISCONNECTED"
    if (
        _scanner_ref is not None
        and getattr(_scanner_ref, "sdr_unresponsive", False) is True
    ):
        return "NOT_RESPONDING"
    if time.time() - _last_hw_error_time < 5.0:
        return "NOT_RESPONDING"
    return "CONNECTED"


def start_server(host: str, port: int, device=None, scanner=None):
    """
    Start the Flask-SocketIO dashboard server in a background thread.

    Werkzeug is allowed to run without a TTY so background and demo launches
    serve the dashboard, and the bind address comes from config, loopback by default.

    Args:
        host    : Bind address (e.g. "0.0.0.0" for all interfaces).
        port    : Port number (e.g. 5000).
        device  : Optional HackRF device reference for status reporting.
        scanner : Optional ScanRunner instance for live system_stats.
                  When provided, system_stats events report real values
                  (scan_count, queue_depth, llm_last_inference_ms) instead
                  of zeros.

    After calling start_server(), the broadcast functions are attached
    as attributes on the function itself:
        start_server._broadcast_fn        — emit a scan_result event
        start_server._broadcast_spectrum_fn — emit spectrum_update at up to
            30 Hz with PSD values rounded to one decimal place
    """
    global _device_ref, _scanner_ref
    _device_ref = device
    _scanner_ref = scanner

    def run_flask() -> None:
        """Run the dashboard server for foreground and background launches."""
        socketio.run(
            app, host=host, port=port, debug=False, use_reloader=False,
            allow_unsafe_werkzeug=True,
        )

    t = threading.Thread(target=run_flask, daemon=True)
    t.start()
    logger.info("Dashboard server started on http://%s:%d", host, port)

    def emit_stats():
        while True:
            time.sleep(2.0)
            if scanner is not None:
                stats = scanner.get_stats()
                active_freq = stats["active_frequency_hz"]
                scan_count = stats["scan_count"]
                queue_depth = stats["queue_depth"]
                last_backlog = stats["last_backlog"]
                llm_call_count = stats["llm_call_count"]
                llm_ms = stats["last_llm_ms"]
            else:
                active_freq = 0.0
                scan_count = 0
                queue_depth = 0
                last_backlog = 0
                llm_call_count = 0
                llm_ms = 0.0
            # Read the active device driver from shared state (under lock)
            # and compute the per-device unsupported-band map. Both are
            # static for the lifetime of a run, but reading every poll
            # keeps the code path uniform with the rest of the stats and
            # means a future hot-swap of the device via a hypothetical
            # /api/device endpoint would just work without touching this
            # function.
            with shared_state.current_device_lock:
                active_device = shared_state.current_device
            unsupported_map = shared_state.unsupported_bands_for_device(active_device)
            data = {
                "hackrf_status": _compute_hackrf_status(),
                "active_frequency_hz": active_freq,
                "scan_count": scan_count,
                "queue_depth": queue_depth,
                "last_backlog": last_backlog,
                "llm_call_count": llm_call_count,
                "llm_last_inference_ms": llm_ms,
                # Phase 38 — device-aware unsupported-band UI.
                "device": active_device,
                # Phase 40b — friendly device name for the signal-detail panel.
                "current_device_display": shared_state.display_name_for_device(active_device),
                "unsupported_bands": unsupported_map,
            }
            socketio.emit("system_stats", data)

    _stats_thread = threading.Thread(target=emit_stats, daemon=True)
    _stats_thread.start()

    def broadcast(scan_result: ScanResult) -> None:
        """Emit a scan_result event for a fingerprint/LLM-classified scan.

        Called by the LLM classification pipeline when ScanRunner finishes
        classifying a spectrum fingerprint. Only emits if the current focused
        frequency matches the scan's center frequency (or is None, meaning
        all frequencies pass through). The payload includes the classification
        result plus fingerprint-derived fields such as peak power, SNR, and
        per-band thresholds. Since Phase 32, also includes a ``source`` field
        set to ``"fingerprint"`` to distinguish LLM-classified scans from
        decoder-driven ones (see :func:`emit_adsb_scan_result`). Since Phase 45,
        includes burst-detection fields (burst_ratio_db, expected_noise_ratio_db,
        burst_excess_db, is_burst) computed by the per-bin max-hold ratio method.

        Args:
            scan_result: The ScanResult dataclass instance to broadcast.
        """
        with _focused_freq_lock:
            focused = _focused_freq_hz
        if focused is not None and not freq_matches(scan_result.center_freq_hz, focused):
            return
        cls = scan_result.classification
        fp = scan_result.fingerprint or {}  # fingerprint dict, may be None
        data = {
            "timestamp": scan_result.timestamp,
            "center_freq_hz": scan_result.center_freq_hz,
            "signal_type": cls.signal_type,
            "confidence": cls.confidence,
            "confidence_score": cls.confidence_score,
            "novel": cls.novel,
            "au_legal_status": cls.au_legal_status,
            "reasoning": cls.reasoning,
            # Fingerprint fields — added in Phase 10-Fix2
            "peak_power_db": fp.get("peak_power_db"),
            "peak_bin_power_db": fp.get("peak_bin_power_db"),
            # Phase 45 burst-detection fields (per-bin max-hold ratio). The
            # frontend consumes `is_burst` to drive the [PEAK] tag in
            # SignalHistoryLog as of Phase 45b; the other three are emitted
            # for forward-compatibility and dashboard tooling but not yet
            # rendered.
            "burst_ratio_db": fp.get("burst_ratio_db"),
            "expected_noise_ratio_db": fp.get("expected_noise_ratio_db"),
            "burst_excess_db": fp.get("burst_excess_db"),
            "is_burst": fp.get("is_burst"),
            "snr_db": fp.get("snr_db"),
            # Per-band threshold fields — added in Phase 11
            "signal_threshold_db": fp.get("signal_threshold_db", 0.0),
            # TODO(tech-debt): snr_margin_db defaults to 0.0 here, which makes a
            # missing margin indistinguishable from a real +0.0 dB margin. The
            # Phase 32 provenance gate (source="fingerprint"|"decode") sidesteps
            # this for confidence display, but a missing margin should ideally
            # default to None. Deferred from Phase 32.
            "snr_margin_db": fp.get("snr_margin_db", 0.0),
            "bandwidth_hz": fp.get("bandwidth_hz"),
            "spectral_flatness": fp.get("spectral_flatness"),
            "chroma_distance": fp.get("chroma_distance"),
            "source": "fingerprint",
        }
        socketio.emit("scan_result", data)

    last_spectrum_emit_time: float | None = None
    spectrum_emit_lock = threading.Lock()

    def broadcast_spectrum(
        psd_db: list,
        center_freq_hz: float,
        freq_min_hz: float,
        freq_max_hz: float,
    ) -> None:
        """Emit spectrum updates at up to 30 Hz with PSD rounded to 0.1 dB.

        The cap is shared across centre frequencies for this server call.
        Updates inside the interval are dropped without being queued.
        Updates at the next emit deadline are accepted.
        """
        nonlocal last_spectrum_emit_time
        with spectrum_emit_lock:
            now = time.monotonic()
            if (
                last_spectrum_emit_time is not None
                and now < last_spectrum_emit_time + 1 / SPECTRUM_MAX_RATE_HZ
            ):
                return
            last_spectrum_emit_time = now

        values = psd_db.tolist() if hasattr(psd_db, "tolist") else psd_db
        data = {
            "psd_db": [round(float(v), SPECTRUM_DB_DECIMALS) for v in values],
            "center_freq_hz": center_freq_hz,
            "freq_min_hz": freq_min_hz,
            "freq_max_hz": freq_max_hz,
        }
        socketio.emit("spectrum_update", data)

    start_server._broadcast_fn = broadcast
    start_server._broadcast_spectrum_fn = broadcast_spectrum

    return broadcast


def emit_adsb_scan_result(msg: AdsbMessage) -> None:
    """Emit a scan_result event for a confirmed ADS-B decode.

    Called by AdsbSubscriber whenever AdsbDecoder successfully decodes a frame
    (CRC valid, DF17/DF18, valid ICAO). Bypasses the LLM pipeline — a confirmed
    decode is ground truth, confidence = 1.0.

    Applies the same focused-frequency filter as broadcast(): only emits if
    the current focused frequency is None (all frequencies pass through) or
    is within FREQ_TOLERANCE_HZ of AU_ADSB_FREQUENCY_HZ (1090 MHz). This
    prevents ADS-B scan_result events from appearing in Signal History when
    the user is focused on a different band.

    Fingerprint fields (peak_power_db, snr_db, etc.) are not available from
     the decoder path and are emitted as None. Signal History will show ---
     for those fields when an entry comes from this path. Since Phase 32,
     also sets ``source`` to ``"decode"`` to distinguish confirmed decodes
     (ground truth, confidence 1.0) from LLM-classified scans (fingerprint
     source). The dashboard uses this field to dim the confidence bar when
     there is no real signal.

    Burst-detection fields (burst_ratio_db, expected_noise_ratio_db,
    burst_excess_db, is_burst) are always None on the decode path because
    the decoder produces no fingerprint. They are included only for payload
    shape parity with broadcast() — the frontend does not need to special-case
    missing keys.

    The reasoning string is built from the merged per-ICAO view maintained
    by ``_field_tracker`` (AdsbFieldTracker), not from the single triggering
    frame: ADS-B frames carry disjoint field sets by typecode, so a field
    an earlier frame already resolved would otherwise show "unknown" here
    while the ADS-B AIRCRAFT table (merged on the frontend) shows the real
    value. A field shows "unknown" only when it has NEVER been resolved for
    that ICAO.

    NOTE: In busy airspace, ADS-B traffic can produce a high rate of decoded
    frames (potentially dozens per second). Each decode emits a separate
    scan_result event. If this floods Signal History or the AI Reasoning
    panel, rate-limiting or batching may be needed in a future build.

    Args:
        msg: Decoded AdsbMessage from AdsbDecoder.
    """
    with _focused_freq_lock:
        focused = _focused_freq_hz
    if focused is not None and abs(focused - AU_ADSB_FREQUENCY_HZ) > FREQ_TOLERANCE_HZ:
        return

    merged = _field_tracker.update(msg)
    callsign_str = merged["callsign"].strip() if merged["callsign"] else 'unknown'
    alt_str = str(merged["altitude_ft"]) + ' ft' if merged["altitude_ft"] is not None else 'unknown'
    speed_str = str(merged["groundspeed"]) + ' kt' if merged["groundspeed"] is not None else 'unknown'
    track_str = f'{merged["track"]:.0f} deg' if merged["track"] is not None else 'unknown'
    squawk_str = merged["squawk"] if merged["squawk"] else 'unknown'
    reasoning = (
        f'Confirmed ADS-B decode - ICAO {merged["icao"]}, callsign {callsign_str}, '
        f'altitude {alt_str}, speed {speed_str}, track {track_str}, squawk {squawk_str}'
    )

    socketio.emit('scan_result', {
        'timestamp': msg.timestamp.isoformat(),
        'center_freq_hz': AU_ADSB_FREQUENCY_HZ,
        'signal_type': 'adsb',
        'confidence': 'high',
        'confidence_score': 1.0,
        'novel': False,
        'au_legal_status': 'legal_rx',
        'reasoning': reasoning,
        'peak_power_db': None,
        'snr_db': None,
        'peak_bin_power_db': None,
        # Phase 45 burst-detection fields. Always None on the decoder
        # path because the decoder does not produce a fingerprint —
        # included so the payload SHAPE matches broadcast() and the
        # frontend does not have to special-case missing keys.
        # TODO(tech-debt TD-45-3): If future decoders produce fingerprints,
        # this parity pattern creates a contract divergence risk where the
        # decoder path must remember to include all fingerprint fields.
        # Consider a shared payload constructor or schema to avoid drift.
        'burst_ratio_db': None,
        'expected_noise_ratio_db': None,
        'burst_excess_db': None,
        'is_burst': None,
        'signal_threshold_db': None,
        'snr_margin_db': None,
        'bandwidth_hz': None,
        'spectral_flatness': None,
        'chroma_distance': None,
        'source': 'decode',
    })


@app.route("/api/frequencies")
def api_frequencies():
    """
    Return ACMA frequency reference entries with optional filtering.

    Query parameters:
        min_mhz=float    — only entries where freq_end_mhz >= min_mhz
        max_mhz=float    — only entries where freq_start_mhz <= max_mhz
        tagged_only=1    — only entries where mimir_band is not null

    Returns JSON array of matching entries (same schema as source file).
    """
    ref_path = os.path.join(
        os.path.dirname(__file__), "..", "data", "frequency_reference.json"
    )
    try:
        with open(ref_path, "r", encoding="utf-8") as f:
            entries = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("Failed to read frequency_reference.json: %s", exc)
        return jsonify({"error": str(exc)}), 500

    min_mhz = request.args.get("min_mhz", type=float)
    max_mhz = request.args.get("max_mhz", type=float)
    tagged_only = request.args.get("tagged_only", "0") == "1"

    results = []
    for entry in entries:
        if min_mhz is not None and entry["freq_end_mhz"] < min_mhz:
            continue
        if max_mhz is not None and entry["freq_start_mhz"] > max_mhz:
            continue
        if tagged_only and entry.get("mimir_band") is None:
            continue
        results.append(entry)

    return jsonify(results), 200


# Anchor for /api/replay path containment. Resolved once at import time,
# so it assumes the process CWD is the repository root (the same CWD
# assumption capture.py's default Path("data/captures") output_dir makes
# for every capture the system writes). Tests monkeypatch this constant.
_REPLAY_CAPTURES_DIR = Path("data/captures").resolve()


# Register HTTP routes and SocketIO handlers, and re-export the moved emitters
# and handlers for scan.py and existing importers. Keep this block at the
# bottom because these modules import this module.
from dashboard import routes_pages, routes_radar, routes_capture, routes_replay, routes_vectorstore  # noqa: E402,F401
from dashboard.emitters import emit_acars_message, emit_ais_message, emit_adsb_aircraft  # noqa: E402,F401
from dashboard.socket_handlers import handle_set_focus, handle_set_capture_trigger  # noqa: E402,F401
