"""
dashboard/server.py — Flask + SocketIO Backend for the Mimir Dashboard

Legal: Receive-only. Radiocommunications Act 1992 (Cth).
       No transmission. Jurisdiction: AU/SA. Authority: ACMA.

WHAT THIS FILE DOES
───────────────────
Provides the HTTP and WebSocket backend that the cyberpunk React
dashboard connects to. Serves two roles:

1. Static file serving — the Vite build output in dashboard/static/
   is served at the root URL.

2. Real-time data — Flask-SocketIO pushes scan_result, spectrum_update,
   and system_stats events to connected browsers. Also accepts
   set_focus_frequency events from the browser to change which frequency
   the scanner dwells on.

3. REST API — GET /api/frequencies returns ACMA frequency reference
   entries with optional query-parameter filtering (min_mhz, max_mhz,
   tagged_only).

CONSTRAINTS
───────────
- async_mode='threading' — do not change to eventlet or gevent.
- broadcast() and broadcast_spectrum() are defined inside start_server()
  and are not importable directly. Retrieve via start_server._broadcast_fn
  and start_server._broadcast_spectrum_fn after calling start_server().
"""

import json
import logging
import os
import re
import threading
import time
from typing import Any

import numpy as np
from flask import Flask, jsonify, request
from flask_socketio import SocketIO

from core.pipeline.scan_result import ScanResult
from embeddings.store import SignalStore
from llm.path_reasoner import PathReasoner
from modules.acars.message import AcarsMessage
from modules.adsb.message import AdsbMessage
from modules.adsb.constants import (
    AIRCRAFT_EXPIRY_SEC,
    AU_ADSB_FREQUENCY_HZ,
    FREQ_TOLERANCE_HZ,
    MAX_AIRCRAFT,
)
from modules.ais.message import AisMessage
import dashboard.shared_state as shared_state

from pyModeS import decode

logger = logging.getLogger(__name__)


class AdsbFieldTracker:
    """Per-ICAO merge of the disjoint field sets carried by ADS-B frames.

    ADS-B frames carry disjoint field sets by typecode: a typecode 4 frame
    carries only a callsign, a typecode 19 frame carries velocity (no
    callsign or altitude), and typecodes 9-18 carry position and altitude
    only.  Building the AI Reasoning string from the single triggering
    frame therefore reported "unknown" for fields an earlier frame for the
    same aircraft had already resolved.  This tracker keeps the last known
    non-None value of each field per ICAO so the reasoning string can be
    built from the merged view, matching what the dashboard's own ADS-B
    AIRCRAFT table already shows (merged on the frontend by BUG-06 /
    mergeAircraftRecord.js).

    Merge semantics: any non-None field on an incoming message overwrites
    the stored value; any None field leaves the stored value untouched.

    Retention discipline mirrors ``modules/adsb/bearing_tracker.py``:
    entries older than ``AIRCRAFT_EXPIRY_SEC`` are swept lazily on each
    ``update()`` call (no separate timer), and if the table reaches
    ``MAX_AIRCRAFT`` the oldest entry (by stored timestamp) is dropped on
    the next insert of an untracked ICAO.  On tied timestamps the eviction
    choice depends on dict insertion order; acceptable for a display aid.

    Single-producer assumption: in steady state ``emit_adsb_scan_result()``
    is only called from AdsbSubscriber's decode thread. The shutdown
    flush in ``AdsbSubscriber.stop()`` runs on the caller's thread and can
    briefly overlap the decode thread for a small window — the same
    pre-existing pattern as TD-48-1 for BearingTracker. No lock is taken:
    the overlap is benign (display aid, GIL-atomic dict ops, the two
    threads typically target different ICAOs).

    If a 7th field is ever tracked, both ``_FIELDS`` (used by ``update()``)
    and any consumer of the returned dict must be extended in lockstep:
    same pattern-divergence risk as TD-45-3.
    """

    # Tracked field names on AdsbMessage.  vertical_rate is merged here but
    # intentionally not shown in the reasoning string (per Phase 50 plan).
    # squawk (Phase 54) is merged and shown: DF5 identity replies carry it.
    _FIELDS = ("callsign", "altitude_ft", "groundspeed", "track", "vertical_rate", "squawk")

    def __init__(self) -> None:
        # icao_key -> {field_name: last_known_value, "_ts": datetime}
        self._state: dict[str, dict[str, Any]] = {}

    def update(self, msg: AdsbMessage) -> dict[str, Any]:
        """Merge one decoded ADS-B message into the stored per-ICAO view.

        Args:
            msg: Decoded ADS-B message from AdsbDecoder.

        Returns:
            The current merged view for the message's ICAO: a dict with
            keys ``icao`` (normalised: stripped, upper-cased) plus one key
            per tracked field, each holding the last known non-None value
            or None if that field has never been resolved for this ICAO.
        """
        # Eviction-first ensures an expired ICAO's next message is treated
        # as a fresh aircraft (see test_expired_aircraft_treated_as_fresh).
        self._evict_stale(msg.timestamp)

        icao_key = str(msg.icao).strip().upper()
        entry = self._state.get(icao_key)
        if entry is None:
            if len(self._state) >= MAX_AIRCRAFT:
                oldest_key = min(self._state, key=lambda k: self._state[k]["_ts"])
                del self._state[oldest_key]
            entry = {field: None for field in self._FIELDS}
            self._state[icao_key] = entry

        for field in self._FIELDS:
            value = getattr(msg, field, None)
            if value is not None:
                entry[field] = value
        entry["_ts"] = msg.timestamp

        merged: dict[str, Any] = {"icao": icao_key}
        for field in self._FIELDS:
            merged[field] = entry[field]
        return merged

    def _evict_stale(self, now) -> None:
        """Sweep entries older than ``AIRCRAFT_EXPIRY_SEC``.

        Called lazily from ``update()`` so a stale ICAO's next message is
        treated as a fresh aircraft.  No separate timer is used.
        """
        stale = [
            key
            for key, entry in self._state.items()
            if (now - entry["_ts"]).total_seconds() > AIRCRAFT_EXPIRY_SEC
        ]
        for key in stale:
            del self._state[key]


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
# AdsbFieldTracker docstring; mirrors the design of
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


# ── /api/radar/reason payload validation (Phase 53) ──────────────────────────
# Whitelist charsets and numeric ranges applied BEFORE any value is
# interpolated into an LLM prompt. Anything outside the whitelist is a 400;
# nothing the operator (or a crafted request) sends can reach the LLM raw.

_REASON_CALLSIGN_RE = re.compile(r"^[A-Z0-9 ]{1,8}$")
_REASON_SQUAWK_RE = re.compile(r"^[0-7]{4}$")
_REASON_ICAO_RE = re.compile(r"^[0-9A-Fa-f]{6}$")

# Numeric fields that must always be present and finite: (min, max).
_REASON_NUMERIC_RANGES = {
    "bearing_deg": (0.0, 360.0),
    "range_nm": (0.0, 1000.0),
    # Widened from ±30 to ±90 in Phase 55: this bound's job is
    # prompt-injection defence, not physical plausibility filtering —
    # ±90 discharges that duty identically while removing the
    # false-positive risk on a legitimate close overhead pass (computed:
    # >30°/s occurs inside ~0.16 nm at 300kt groundspeed). Do not widen
    # any other bound without separate review.
    "theta_deg_per_sec": (-90.0, 90.0),
    "delta_r_nm_per_sec": (-1.0, 1.0),
    "projected_bearing_deg": (0.0, 360.0),
    "projected_range_nm": (0.0, 1000.0),
}
# Per-frame ADS-B fields that legitimately arrive as null (velocity and
# position travel in disjoint Mode S typecodes). Null passes through; a
# non-null value must be finite and in range.
_REASON_NULLABLE_NUMERIC_RANGES = {
    "altitude_ft": (-1000.0, 100000.0),
    "groundspeed": (0.0, 700.0),
    "track": (0.0, 360.0),
    "vertical_rate": (-12000.0, 12000.0),
}


def _coerce_finite_float(value):
    """Coerce to a finite float, or return None on any failure.

    Rejects NaN and Infinity (json.loads accepts both by default, so they
    CAN arrive over the wire), booleans, non-numeric strings, and None.
    """
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not (result == result) or result in (float("inf"), float("-inf")):
        return None
    return result


def _validate_reason_payload(data: dict) -> tuple[dict, str | None]:
    """Validate and clean a POST /api/radar/reason JSON body.

    Returns:
        (cleaned, None) on success — cleaned holds only the known keys,
        coerced to their expected types.
        ({}, error_message) on any validation failure — the route turns
        this into a 400 with the message.
    """
    icao = data.get("icao")
    if not isinstance(icao, str) or not _REASON_ICAO_RE.fullmatch(icao):
        return {}, "Invalid icao (want 6 hex characters)"

    callsign = data.get("callsign")
    if callsign is None:
        # No callsign frame decoded yet for this ICAO — valid real state.
        callsign = None
    elif isinstance(callsign, str) and _REASON_CALLSIGN_RE.fullmatch(callsign.upper()):
        callsign = callsign.upper()
    else:
        return {}, "Invalid callsign (want 1-8 chars of A-Z, 0-9, space)"

    squawk = data.get("squawk")
    if squawk is not None:
        if not isinstance(squawk, str) or not _REASON_SQUAWK_RE.fullmatch(squawk):
            return {}, "Invalid squawk (want 4 octal digits)"

    cleaned: dict[str, Any] = {
        "icao": icao.upper(),
        "callsign": callsign,
        "squawk": squawk,
    }

    for field, (lo, hi) in _REASON_NUMERIC_RANGES.items():
        value = _coerce_finite_float(data.get(field))
        if value is None:
            return {}, f"Invalid {field} (want a finite number)"
        if not (lo <= value <= hi):
            return {}, f"Invalid {field} (out of range {lo}..{hi})"
        cleaned[field] = value

    for field, (lo, hi) in _REASON_NULLABLE_NUMERIC_RANGES.items():
        raw = data.get(field)
        if raw is None:
            cleaned[field] = None
            continue
        value = _coerce_finite_float(raw)
        if value is None:
            return {}, f"Invalid {field} (want a finite number or null)"
        if not (lo <= value <= hi):
            return {}, f"Invalid {field} (out of range {lo}..{hi})"
        cleaned[field] = value

    trail_raw = data.get("trail_length")
    if isinstance(trail_raw, bool):
        return {}, "Invalid trail_length (want an integer)"
    try:
        trail_length = int(float(trail_raw))
    except (TypeError, ValueError):
        return {}, "Invalid trail_length (want an integer)"
    if not (0 <= trail_length <= 1000):
        return {}, "Invalid trail_length (out of range 0..1000)"
    cleaned["trail_length"] = trail_length

    return cleaned, None


@socketio.on("set_focus_frequency")
def handle_set_focus(data):
    """Set or clear the focused frequency filter for scan_result emissions.

    Coerces freq_hz to float. Non-numeric or missing values clear the focus
    (set to None, meaning all frequencies pass through). When a scanner
    reference is available, also calls scanner.set_focus_frequency() to
    retune the HackRF and flush any queued results.

    Also updates shared_state.current_band to the matching BAND_PROFILES entry
    when freq_hz corresponds to a known band centre frequency, so the scan loop
    applies the correct per-band signal_threshold_db without a restart.

    Args:
        data: Dict from the browser with key "freq_hz". Values accepted:
              numeric (int/float), string numeric, None (clear focus),
              or missing key (clear focus).
    """
    global _focused_freq_hz
    raw = data.get("freq_hz")
    try:
        freq_hz = float(raw) if raw is not None else None
    except (TypeError, ValueError):
        freq_hz = None
    with _focused_freq_lock:
        _focused_freq_hz = freq_hz
    band_profile = (
        shared_state.get_band_for_freq(freq_hz)
        or shared_state.get_nearest_band_for_freq(freq_hz)
    )
    if band_profile is not None:
        with shared_state.current_band_lock:
            shared_state.current_band = band_profile
    if _scanner_ref is not None:
        _scanner_ref.set_focus_frequency(freq_hz)


def record_hw_error() -> None:
    global _last_hw_error_time
    _last_hw_error_time = time.time()


def _compute_hackrf_status() -> str:
    if _device_ref is None or not _device_ref.is_open:
        return "DISCONNECTED"
    if time.time() - _last_hw_error_time < 5.0:
        return "NOT_RESPONDING"
    return "CONNECTED"


def start_server(host: str, port: int, device=None, scanner=None):
    """
    Start the Flask-SocketIO dashboard server in a background thread.

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
        start_server._broadcast_spectrum_fn — emit a spectrum_update event
    """
    global _device_ref, _scanner_ref
    _device_ref = device
    _scanner_ref = scanner

    def run_flask():
        socketio.run(app, host=host, port=port, debug=False, use_reloader=False)

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
        if focused is not None and scan_result.center_freq_hz != focused:
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

    def broadcast_spectrum(
        psd_db: list,
        center_freq_hz: float,
        freq_min_hz: float,
        freq_max_hz: float,
    ) -> None:
        data = {
            "psd_db": psd_db.tolist() if hasattr(psd_db, 'tolist') else psd_db,
            "center_freq_hz": center_freq_hz,
            "freq_min_hz": freq_min_hz,
            "freq_max_hz": freq_max_hz,
        }
        socketio.emit("spectrum_update", data)

    start_server._broadcast_fn = broadcast
    start_server._broadcast_spectrum_fn = broadcast_spectrum

    return broadcast


def emit_acars_message(msg: AcarsMessage) -> None:
    """Broadcast a decoded ACARS message to all connected browsers.

    Emits the ``acars_message`` SocketIO event with the decoded ACARS
    fields and a ``raw`` field containing the decoded ASCII message text
    (same as ``text``). The frontend ``useSocket`` hook extracts ``raw``
    into the ``acarsRawLog`` ring buffer, which the RAW DECODE section
    of the ACARS sub-panel renders as a scrollable monospace log.

    Payload fields:
        timestamp  — ISO-8601 string
        freq_hz    — receive frequency in Hz
        registration — aircraft registration (e.g. "VH-ABC")
        label      — ACARS label code
        block_id   — block identifier
        text       — decoded ACARS message text
        crc_ok     — whether the CRC-16 check passed
        raw        — raw decoded text shown in RAW DECODE panel
    """
    socketio.emit("acars_message", {
        "timestamp": msg.timestamp.isoformat(),
        "freq_hz": msg.freq_hz,
        "registration": msg.registration.strip(),
        "label": msg.label,
        "block_id": msg.block_id,
        "text": msg.text,
        "crc_ok": msg.crc_ok,
        "raw": msg.text,
    })


def emit_ais_message(msg: AisMessage) -> None:
    """Broadcast a decoded AIS message to all connected browsers.

    Emits the ``ais_message`` SocketIO event with the decoded AIS vessel
    fields and a ``raw`` field containing the original NMEA-0183 sentence
    text (e.g. ``!AIVDM,...``). The frontend ``useSocket`` hook extracts
    ``raw`` into the ``aisRawLog`` ring buffer, which the RAW DECODE
    section of the AIS sub-panel renders as a scrollable monospace log.

    Payload fields:
        timestamp    — ISO-8601 string (or raw if not datetime-parseable)
        mmsi         — Maritime Mobile Service Identity (9-digit)
        vessel_name  — decoded vessel name (falls back to "---")
        lat          — latitude in decimal degrees (or "---")
        lon          — longitude in decimal degrees (or "---")
        speed        — speed over ground in knots (or "---")
        course       — course over ground in degrees (or "---")
        channel      — AIS channel (A or B)
        raw          — NMEA-0183 sentence shown in RAW DECODE panel
    """
    socketio.emit("ais_message", {
        "timestamp": msg.timestamp.isoformat() if hasattr(msg.timestamp, "isoformat") else msg.timestamp,
        "mmsi": msg.mmsi,
        "vessel_name": msg.vessel_name or "---",
        "lat": msg.lat if msg.lat is not None else "---",
        "lon": msg.lon if msg.lon is not None else "---",
        "speed": msg.speed if msg.speed is not None else "---",
        "course": msg.course if msg.course is not None else "---",
        "channel": msg.channel,
        "raw": msg.raw_nmea,
    })


def emit_adsb_aircraft(msg: AdsbMessage) -> None:
    """Broadcast a decoded ADS-B aircraft message via SocketIO.

    Payload includes all decoded fields plus the raw hex Mode S frame
    for diagnostic display in the ADS-B panel. The raw_hex field
    carries the original DF17/DF18 frame as a hex string, enabling
    the frontend to show both hex and binary representations in the
    raw decode view. The range_nm field (great-circle distance from
    the receiver, computed by the backend BearingTracker) feeds the
    Phase 49 radar scope panel.
    """
    socketio.emit("adsb_aircraft", {
        "icao": msg.icao,
        "callsign": msg.callsign,
        "altitude_ft": msg.altitude_ft,
        "latitude": msg.latitude,
        "longitude": msg.longitude,
        "groundspeed": msg.groundspeed,
        "track": msg.track,
        "vertical_rate": msg.vertical_rate,
        "squawk": msg.squawk,
        "bearing_deg": getattr(msg, "bearing_deg", None),
        "delta_r_deg_per_sec": getattr(msg, "delta_r_deg_per_sec", None),
        "range_nm": getattr(msg, "range_nm", None),
        "timestamp": msg.timestamp.isoformat(),
        "raw_hex": msg.raw_hex,
    })


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


@app.route("/")
def index():
    from flask import send_from_directory
    return send_from_directory(
        os.path.join(os.path.dirname(__file__), "static"),
        "index.html"
    )


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


@app.route("/api/adsb/parse")
def api_adsb_parse():
    """
    Parse a raw ADS-B hex frame using pyModeS.

    Purpose: Decode a Mode S hex frame into structured ADS-B fields for display
    in the ADS-B panel's frame inspector. This is a decode-only endpoint with no
    hardware interaction or transmission capability.

    Input format: GET request with query parameter 'hex' containing the raw
    ADS-B hex string (e.g. "8D406B902015A678D4D220AA4BDA").

    Output format: JSON with decoded fields:
    {
        "df": int,              # downlink format
        "icao": str | null,     # ICAO address
        "crc_ok": bool | null,  # CRC validity
        "typecode": int | null, # message type code
        "message_type": str | null,  # human-readable message type
        "fields": {str: str}    # additional fields by typecode
    }

    Validation rules:
    - 400 error if hex parameter is missing or empty
    - 400 error if hex contains non-hex characters (not 0-9/A-F/a-f)
    - 400 error if hex string exceeds 32 characters (max length for Mode S frames)
    - 400 error if pyModeS.decode() raises an exception (invalid frame format)
    - 400 error if pyModeS returns a non-dict result

    Implementation notes:
    - pyModeS.decode() calls are wrapped in try/except to handle malformed frames
    - This endpoint is receive-only — no RF transmission or hardware control
    - Legal constraint: Radiocommunications Act 1992 (Cth), AU/SA jurisdiction, ACMA authority
    """
    hex_string = request.args.get("hex", "").strip()

    # REQ-1: Input validation
    if not hex_string:
        return jsonify({"error": "Missing hex parameter"}), 400

    # Enforce hex charset
    if not re.fullmatch(r"^[0-9A-Fa-f]+$", hex_string):
        return jsonify({"error": "Invalid hex characters"}), 400

    # Enforce length cap (extended squitter is 28 chars; short messages 14)
    if len(hex_string) > 32:
        return jsonify({"error": "Hex string too long (max 32 chars)"}), 400

    # REQ-2: All pyModeS calls wrapped in try/except
    try:
        result = decode(hex_string)
    except Exception as exc:
        logger.debug("pyModeS decode failed for %s: %s", hex_string, exc)
        return jsonify({"error": str(exc)}), 400

    # result is always a dict (Decoded or error-dict)
    if not isinstance(result, dict):
        logger.debug("pyModeS returned non-dict for %s: %s", hex_string, type(result))
        return jsonify({"error": "Decode returned invalid result"}), 400

    # Extract base fields
    df = result.get("df")
    icao = result.get("icao")
    crc_ok = result.get("crc_valid")
    typecode = result.get("typecode")

    # Build response
    response = {
        "df": df,
        "icao": icao,
        "crc_ok": crc_ok,
        "typecode": typecode,
        "message_type": None,
        "fields": {}
    }

    # Map typecodes to message types and extract fields
    if typecode is not None:
        try:
            if 1 <= typecode <= 4:
                response["message_type"] = "Aircraft identification"
                callsign = result.get("callsign")
                if callsign:
                    response["fields"]["Callsign"] = callsign.strip()
                category = result.get("category")
                if category is not None:
                    response["fields"]["Category"] = str(category)

            elif 5 <= typecode <= 8:
                response["message_type"] = "Surface position"
                altitude = result.get("altitude")
                if altitude is not None:
                    response["fields"]["Altitude"] = f"{altitude} ft"
                cpr_lat = result.get("cpr_lat")
                if cpr_lat is not None:
                    response["fields"]["CPR Latitude"] = str(cpr_lat)
                cpr_lon = result.get("cpr_lon")
                if cpr_lon is not None:
                    response["fields"]["CPR Longitude"] = str(cpr_lon)
                groundspeed = result.get("groundspeed")
                if groundspeed is not None:
                    response["fields"]["Groundspeed"] = f"{groundspeed:.0f} kt"
                track = result.get("track")
                if track is not None:
                    response["fields"]["Track"] = f"{track:.1f}°"

            elif 9 <= typecode <= 18:
                response["message_type"] = "Airborne position"
                altitude = result.get("altitude")
                if altitude is not None:
                    response["fields"]["Altitude"] = f"{altitude} ft"
                cpr_lat = result.get("cpr_lat")
                if cpr_lat is not None:
                    response["fields"]["CPR Latitude"] = str(cpr_lat)
                cpr_lon = result.get("cpr_lon")
                if cpr_lon is not None:
                    response["fields"]["CPR Longitude"] = str(cpr_lon)

            elif typecode == 19:
                response["message_type"] = "Airborne velocity"
                groundspeed = result.get("groundspeed")
                if groundspeed is not None:
                    response["fields"]["Speed"] = f"{groundspeed:.0f} kt"
                track = result.get("track")
                if track is not None:
                    response["fields"]["Track"] = f"{track:.1f}°"
                vertical_rate = result.get("vertical_rate")
                if vertical_rate is not None:
                    response["fields"]["Vertical rate"] = f"{vertical_rate:+.0f} ft/min"

            elif 20 <= typecode <= 22:
                response["message_type"] = "Airborne position (GNSS)"
                altitude = result.get("altitude")
                if altitude is not None:
                    response["fields"]["Altitude"] = f"{altitude} ft"
                cpr_lat = result.get("cpr_lat")
                if cpr_lat is not None:
                    response["fields"]["CPR Latitude"] = str(cpr_lat)
                cpr_lon = result.get("cpr_lon")
                if cpr_lon is not None:
                    response["fields"]["CPR Longitude"] = str(cpr_lon)

            elif typecode == 28:
                response["message_type"] = "Aircraft status"

            elif typecode == 29:
                response["message_type"] = "Target state and status"

            elif typecode == 31:
                response["message_type"] = "Aircraft operational status"

            else:
                response["message_type"] = f"Reserved (TC {typecode})"

        except Exception as exc:
            logger.debug("Field extraction failed for typecode %d: %s", typecode, exc)

    return jsonify(response), 200


@app.route("/api/radar/reason", methods=["POST"])
def api_radar_reason():
    """Run LLM trajectory reasoning over one aircraft's physics facts.

    Purpose: Backs the manual "request LLM analysis" button in the /radar
    Path & Trajectory Prediction panel (Phase 53). The browser sends the
    physics readout it already displays (position, motion vector, 45 s
    projection); the server validates every field against whitelists and
    ranges, then hands the cleaned facts to the shared PathReasoner.

    Input format: POST with a JSON body:
    {
        "icao": str (6 hex),                 — required
        "callsign": str (1-8 [A-Z0-9 ]) | null,
        "squawk": str (4 octal) | null,
        "altitude_ft": number | null,        — per-frame fields are
        "track": number | null,                legitimately null when the
        "groundspeed": number | null,          current frame's typecode
        "vertical_rate": number | null,        did not carry them
        "bearing_deg": number, "range_nm": number,
        "theta_deg_per_sec": number, "delta_r_nm_per_sec": number,
        "projected_bearing_deg": number, "projected_range_nm": number,
        "trail_length": int
    }

    Output format: always HTTP 200 with a structured body once validation
    has passed:
    {
        "status": "ok" | "unavailable",
        "verdict": str,       — one short headline line ("unavailable" on failure)
        "confidence": "high" | "medium" | "low",
        "notes": str,         — caveats, or why the call failed
        "cause": str | null   — "timeout" | "network" | "parse" | "http" |
                                "unknown" on failure; null on success
    }

    Validation rules (400 on failure — the ONLY non-200 path):
    - Body must be a JSON object.
    - icao / callsign / squawk must match their whitelist charsets.
    - Numeric fields must coerce to finite floats (NaN/Infinity rejected)
      and sit inside their documented ranges (see _REASON_NUMERIC_RANGES
      and _REASON_NULLABLE_NUMERIC_RANGES).

    LLM failures NEVER produce a 500: PathReasoner.reason() never raises,
    and any failure arrives here as status="unavailable" with a cause.

    Implementation notes:
    - This endpoint is receive-only — no RF transmission or hardware control.
    - Legal constraint: Radiocommunications Act 1992 (Cth), AU/SA
      jurisdiction, ACMA authority. ADS-B 1090 MHz is legal passive RX.
    """
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400

    cleaned, error = _validate_reason_payload(data)
    if error is not None:
        return jsonify({"error": error}), 400

    result = _get_path_reasoner().reason(cleaned)
    return jsonify({
        "status": result.status,
        "verdict": result.verdict,
        "confidence": result.confidence,
        "notes": result.notes,
        "cause": result.cause,
    }), 200


@app.route("/vectordb")
def vector_space_page():
    """Serve the React app for the isolated vector-space visualisation page.

    The /vectordb route is reached directly; the React entry point then
    inspects window.location.pathname and renders VectorSpacePage instead
    of the main dashboard App.

    Returns:
        Flask response: The index.html file for the VectorSpacePage React app.
    """
    from flask import send_from_directory
    return send_from_directory(
        os.path.join(os.path.dirname(__file__), "static"),
        "index.html"
    )


@app.route("/radar")
def radar_page():
    """Serve the React app for the isolated radar scope page.

    The /radar route is reached directly; the React entry point
    then inspects window.location.pathname and renders RadarPage
    instead of the main dashboard App.

    Returns:
        Flask response: The index.html file for the RadarPage React app.
    """
    from flask import send_from_directory
    return send_from_directory(
        os.path.join(os.path.dirname(__file__), "static"),
        "index.html"
    )


@app.route("/api/vectorstore/points")
def api_vectorstore_points():
    """Return all stored ChromaDB embeddings projected into 3D.

    This endpoint is read-only: it pulls existing vectors and metadata from
    the SignalStore and applies scikit-learn dimensionality reduction so the
    frontend can render the vector space as an interactive 3D scatter plot.

    Reduction strategy:
        * n == 0        -> empty response (no computation).
        * 1 <= n < 5    -> PCA to 3 components (t-SNE is unstable this small).
        * n >= 5        -> t-SNE with fixed random_state=42 for reproducible
                          demo layouts; perplexity is capped at min(30, n-1)
                          because t-SNE requires perplexity < n_samples.

    The resulting 3D coordinates are normalised to roughly [-10, 10] on each
    axis so the camera framing is stable regardless of raw magnitudes.

    Frequency metadata handling:
        * Seed data (RTL-ML) uses "center_freq_hz" key
        * Live captures (capture_to_vectorstore.py) use "freq_hz" key
        * The endpoint reads "center_freq_hz" first, falling back to "freq_hz"
          to support both record types and ensure the /vectordb tooltip FREQ field
          displays correctly for seeded records.

    Returns:
        JSON: {"status": "ok"|"empty", "count": int, "method": str|null,
               "points": [{id, x, y, z, label, frequency_hz, snr_db,
               peak_power_db, timestamp}, ...]}
    """
    try:
        store = _get_signal_store()

        with _VECTORSTORE_CACHE_LOCK:
            cached_count = _VECTORSTORE_CACHE["count"]
            cached_points = _VECTORSTORE_CACHE["points"]
            cached_method = _VECTORSTORE_CACHE["method"]
            if cached_count >= 0 and cached_points is not None:
                return jsonify({
                    "status": "ok",
                    "count": cached_count,
                    "method": cached_method,
                    "points": cached_points,
                }), 200

        # Cache miss: read embeddings and compute the projection.  This runs
        # under the cache lock so concurrent requests don't start multiple
        # expensive t-SNE jobs.
        with _VECTORSTORE_CACHE_LOCK:
            raw = store.get_all_embeddings()
            ids = raw["ids"]
            embeddings = raw["embeddings"]
            metadatas = raw["metadatas"]
            n = len(ids)

            if n == 0:
                return jsonify({
                    "status": "empty",
                    "count": 0,
                    "method": None,
                    "points": [],
                }), 200

            matrix = np.array(embeddings, dtype=float)

            # Lazy import scikit-learn so scan.py startup is not penalised for
            # a visualisation endpoint that is rarely hit.
            from sklearn.decomposition import PCA
            from sklearn.manifold import TSNE

            if n == 1:
                projected = np.zeros((1, 3), dtype=float)
                method = "pca"
            elif n < 5:
                n_components = min(3, n)
                reducer = PCA(n_components=n_components, random_state=42)
                method = "pca"
                projected = reducer.fit_transform(matrix)
                if projected.shape[1] < 3:
                    projected = np.pad(
                        projected,
                        ((0, 0), (0, 3 - projected.shape[1])),
                        mode="constant",
                    )
            else:
                reducer = TSNE(
                    n_components=3,
                    random_state=42,
                    perplexity=min(30, n - 1),
                )
                method = "tsne"
                projected = reducer.fit_transform(matrix)

            max_abs = np.max(np.abs(projected))
            if max_abs > 0:
                projected = (projected / max_abs) * 10.0

            points = []
            for i, record_id in enumerate(ids):
                meta = metadatas[i] or {}
                points.append({
                    "id": record_id,
                    "x": float(projected[i, 0]),
                    "y": float(projected[i, 1]),
                    "z": float(projected[i, 2]),
                    "label": str(meta.get("label") or "unknown"),
                    # Seed data uses "center_freq_hz"; live captures use "freq_hz".
                    "frequency_hz": meta.get("center_freq_hz", meta.get("freq_hz")),
                    "snr_db": meta.get("snr_db"),
                    "peak_power_db": meta.get("peak_power_db"),
                    "timestamp": meta.get("timestamp"),
                })

            _VECTORSTORE_CACHE["count"] = n
            _VECTORSTORE_CACHE["points"] = points
            _VECTORSTORE_CACHE["method"] = method

            return jsonify({
                "status": "ok",
                "count": n,
                "method": method,
                "points": points,
            }), 200

    except Exception as exc:
        logger.exception("Vector store projection failed: %s", exc)
        return jsonify({"error": "Vector store projection failed"}), 500
