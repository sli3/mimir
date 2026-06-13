"""Tests for AdsbDecoder — pyModeS integration and validation gates."""

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

    def test_decode_position_message_with_ref(self):
        """POS_EVEN_MSG decoded with Adelaide reference yields valid lat/lon."""
        decoder = AdsbDecoder()
        msg = decoder.decode(POS_EVEN_MSG)
        assert isinstance(msg, AdsbMessage)
        assert isinstance(msg.latitude, float)
        assert isinstance(msg.longitude, float)
        # European aircraft with Adelaide ref will produce a mathematically
        # valid but geographically shifted position; just check hemisphere-ish.
        assert -90 <= msg.latitude <= 0
        assert 0 <= msg.longitude <= 180

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
