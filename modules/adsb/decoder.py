"""ADS-B decoder — Mode S extended squitter validation and field extraction.

Uses pyModeS v3 decode-only API.  No transmit or encode symbols are imported.

Legal: passive receive only.  Radiocommunications Act 1992 (Cth).
Jurisdiction: AU / SA.  Authority: ACMA.

TX-Safety Note:
    pyModeS is a decode-only library.  It parses Mode S / ADS-B hex strings
    and returns decoded fields.  It does not provide any transmit or encode
    functionality, and it does not interact with radio hardware.
"""

import logging

from pyModeS import decode as pms_decode

from modules.adsb.constants import ADELAIDE_LAT, ADELAIDE_LON
from modules.adsb.message import AdsbMessage

logger = logging.getLogger(__name__)


class AdsbDecoder:
    """Validate and decode ADS-B hex strings into ``AdsbMessage`` objects.

    Limitations:
        - CPR decoding uses a fixed reference position (Adelaide) via
          ``pyModeS.decode(msg, reference=(lat, lon))``.  This resolves
          airborne position (typecodes 9-18) only.  Surface position
          messages (typecodes 5-8) are not decoded because ``surface_ref``
          is not passed to pyModeS.  See Deferred Items below.
        - Without a CPR even/odd frame pair accumulator, position accuracy
          degrades beyond ~180 NM from the reference point.  All aircraft
          receivable at 1090 MHz from Adelaide are within this range.

    Deferred Items:
        - CPR pair accumulator: future enhancement to decode positions
          without a fixed reference by pairing even and odd CPR frames.
          Currently deferred because single-reference decoding is sufficient
          for Adelaide reception range.
    """

    def decode(self, raw_hex: str) -> AdsbMessage | None:
        """Decode a single ADS-B hex string.

        Args:
            raw_hex: 28-character hex string (14 bytes) from the demodulator.

        Returns:
            ``AdsbMessage`` on success, or ``None`` if the frame is not a
            valid ADS-B extended squitter.
        """
        if not raw_hex or len(raw_hex) != 28:
            return None

        # DEFERRED (surface position): pyModeS decode() with reference=
        # resolves airborne CPR (typecodes 9-18) only.  Surface position
        # messages (typecodes 5-8) require a separate surface_ref= kwarg
        # which is not passed here.  This means surface positions will not
        # be decoded.  When surface tracking is needed, pass
        # surface_ref=(ADELAIDE_LAT, ADELAIDE_LON) as well.
        try:
            result = pms_decode(
                raw_hex,
                reference=(ADELAIDE_LAT, ADELAIDE_LON),
            )
        except Exception:
            logger.debug("ADS-B pyModeS decode failed for %s", raw_hex, exc_info=True)
            return None

        if not isinstance(result, dict):
            return None

        if not result.get("crc_valid", False):
            return None

        df = result.get("df")
        if df not in (17, 18):
            return None

        typecode = result.get("typecode")
        if typecode is None or not (1 <= typecode <= 22):
            return None

        callsign = result.get("callsign")
        if callsign:
            callsign = callsign.strip()
            if callsign == "":
                callsign = None

        altitude_ft = result.get("altitude")
        if altitude_ft is not None:
            altitude_ft = int(altitude_ft)

        icao = str(result.get("icao", ""))
        if not icao:
            return None

        latitude = result.get("latitude")
        longitude = result.get("longitude")

        groundspeed = result.get("groundspeed")
        if groundspeed is not None:
            groundspeed = float(groundspeed)

        track = result.get("track")
        if track is None:
            # Some pyModeS versions/TCs expose heading instead of track
            track = result.get("heading")
        if track is not None:
            track = float(track)

        vertical_rate = result.get("vertical_rate")
        if vertical_rate is not None:
            vertical_rate = int(vertical_rate)

        return AdsbMessage(
            icao=icao,
            callsign=callsign,
            altitude_ft=altitude_ft,
            latitude=latitude,
            longitude=longitude,
            groundspeed=groundspeed,
            track=track,
            vertical_rate=vertical_rate,
            raw_hex=raw_hex,
        )
