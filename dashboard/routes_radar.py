"""Provide ADS-B frame parsing and radar trajectory reasoning routes.

Legal: Receive-only. Radiocommunications Act 1992 (Cth).
       No transmission. Jurisdiction: AU/SA. Authority: ACMA.
"""

import logging
import re

from flask import jsonify, request
from pyModeS import decode

import dashboard.server as _server
from dashboard.reason_validation import _validate_reason_payload

logger = logging.getLogger(__name__)


@_server.app.route("/api/adsb/parse")
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


@_server.app.route("/api/radar/reason", methods=["POST"])
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
      and _REASON_NULLABLE_NUMERIC_RANGES in dashboard/reason_validation.py).

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

    result = _server._get_path_reasoner().reason(cleaned)
    return jsonify({
        "status": result.status,
        "verdict": result.verdict,
        "confidence": result.confidence,
        "notes": result.notes,
        "cause": result.cause,
    }), 200
