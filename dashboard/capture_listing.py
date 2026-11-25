"""Pure metadata parsing and sorting for dashboard capture listings.

Legal: Receive-only. Radiocommunications Act 1992 (Cth).
       No transmission. Jurisdiction: AU/SA. Authority: ACMA.
"""

import json
import logging
import math
import re
from pathlib import Path

from core.pipeline.replay import MAX_SEQUENCE_ENTRIES

logger = logging.getLogger(__name__)


# Timestamp used to age-sort captures; group matches YYYYMMDD_HHMMSS in
# capture_<freq>hz_YYYYMMDD_HHMMSS.sigmf-meta filenames, optionally suffixed
# with _N before .sigmf-meta when saves share a timestamp.
_CAPTURE_FILENAME_RE = re.compile(
    r"capture_(\d+)hz_(\d{8})_(\d{6})(?:_\d+)?\.sigmf-meta$"
)


def _parse_capture_meta_entry(path: Path) -> dict:
    """Parse a .sigmf-meta Path into the api_captures entry dict.

    Uses json.load() so the .sigmf-data sibling is never touched.
    Any failure produces an "unknown" entry with an "error" key.
    Record sequences must be lists within MAX_SEQUENCE_ENTRIES; one-shot
    fingerprints must be dicts. Invalid shapes keep chunk_count at zero.
    Non-finite capture frequencies are listed as None.
    """
    entry = {
        "filename": path.name,
        "mode": "unknown",
        "chunk_count": 0,
        "core_frequency_hz": None,
        "device": None,
        "timestamp": _parse_capture_timestamp(path.name),
    }

    try:
        with path.open("r", encoding="utf-8") as fh:
            meta = json.load(fh)
    except Exception as exc:  # broad, per spec: JSON, Unicode, OSError...
        entry["error"] = f"could not read metadata: {exc}"
        logger.warning("Capture metadata unreadable: %s — %s", path.name, exc)
        return entry

    try:
        global_fields = meta.get("global", {}) if isinstance(meta, dict) else {}
        captures = meta.get("captures", []) if isinstance(meta, dict) else []
        capture_record = captures[0] if captures else {}
        if not isinstance(capture_record, dict):
            capture_record = {}

        if "mimir:fingerprint_sequence" in global_fields:
            sequence = global_fields["mimir:fingerprint_sequence"]
            if (
                isinstance(sequence, list)
                and len(sequence) > MAX_SEQUENCE_ENTRIES
            ):
                entry["error"] = "mimir:fingerprint_sequence exceeds entry cap"
            elif isinstance(sequence, list):
                entry["mode"] = "record"
                entry["chunk_count"] = len(sequence)
            else:
                entry["error"] = "mimir:fingerprint_sequence is not a list"
        elif "mimir:fingerprint" in global_fields:
            if isinstance(global_fields["mimir:fingerprint"], dict):
                entry["mode"] = "oneshot"
                entry["chunk_count"] = 1
            else:
                entry["error"] = "mimir:fingerprint is not a dict"

        core_freq = capture_record.get("core:frequency")
        if core_freq is not None:
            try:
                frequency = float(core_freq)
                entry["core_frequency_hz"] = (
                    frequency if math.isfinite(frequency) else None
                )
            except (TypeError, ValueError):
                entry["core_frequency_hz"] = None

        device = global_fields.get("mimir:device_profile")
        if device is not None:
            entry["device"] = str(device)
    except Exception as exc:
        entry["error"] = f"metadata parse error: {exc}"
        logger.warning("Capture metadata parse error: %s — %s", path.name, exc)

    return entry


def _parse_capture_timestamp(filename: str) -> str | None:
    """Return an ISO timestamp string from a capture filename string, or None."""
    match = _CAPTURE_FILENAME_RE.search(filename)
    if not match:
        return None
    date_part, time_part = match.group(2), match.group(3)
    return (
        f"{date_part[:4]}-{date_part[4:6]}-{date_part[6:8]}"
        f"T{time_part[:2]}:{time_part[2:4]}:{time_part[4:6]}"
    )


def _capture_sort_key(entry: dict) -> tuple[str, str]:
    """Return timestamp and filename strings for descending capture sorting.

    Entries without a timestamp are pushed to the end by using an
    empty string for the primary key. Filename provides a stable
    secondary sort.
    """
    return (entry.get("timestamp") or "", entry.get("filename") or "")
