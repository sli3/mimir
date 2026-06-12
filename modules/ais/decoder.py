"""AIS decoder — NMEA sentence decoding using pyais.

Reconstructs a valid AIVDM NMEA sentence from a raw HDLC payload so that
pyais can decode the structured AIS fields.  Also accepts pre-formed NMEA
sentences for testing.

Legal: passive receive only.  Radiocommunications Act 1992 (Cth).
Jurisdiction: AU / SA.  Authority: ACMA.

TX-Safety Note:
    pyais imports its encode module at package level (__init__.py). This module
    is loaded into memory when any pyais import occurs. It is NEVER called by
    Mimir. It produces NMEA text strings only and has no interaction with radio
    hardware. Mimir imports only pyais.decode and pyais.IterMessages.
"""

import logging
from datetime import datetime

from modules.ais.message import AisMessage

logger = logging.getLogger(__name__)


def _armor_6bit(value: int) -> str:
    """Convert a 6-bit value to its AIS ASCII armored character."""
    if value < 40:
        return chr(value + 48)
    else:
        return chr(value + 56)


def _bytes_to_armored(payload: bytes) -> str:
    """Convert raw AIS payload bytes to 6-bit ASCII armored string.

    ITU-R M.1371 6-bit armoring: each 6-bit nibble maps to an ASCII character.
    """
    bits: list[int] = []
    for byte in payload:
        for i in range(7, -1, -1):  # MSB first
            bits.append((byte >> i) & 1)

    # Pad to multiple of 6
    while len(bits) % 6 != 0:
        bits.append(0)

    armored = ""
    for i in range(0, len(bits), 6):
        value = 0
        for j in range(6):
            value |= bits[i + j] << (5 - j)
        armored += _armor_6bit(value)

    return armored


def _compute_nmea_checksum(sentence: str) -> int:
    """Compute NMEA checksum — XOR of all bytes between '!' and '*'."""
    payload = sentence[1 : sentence.rindex("*")]
    checksum = 0
    for ch in payload:
        checksum ^= ord(ch)
    return checksum


def _decode_nmea_sentence(nmea_str: str, channel: str) -> AisMessage | None:
    """Parse a valid NMEA sentence string with pyais and return an AisMessage."""
    try:
        # pyais: safe receive-only import. encode module is loaded at package
        # level but never called by Mimir. See TX-Safety Note above.
        from pyais import decode
        from pyais.exceptions import UnknownMessageException

        decoded = decode(nmea_str.encode())
    except UnknownMessageException:
        logger.debug("AIS NMEA unknown message: %s", nmea_str)
        return None
    except Exception:
        logger.debug("AIS NMEA decode failed: %s", nmea_str, exc_info=True)
        return None

    try:
        msg_type = int(decoded.msg_type) if hasattr(decoded, "msg_type") else 0
    except Exception:
        msg_type = 0

    return AisMessage(
        mmsi=str(getattr(decoded, "mmsi", "")),
        lat=getattr(decoded, "lat", None),
        lon=getattr(decoded, "lon", None),
        speed=getattr(decoded, "speed", None),
        course=getattr(decoded, "course", None),
        vessel_name=getattr(decoded, "shipname", None),
        msg_type=msg_type,
        channel=channel,
        freq_hz=0.0,
        timestamp=datetime.now(),
        raw_nmea=nmea_str,
    )


class AisDecoder:
    """Decode AIS HDLC payloads or NMEA sentences into structured AisMessage objects."""

    def decode(self, hdlc_payload, channel: str) -> AisMessage | None:
        """Decode a raw HDLC payload or NMEA sentence into an AisMessage.

        If the input is a string or bytes starting with ``!AIVDM`` or ``!AIVDO``,
        it is parsed directly as a NMEA sentence.  Otherwise, it is treated as a
        raw HDLC payload and a NMEA sentence is reconstructed before parsing.
        For multi-fragment NMEA sentences, pass a list of fragment strings/bytes.

        Args:
            hdlc_payload: Raw payload bytes extracted from an HDLC frame, a
                          complete NMEA sentence string/bytes, or a list of
                          NMEA sentence fragments for multi-part messages.
            channel: AIS channel identifier ("A" or "B").

        Returns:
            AisMessage on success, or None if decoding fails.
        """
        # Handle list of fragments (multi-part NMEA message)
        if isinstance(hdlc_payload, list):
            try:
                from pyais import decode
                from pyais.exceptions import UnknownMessageException

                parts = [
                    p.encode() if isinstance(p, str) else p for p in hdlc_payload
                ]
                decoded = decode(*parts)
            except UnknownMessageException:
                return None
            except Exception:
                return None

            try:
                msg_type = int(decoded.msg_type) if hasattr(decoded, "msg_type") else 0
            except Exception:
                msg_type = 0

            return AisMessage(
                mmsi=str(getattr(decoded, "mmsi", "")),
                lat=getattr(decoded, "lat", None),
                lon=getattr(decoded, "lon", None),
                speed=getattr(decoded, "speed", None),
                course=getattr(decoded, "course", None),
                vessel_name=getattr(decoded, "shipname", None),
                msg_type=msg_type,
                channel=channel,
                freq_hz=0.0,
                timestamp=datetime.now(),
                raw_nmea=", ".join(
                    p.decode() if isinstance(p, bytes) else p for p in hdlc_payload
                ),
            )

        # If input is a string or looks like a NMEA sentence, parse directly
        if isinstance(hdlc_payload, str):
            if hdlc_payload.startswith("!AIVDM") or hdlc_payload.startswith("!AIVDO"):
                return _decode_nmea_sentence(hdlc_payload, channel)
            return None

        if isinstance(hdlc_payload, bytes):
            try:
                text = hdlc_payload.decode("ascii", errors="ignore")
            except Exception:
                text = ""
            if text.startswith("!AIVDM") or text.startswith("!AIVDO"):
                return _decode_nmea_sentence(text, channel)
            # If it doesn't look like a NMEA sentence and doesn't have HDLC header,
            # it's not a valid AIS payload
            if len(hdlc_payload) < 3 or hdlc_payload[:3] != bytes([0xFF, 0x03, 0xF0]):
                return None

        # Otherwise treat as raw HDLC payload bytes
        if not isinstance(hdlc_payload, bytes) or len(hdlc_payload) < 4:
            return None

        # Standard AIS HDLC frames use address 0xFF, control 0x03, PID 0xF0
        ais_payload = hdlc_payload[3:]

        if len(ais_payload) == 0:
            return None

        armored = _bytes_to_armored(ais_payload)
        payload_bits = len(ais_payload) * 8
        fill_bits = (6 - (payload_bits % 6)) % 6

        # Build NMEA sentence (without checksum)
        sentence_body = f"!AIVDM,1,1,,{channel},{armored},{fill_bits}"
        checksum = _compute_nmea_checksum(sentence_body + "*00")
        nmea = f"{sentence_body}*{checksum:02X}"

        return _decode_nmea_sentence(nmea, channel)
