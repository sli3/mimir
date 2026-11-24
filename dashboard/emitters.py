"""
Broadcast decoded ACARS, AIS, ADS-B aircraft and scan results to browsers.

Legal: Receive-only. Radiocommunications Act 1992 (Cth).
       No transmission. Jurisdiction: AU/SA. Authority: ACMA.

Four emitters send the acars_message, ais_message, adsb_aircraft and
decoder-driven scan_result SocketIO events.
Imported only by the import at the bottom of dashboard/server.py, which
must be the first module imported. Callers import these functions from
dashboard.server.
"""

import dashboard.server as _server
from modules.acars.message import AcarsMessage
from modules.adsb.constants import AU_ADSB_FREQUENCY_HZ, FREQ_TOLERANCE_HZ
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


def emit_adsb_scan_result(msg: AdsbMessage) -> None:
    """Emit a scan_result event for a confirmed ADS-B decode.

    Called by AdsbSubscriber whenever AdsbDecoder successfully decodes a frame
    (CRC valid, DF17/DF18, valid ICAO). Bypasses the LLM pipeline — a confirmed
    decode is ground truth, confidence = 1.0.

    Applies the focused-frequency filter used by broadcast() inside
    dashboard.lifecycle.start_server(): only emits if the current focused
    frequency is None (all frequencies pass through) or
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
    shape parity with broadcast() in dashboard.lifecycle.start_server(), so
    the frontend does not need to special-case missing keys.

    The reasoning string is built from the merged per-ICAO view maintained
    by ``dashboard.server._field_tracker`` (AdsbFieldTracker), rather than
    from the single triggering frame: ADS-B frames carry disjoint field sets
    by typecode, so a field an earlier frame already resolved would otherwise
    show "unknown" here
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
    with _server._focused_freq_lock:
        focused = _server._focused_freq_hz
    if focused is not None and abs(focused - AU_ADSB_FREQUENCY_HZ) > FREQ_TOLERANCE_HZ:
        return

    merged = _server._field_tracker.update(msg)
    callsign_str = merged["callsign"].strip() if merged["callsign"] else 'unknown'
    alt_str = str(merged["altitude_ft"]) + ' ft' if merged["altitude_ft"] is not None else 'unknown'
    speed_str = str(merged["groundspeed"]) + ' kt' if merged["groundspeed"] is not None else 'unknown'
    track_str = f'{merged["track"]:.0f} deg' if merged["track"] is not None else 'unknown'
    squawk_str = merged["squawk"] if merged["squawk"] else 'unknown'
    reasoning = (
        f'Confirmed ADS-B decode - ICAO {merged["icao"]}, callsign {callsign_str}, '
        f'altitude {alt_str}, speed {speed_str}, track {track_str}, squawk {squawk_str}'
    )

    _server.socketio.emit('scan_result', {
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
        # included so the payload SHAPE matches lifecycle's broadcast() and the
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
