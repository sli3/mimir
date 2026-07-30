"""Bearing / delta-r tracker for decoded ADS-B aircraft.

Computes the geometric great-circle initial bearing from the fixed Adelaide
receiver position to each aircraft's self-reported ADS-B position, and the
rate of change of that bearing (delta-r) between successive reports.

Legal: passive receive only.  Radiocommunications Act 1992 (Cth).
Jurisdiction: AU / SA.  Authority: ACMA.

This module performs no radio operations at all — it is pure computation on
already-decoded ``AdsbMessage`` objects.

Security gate advisory — NOT direction-finding:
    This is NOT angle-of-arrival / direction-finding.  There is no antenna
    array, no phase measurement, and no bearing derived from the radio
    signal itself.  The bearing is a geometric great-circle initial bearing
    from a fixed reference point to the aircraft's self-reported ADS-B
    position.  It is a derived display aid only; the operator must not infer
    DF / antenna capability from this number.

Sign convention for ``delta_r_deg_per_sec``:
    Positive means the bearing angle is increasing (sweeping clockwise as
    seen from the fixed receiver position); negative means decreasing
    (anticlockwise).  This describes the angular motion of the LINE OF
    SIGHT from the receiver to the aircraft, NOT the aircraft's own
    heading / track.

Design note:
    The inner trigonometric functions (``initial_bearing_deg`` and
    ``angular_diff_deg``) are intentionally decoupled from ``AdsbMessage``
    and from the ADS-B constants so they can be reused by a future
    non-ADS-B bearing source.  Only the ``BearingTracker`` class imports
    ADS-B-specific symbols.
"""

import math
from dataclasses import dataclass
from datetime import datetime

from modules.adsb.constants import ADELAIDE_LAT, ADELAIDE_LON, AIRCRAFT_EXPIRY_SEC, MAX_AIRCRAFT
from modules.adsb.message import AdsbMessage


def initial_bearing_deg(lat1_deg: float, lon1_deg: float, lat2_deg: float, lon2_deg: float) -> float:
    """Great-circle initial bearing from point 1 to point 2.

    Args:
        lat1_deg: Latitude of the origin point, in degrees.
        lon1_deg: Longitude of the origin point, in degrees.
        lat2_deg: Latitude of the destination point, in degrees.
        lon2_deg: Longitude of the destination point, in degrees.

    Returns:
        Initial bearing in degrees, normalised to 0-360.  A coincident
        pair returns 0.0 (``atan2(0, 0)`` is 0 — a documented convention,
        not a real measurement).
    """
    phi1 = math.radians(lat1_deg)
    phi2 = math.radians(lat2_deg)
    delta_lambda = math.radians(lon2_deg - lon1_deg)
    y = math.sin(delta_lambda) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(delta_lambda)
    theta = math.atan2(y, x)
    return (math.degrees(theta) + 360) % 360


def angular_diff_deg(a_deg: float, b_deg: float) -> float:
    """Signed angular difference ``a - b``, wraparound-safe across 0/360.

    Args:
        a_deg: First angle, in degrees.
        b_deg: Second angle, in degrees.

    Returns:
        Signed difference in the range [-180, 180).  For example,
        ``angular_diff_deg(5, 355)`` is +10 (sweeping CCW past 360/0) and
        ``angular_diff_deg(355, 5)`` is -10.
    """
    return ((a_deg - b_deg + 180) % 360) - 180


@dataclass
class BearingReport:
    """Result of one bearing update for a single aircraft."""

    icao: str                          # normalised ICAO key (stripped, upper-cased)
    bearing_deg: float                 # initial bearing, 0-360, from the fixed receiver position
    delta_r_deg_per_sec: float | None  # bearing rate of change; None when no valid prior reading
    timestamp: datetime                # timestamp of the message that produced this report


class BearingTracker:
    """Track per-aircraft bearing and bearing-rate from ADS-B positions.

    Maintains one (bearing, timestamp) entry per ICAO.  The first position
    report for an aircraft yields a bearing with ``delta_r_deg_per_sec=None``
    (no rate without two readings); subsequent reports yield a rate computed
    against the stored prior reading.

    Retention discipline mirrors the ADS-B decoder: entries older than
    ``AIRCRAFT_EXPIRY_SEC`` are swept lazily on each ``update()`` call (no
    separate timer), and if the table reaches ``MAX_AIRCRAFT`` the oldest
    entry is dropped on the next insert.

    This tracker is not wired into the live subscriber broadcast path; it
    consumes ``AdsbMessage`` objects supplied by the caller.
    """

    def __init__(self, ref_lat_deg: float = ADELAIDE_LAT, ref_lon_deg: float = ADELAIDE_LON) -> None:
        self._ref_lat_deg = ref_lat_deg
        self._ref_lon_deg = ref_lon_deg
        # icao_key -> (bearing_deg, timestamp)
        self._state: dict[str, tuple[float, datetime]] = {}

    def update(self, msg: AdsbMessage) -> BearingReport | None:
        """Update tracker state from one decoded ADS-B message.

        Args:
            msg: Decoded ADS-B message.  Messages with unresolved position
                (``latitude`` or ``longitude`` is None — CPR not yet
                resolved, a normal expected state) are ignored.

        Returns:
            A ``BearingReport`` with the current bearing and, when a valid
            prior reading exists, the bearing rate of change in degrees per
            second.  ``None`` if the message carries no position.
        """
        # Short-circuit before any trigonometry — never feed None into
        # math.sin / math.cos.
        if msg.latitude is None or msg.longitude is None:
            return None

        self._evict_stale(msg.timestamp)

        bearing = initial_bearing_deg(self._ref_lat_deg, self._ref_lon_deg, msg.latitude, msg.longitude)
        icao_key = str(msg.icao).strip().upper()

        delta_r: float | None = None
        prev = self._state.get(icao_key)
        if prev is not None:
            prev_bearing, prev_ts = prev
            elapsed_sec = (msg.timestamp - prev_ts).total_seconds()
            if elapsed_sec > 0:
                delta_r = angular_diff_deg(bearing, prev_bearing) / elapsed_sec
            # elapsed_sec <= 0 means a duplicate or out-of-order message:
            # no rate is computed.  State is only updated below when the new
            # message is not older than the stored one, so a stale reading
            # never rolls back a more-recent one.

        if prev is None or msg.timestamp >= prev[1]:
            self._insert(icao_key, bearing, msg.timestamp)

        return BearingReport(
            icao=icao_key,
            bearing_deg=bearing,
            delta_r_deg_per_sec=delta_r,
            timestamp=msg.timestamp,
        )

    def _insert(self, icao_key: str, bearing: float, timestamp: datetime) -> None:
        """Store a reading, dropping the oldest entry if at capacity."""
        if icao_key not in self._state and len(self._state) >= MAX_AIRCRAFT:
            oldest_key = min(self._state, key=lambda k: self._state[k][1])
            del self._state[oldest_key]
        self._state[icao_key] = (bearing, timestamp)

    def _evict_stale(self, now: datetime) -> None:
        """Sweep entries older than ``AIRCRAFT_EXPIRY_SEC``.

        Called lazily from ``update()`` so a stale ICAO's next message is
        treated as a fresh aircraft.  No separate timer is used.
        """
        stale = [
            key
            for key, (_, ts) in self._state.items()
            if (now - ts).total_seconds() > AIRCRAFT_EXPIRY_SEC
        ]
        for key in stale:
            del self._state[key]
