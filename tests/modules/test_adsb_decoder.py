"""Tests for AdsbDecoder — pyModeS PipeDecoder integration and validation gates."""

from modules.adsb.decoder import AdsbDecoder
from modules.adsb.message import AdsbMessage

# Known-good DF17 ADS-B messages from pyModeS documentation/test fixtures.
IDENT_MSG = "8D406B902015A678D4D220AA4BDA"
VELOCITY_MSG = "8D485020994409940838175B284F"
POS_EVEN_MSG = "8D40058B58C901375147EFD09357"
POS_ODD_MSG = "8D40058B58C904A87F402D3B8C59"


class TestAdsbDecoder:
    def test_decode_identification_message(self):
        """IDENT_MSG decodes to the expected ICAO address and callsign."""
        decoder = AdsbDecoder()
        msg = decoder.decode(IDENT_MSG)
        assert isinstance(msg, AdsbMessage)
        assert msg.icao == "406B90"
        assert msg.callsign == "EZY85MH"

    def test_decode_velocity_message(self):
        """VELOCITY_MSG decodes to the expected groundspeed."""
        decoder = AdsbDecoder()
        msg = decoder.decode(VELOCITY_MSG)
        assert isinstance(msg, AdsbMessage)
        assert msg.groundspeed == 159

    def test_single_position_frame_yields_no_position(self):
        """A single CPR frame gives no position before a pair is formed."""
        decoder = AdsbDecoder()
        msg = decoder.decode(POS_EVEN_MSG, timestamp=1000.0)
        # May be None (if ICAO has no non-position fields) or an
        # AdsbMessage with latitude=None. Either is acceptable.
        if msg is not None:
            assert msg.latitude is None
            assert msg.longitude is None

    def test_position_after_pair_and_flush(self):
        """Even+odd pair followed by flush() yields a valid global position."""
        decoder = AdsbDecoder()
        t = 1000.0
        decoder.decode(POS_EVEN_MSG, timestamp=t)
        decoder.decode(POS_ODD_MSG, timestamp=t + 0.5)
        decoder.flush()
        # Second pair — ICAO is now locked, position should resolve
        msg_even = decoder.decode(POS_EVEN_MSG, timestamp=t + 2.0)
        msg_odd = decoder.decode(POS_ODD_MSG, timestamp=t + 2.5)
        positioned = next(
            (m for m in (msg_even, msg_odd) if m is not None and m.latitude is not None),
            None,
        )
        assert positioned is not None, (
            "Expected a position after pair+flush, but neither frame resolved one"
        )
        assert -90.0 <= positioned.latitude <= 90.0
        assert -180.0 <= positioned.longitude <= 180.0

    def test_non_position_fields_unaffected_by_accumulator(self):
        """Callsign, altitude, and groundspeed decode without needing a pair."""
        decoder = AdsbDecoder()
        ident_msg = decoder.decode(IDENT_MSG, timestamp=2000.0)
        assert isinstance(ident_msg, AdsbMessage)
        assert ident_msg.callsign == "EZY85MH"
        vel_msg = decoder.decode(VELOCITY_MSG, timestamp=2001.0)
        assert isinstance(vel_msg, AdsbMessage)
        assert vel_msg.groundspeed == 159

    def test_invalid_crc_returns_none(self):
        """Corrupting the last byte of a valid message causes rejection."""
        decoder = AdsbDecoder()
        corrupted = IDENT_MSG[:-2] + "00"
        assert decoder.decode(corrupted) is None

    def test_non_adsb_downlink_format_returns_none(self):
        """A DF11 all-call reply is rejected."""
        decoder = AdsbDecoder()
        # DF11 short all-call reply (56 bits, but padded to 28 hex = 112 bits)
        df11 = "5D406B90E11A9F" + "00" * 7
        assert decoder.decode(df11) is None

    def test_empty_hex_returns_none(self):
        """Empty string is rejected without exception."""
        decoder = AdsbDecoder()
        assert decoder.decode("") is None

    def test_callsign_whitespace_stripped(self):
        """Trailing spaces in pyModeS callsign output are stripped."""
        decoder = AdsbDecoder()
        msg = decoder.decode(IDENT_MSG)
        assert msg is not None
        assert msg.callsign == "EZY85MH"
        assert not msg.callsign.endswith(" ")
