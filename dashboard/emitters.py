"""
Broadcast decoded ACARS, AIS and ADS-B aircraft messages to browsers.

Legal: Receive-only. Radiocommunications Act 1992 (Cth).
       No transmission. Jurisdiction: AU/SA. Authority: ACMA.

Emits the acars_message, ais_message and adsb_aircraft SocketIO events.
Imported only by the import at the bottom of dashboard/server.py, which
must be the first module imported. Callers import these functions from
dashboard.server.
"""

import dashboard.server as _server
from modules.acars.message import AcarsMessage
from modules.adsb.message import AdsbMessage
from modules.ais.message import AisMessage


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
    _server.socketio.emit("acars_message", {
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
    _server.socketio.emit("ais_message", {
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
    _server.socketio.emit("adsb_aircraft", {
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
