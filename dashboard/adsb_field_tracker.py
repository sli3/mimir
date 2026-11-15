"""Per-ICAO ADS-B field merging for dashboard reasoning.

Legal: Receive-only. Radiocommunications Act 1992 (Cth).
       No transmission. Jurisdiction: AU/SA. Authority: ACMA.
"""

from typing import Any

from modules.adsb.message import AdsbMessage
from modules.adsb.constants import AIRCRAFT_EXPIRY_SEC, MAX_AIRCRAFT


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
