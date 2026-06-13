"""ADS-B (Automatic Dependent Surveillance-Broadcast) decoder package.

Pure-Python amplitude-only demodulation and pyModeS decoding for ADS-B
aircraft transponder signals at 1090 MHz.

Legal: passive receive only.  Radiocommunications Act 1992 (Cth).
Jurisdiction: AU / SA.  Authority: ACMA.
"""

from modules.adsb.constants import (
    ADELAIDE_LAT,
    ADELAIDE_LON,
    AIRCRAFT_EXPIRY_SEC,
    AU_ADSB_FREQUENCY_HZ,
    DATA_BITS,
    DATA_SAMPLES,
    FREQ_TOLERANCE_HZ,
    MAX_AIRCRAFT,
    MESSAGE_SAMPLES,
    PREAMBLE_HIGH_INDICES,
    PREAMBLE_LOW_INDICES,
    PREAMBLE_SAMPLES,
    PREAMBLE_THRESHOLD,
)
from modules.adsb.decoder import AdsbDecoder
from modules.adsb.demodulator import AdsbDemodulator
from modules.adsb.message import AdsbMessage
from modules.adsb.subscriber import AdsbSubscriber

__all__ = [
    "AdsbSubscriber",
    "AdsbDemodulator",
    "AdsbDecoder",
    "AdsbMessage",
    "AU_ADSB_FREQUENCY_HZ",
    "FREQ_TOLERANCE_HZ",
    "ADELAIDE_LAT",
    "ADELAIDE_LON",
    "MAX_AIRCRAFT",
    "AIRCRAFT_EXPIRY_SEC",
    "PREAMBLE_THRESHOLD",
    "PREAMBLE_HIGH_INDICES",
    "PREAMBLE_LOW_INDICES",
    "PREAMBLE_SAMPLES",
    "DATA_BITS",
    "DATA_SAMPLES",
    "MESSAGE_SAMPLES",
]
