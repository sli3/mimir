"""AIS (Automatic Identification System) decoder package.

Pure-Python GMSK demodulation, HDLC frame extraction, and NMEA decoding
for AIS maritime VHF signals.

Legal: passive receive only.  Radiocommunications Act 1992 (Cth).
Jurisdiction: AU / SA.  Authority: ACMA.
"""

from modules.ais.decoder import AisDecoder
from modules.ais.demodulator import AisDemodulator
from modules.ais.message import AisMessage
from modules.ais.subscriber import AisSubscriber

__all__ = [
    "AisDecoder",
    "AisDemodulator",
    "AisMessage",
    "AisSubscriber",
]
