"""ACARS decoder module — pure-Python subscriber on Mimir's IQ bus.

Legal: passive receive only.  Radiocommunications Act 1992 (Cth).
Jurisdiction: AU / SA.  Authority: ACMA.
"""

from modules.acars.constants import (
    AU_ACARS_FREQUENCIES_HZ,
    ACARS_BAUD_RATE,
    ACARS_TONE_0,
    ACARS_TONE_1,
    PREAMBLE_BITS,
    FREQ_TOLERANCE_HZ,
)
from modules.acars.message import AcarsMessage
from modules.acars.demodulator import AcarsDemodulator
from modules.acars.decoder import AcarsDecoder
from modules.acars.subscriber import AcarsSubscriber

__all__ = [
    "AcarsSubscriber",
    "AcarsDemodulator",
    "AcarsDecoder",
    "AcarsMessage",
    "AU_ACARS_FREQUENCIES_HZ",
    "ACARS_BAUD_RATE",
    "ACARS_TONE_0",
    "ACARS_TONE_1",
    "PREAMBLE_BITS",
    "FREQ_TOLERANCE_HZ",
]
