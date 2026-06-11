"""AcarsMessage dataclass — decoded ACARS frame payload.

Legal: passive receive only.  Radiocommunications Act 1992 (Cth).
Jurisdiction: AU / SA.  Authority: ACMA.
"""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class AcarsMessage:
    """A single decoded ACARS downlink message."""

    timestamp: datetime
    freq_hz: float
    mode: str
    registration: str       # aircraft tail number, e.g. 'VH-OGE'
    label: str              # 2-char message type, e.g. 'H1', 'SA', 'B2'
    block_id: str           # single char block sequence identifier
    text: str               # decoded message body (may be empty)
    crc_ok: bool            # True if CRC-16 validated successfully
    error_count: int = 0    # number of parity errors detected
