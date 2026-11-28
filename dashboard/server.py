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

3. REST API: GET /api/frequencies lives in dashboard/routes_frequencies.py
   and returns ACMA frequency reference entries with optional query filtering
   (min_mhz, max_mhz, tagged_only). Other HTTP routes live in
   dashboard/routes_pages.py, dashboard/routes_radar.py,
   dashboard/routes_capture.py, dashboard/routes_replay.py and
   dashboard/routes_vectorstore.py. The bottom imports register routes on app.

Four decoded-message emitters live in dashboard/emitters.py and the SocketIO
handlers in dashboard/socket_handlers.py. Server startup, statistics and scan
broadcast callbacks live in dashboard/lifecycle.py. The bottom import block
registers handlers and re-exports emitters, handlers and lifecycle functions;
shared application state remains here.

Pure helpers live in dashboard/adsb_field_tracker.py,
dashboard/reason_validation.py and dashboard/capture_listing.py.

CONSTRAINTS
───────────
- async_mode='threading' — do not change to eventlet or gevent.
- broadcast() and broadcast_spectrum() are defined inside start_server()
  in dashboard/lifecycle.py and are not importable directly. Retrieve via
  start_server._broadcast_fn and start_server._broadcast_spectrum_fn after
  calling start_server().
  Spectrum updates are capped at 30 Hz and rounded to one decimal place.
"""

import logging
import os
import threading
import time
from pathlib import Path

from flask import Flask
from flask_socketio import SocketIO

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

    Read MIMIR_LLM_URL once, at first use, to override the configured LLM
    URL, even when the variable is empty. The cached singleton does not
    read it per request. load_config() supplies the Phase 53
    llm_reason_timeout_sec / llm_reason_cooldown_sec keys. If config loading
    fails, use the override with default reasoner settings; an unset or
    empty override leaves the reasoner unconfigured and serving a
    well-formed "unavailable" answer.

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
                        base_url=os.environ.get("MIMIR_LLM_URL", cfg.llm_url),
                        cooldown_sec=cfg.llm_reason_cooldown_sec,
                        timeout_sec=cfg.llm_reason_timeout_sec,
                    )
                except Exception as exc:
                    logger.warning(
                        "Config load failed for PathReasoner (%s); "
                        "using default reasoner settings with MIMIR_LLM_URL "
                        "if set", exc,
                    )
                    _path_reasoner = PathReasoner(
                        base_url=os.environ.get("MIMIR_LLM_URL", ""),
                    )
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


# Anchor for /api/replay path containment. Resolved once at import time,
# so it assumes the process CWD is the repository root (the same CWD
# assumption capture.py's default Path("data/captures") output_dir makes
# for every capture the system writes). Tests monkeypatch this constant.
_REPLAY_CAPTURES_DIR = Path("data/captures").resolve()


# Register HTTP routes and SocketIO handlers, and re-export emitters and
# lifecycle functions for scan.py and existing importers. Keep these imports
# after all definitions: these modules access shared state through _server.
from dashboard import routes_pages, routes_radar, routes_capture, routes_replay, routes_vectorstore, routes_frequencies  # noqa: E402,F401
from dashboard.emitters import emit_acars_message, emit_ais_message, emit_adsb_aircraft, emit_adsb_scan_result  # noqa: E402,F401
from dashboard.socket_handlers import handle_set_focus, handle_set_capture_trigger  # noqa: E402,F401
from dashboard.lifecycle import start_server, _run_socketio, _unsupported_bands_or_empty, _warned_unknown_devices  # noqa: E402,F401
