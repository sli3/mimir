"""AdsbMessage dataclass — decoded ADS-B aircraft report.

Legal: passive receive only.  Radiocommunications Act 1992 (Cth).
Jurisdiction: AU / SA.  Authority: ACMA.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class AdsbMessage:
    """A single decoded ADS-B extended squitter message."""

    icao: str                          # 6-char hex, e.g. "7C4B4C"
    callsign: str | None               # flight code, e.g. "QFA456"
    altitude_ft: int | None            # barometric altitude in feet
    latitude: float | None             # degrees, from PipeDecoder global CPR pair resolution (no fixed reference)
    longitude: float | None            # degrees, from PipeDecoder global CPR pair resolution (no fixed reference)
    groundspeed: float | None          # knots
    track: float | None                # degrees true, 0-360
    vertical_rate: int | None          # ft/min, positive = climbing
    raw_hex: str                       # original hex string from demodulator
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
