"""AisMessage dataclass — decoded AIS vessel report.

Legal: passive receive only.  Radiocommunications Act 1992 (Cth).
Jurisdiction: AU / SA.  Authority: ACMA.
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class AisMessage:
    """A single decoded AIS message (position or static report)."""

    mmsi: str
    lat: float | None
    lon: float | None
    speed: float | None
    course: float | None
    vessel_name: str | None
    msg_type: int
    channel: str  # "A" or "B"
    timestamp: datetime
    raw_nmea: str
    freq_hz: float | None = None
