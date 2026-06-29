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

from flask import Flask, jsonify, request
from flask_socketio import SocketIO

from core.pipeline.scan_result import ScanResult
from modules.acars.message import AcarsMessage
from modules.adsb.message import AdsbMessage
from modules.adsb.constants import AU_ADSB_FREQUENCY_HZ, FREQ_TOLERANCE_HZ
from modules.ais.message import AisMessage
import dashboard.shared_state as shared_state

from pyModeS import decode

logger = logging.getLogger(__name__)

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
            data = {
                "hackrf_status": _compute_hackrf_status(),
                "active_frequency_hz": active_freq,
                "scan_count": scan_count,
                "queue_depth": queue_depth,
                "last_backlog": last_backlog,
                "llm_call_count": llm_call_count,
                "llm_last_inference_ms": llm_ms,
            }
            socketio.emit("system_stats", data)

    _stats_thread = threading.Thread(target=emit_stats, daemon=True)
    _stats_thread.start()

    def broadcast(scan_result: ScanResult) -> None:
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
            "snr_db": fp.get("snr_db"),
            # Per-band threshold fields — added in Phase 11
            "signal_threshold_db": fp.get("signal_threshold_db", 0.0),
            "snr_margin_db": fp.get("snr_margin_db", 0.0),
            "bandwidth_hz": fp.get("bandwidth_hz"),
            "spectral_flatness": fp.get("spectral_flatness"),
            "chroma_distance": fp.get("chroma_distance"),
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
    raw decode view.
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
    for those fields when an entry comes from this path.

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

    callsign_str = msg.callsign.strip() if msg.callsign else 'unknown'
    alt_str = str(msg.altitude_ft) + ' ft' if msg.altitude_ft is not None else 'unknown'
    reasoning = f'Confirmed ADS-B decode - ICAO {msg.icao}, callsign {callsign_str}, altitude {alt_str}'

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
        'signal_threshold_db': None,
        'snr_margin_db': None,
        'bandwidth_hz': None,
        'spectral_flatness': None,
        'chroma_distance': None,
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
