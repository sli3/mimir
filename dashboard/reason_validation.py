"""Pure payload validation for dashboard radar reasoning.

Legal: Receive-only. Radiocommunications Act 1992 (Cth).
       No transmission. Jurisdiction: AU/SA. Authority: ACMA.
"""

import re
from typing import Any


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
