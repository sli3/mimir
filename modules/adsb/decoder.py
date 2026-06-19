"""ADS-B decoder — Mode S extended squitter validation and field extraction.

Uses pyModeS v3 PipeDecoder for stateful CPR pair accumulation.  No transmit or
encode symbols are imported.

Legal: passive receive only.  Radiocommunications Act 1992 (Cth).
Jurisdiction: AU / SA.  Authority: ACMA.

TX-Safety Note:
    pyModeS is a decode-only library.  It parses Mode S / ADS-B hex strings
    and returns decoded fields.  It does not provide any transmit or encode
    functionality, and it does not interact with radio hardware.
"""

import logging
import time

from pyModeS import Decoded, PipeDecoder

from modules.adsb.message import AdsbMessage

logger = logging.getLogger(__name__)

FLUSH_INTERVAL_SEC: float = 5.0


class AdsbDecoder:
    """Validate and decode ADS-B hex strings into ``AdsbMessage`` objects.

    This decoder uses pyModeS ``PipeDecoder`` to accumulate per-ICAO state
    and resolve CPR (Compact Position Reporting) even/odd frame pairs globally.
    No fixed reference position is required — positions are decoded by pairing
    alternating even (F=0) and odd (F=1) CPR frames from the same aircraft.

    Parameters:
        pair_window (10.0 s): maximum time between even and odd frames in a
            pair.  Frames outside this window are discarded.
        eviction_ttl (300.0 s): per-ICAO state is dropped after this many
            seconds of silence, preventing unbounded memory growth.

    Bootstrap / flush mechanism:
        PipeDecoder holds the first few position pairs in a bootstrap buffer to
        avoid false positives from noise.  By default an aircraft needs ~5
        position pairs (~10 frames, ~5 s at typical 2 Hz) before positions are
        released.  ``flush()`` is called automatically every
        ``FLUSH_INTERVAL_SEC`` seconds during ``decode()`` to release
        bootstrap-held positions for aircraft that have generated at least 2
        candidate pairs.  This means positions typically appear within ~5 s of
        the first pair for any aircraft.

    Limitations:
        - Surface position messages (typecodes 5-8) are not decoded because
          ``surface_ref`` is not passed to PipeDecoder.  Only airborne
          position messages (typecodes 9-18) are resolved.
    """

    def __init__(self) -> None:
        self._pipe: PipeDecoder = PipeDecoder(
            pair_window=10.0,
            eviction_ttl=300.0,
        )
        self._last_flush_ts: float = time.monotonic()
        self._pending_bootstrap: list[tuple[Decoded, str]] = []

    def decode(self, raw_hex: str, timestamp: float | None = None) -> AdsbMessage | None:
        """Decode a single ADS-B hex string.

        Args:
            raw_hex: 28-character hex string (14 bytes) from the demodulator.
            timestamp: Unix epoch timestamp for the frame.  Used by
                PipeDecoder for pair matching and stale-state eviction.
                Defaults to ``time.time()`` when not provided.

        Returns:
            ``AdsbMessage`` on success, or ``None`` if the frame is not a
            valid ADS-B extended squitter.
        """
        if not raw_hex or len(raw_hex) != 28:
            return None

        now = time.monotonic()
        if now - self._last_flush_ts >= FLUSH_INTERVAL_SEC:
            self._pipe.flush()
            self._last_flush_ts = now

        ts = timestamp if timestamp is not None else time.time()

        try:
            result = self._pipe.decode(raw_hex, timestamp=ts)
        except Exception:
            logger.debug("ADS-B PipeDecoder failed for %s", raw_hex, exc_info=True)
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

        icao = str(result.get("icao", ""))
        if not icao:
            return None

        msg = self._build_message(result, raw_hex)
        if msg is not None and msg.latitude is None and result.get("cpr_lat") is not None:
            self._pending_bootstrap.append((result, raw_hex))
        return msg

    def _build_message(self, result: Decoded, raw_hex: str) -> AdsbMessage | None:
        """Construct an ``AdsbMessage`` from a pyModeS ``Decoded`` result dict.

        Args:
            result: The result dict from ``PipeDecoder.decode()``.
            raw_hex: The original 28-character hex string.

        Returns:
            ``AdsbMessage`` on success, or ``None`` if the result dict has
            no valid ICAO address.
        """
        icao = str(result.get("icao", ""))
        if not icao:
            return None

        callsign = result.get("callsign")
        if callsign:
            callsign = callsign.strip()
            if callsign == "":
                callsign = None

        altitude_ft = result.get("altitude")
        if altitude_ft is not None:
            altitude_ft = int(altitude_ft)

        groundspeed = result.get("groundspeed")
        if groundspeed is not None:
            groundspeed = float(groundspeed)

        track = result.get("track")
        if track is None:
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
            latitude=result.get("latitude"),
            longitude=result.get("longitude"),
            groundspeed=groundspeed,
            track=track,
            vertical_rate=vertical_rate,
            raw_hex=raw_hex,
        )

    def flush(self) -> list[AdsbMessage]:
        """Release any bootstrap-held positions immediately.

        Calls the underlying ``PipeDecoder.flush()``, which retro-fills
        latitude/longitude on the ``Decoded`` result dicts that were held
        in the bootstrap buffer.  This method then collects those newly-
        resolved positions and returns them as ``AdsbMessage`` objects.

        After flush(), subsequent ``decode()`` calls for previously
        bootstrapping ICAOs will return positions immediately.

        Returns:
            A list of ``AdsbMessage`` objects whose positions were resolved
            by the flush.  Returns an empty list if no positions were held.
        """
        self._pipe.flush()
        self._last_flush_ts = time.monotonic()

        harvested: list[AdsbMessage] = []
        for result, raw_hex in self._pending_bootstrap:
            lat = result.get("latitude")
            lon = result.get("longitude")
            if lat is not None and lon is not None:
                msg = self._build_message(result, raw_hex)
                if msg is not None:
                    harvested.append(msg)
        self._pending_bootstrap.clear()
        return harvested
