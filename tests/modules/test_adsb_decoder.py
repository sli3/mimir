"""Tests for AdsbDecoder — pyModeS PipeDecoder integration and validation gates."""

from unittest.mock import MagicMock

from modules.adsb.decoder import AdsbDecoder
from modules.adsb.message import AdsbMessage

# Known-good DF17 ADS-B messages from pyModeS documentation/test fixtures.
IDENT_MSG = "8D406B902015A678D4D220AA4BDA"
VELOCITY_MSG = "8D485020994409940838175B284F"
POS_EVEN_MSG = "8D40058B58C901375147EFD09357"
POS_ODD_MSG = "8D40058B58C904A87F402D3B8C59"

# DF4 / DF5 Mode S surveillance replies (Phase 54). Real short squitters are
# 56-bit (14 hex), but the demodulator always emits 112-bit (28 hex) frames,
# so the fixtures are zero-padded to 28 hex, matching the demodulator output
# shape and the decoder's length gate. Verified against pyModeS 3.3.0
# PipeDecoder: DF4 decodes altitude 2850 ft, DF5 decodes squawk "7500".
DF4_MSG = "2006023AF07500" + "00" * 7   # DF4 altitude reply, 2850 ft
DF5_MSG = "28000AA2000000" + "00" * 7   # DF5 identity reply, squawk 7500


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


class TestAdsbDecoderDf4Df5:
    """DF4/DF5 Mode S surveillance replies admitted by the Phase 54 df filter."""

    def test_df4_frame_accepted(self):
        """A DF4 altitude reply with valid parity is accepted, not dropped."""
        decoder = AdsbDecoder()
        msg = decoder.decode(DF4_MSG)
        assert isinstance(msg, AdsbMessage)
        assert msg.altitude_ft == 2850

    def test_df5_frame_accepted_and_squawk_populated(self):
        """A DF5 identity reply is accepted and its squawk is populated."""
        decoder = AdsbDecoder()
        msg = decoder.decode(DF5_MSG)
        assert isinstance(msg, AdsbMessage)
        assert msg.squawk == "7500"

    def test_df5_squawk_is_four_char_string(self):
        """The squawk value is exactly a 4-character string."""
        decoder = AdsbDecoder()
        msg = decoder.decode(DF5_MSG)
        assert isinstance(msg.squawk, str)
        assert len(msg.squawk) == 4

    def test_df17_invalid_typecode_still_rejected(self):
        """Regression: typecode validation must still apply to DF17/18."""
        decoder = AdsbDecoder()
        # PipeDecoder.decode is a read-only C-level attribute, so swap the
        # whole pipe for a stub returning a DF17 result with an out-of-range
        # typecode.
        decoder._pipe = MagicMock()
        decoder._pipe.decode.return_value = {
            "df": 17, "crc_valid": True, "icao": "406B90", "typecode": 25,
        }
        assert decoder.decode(IDENT_MSG) is None

    def test_df17_valid_typecode_still_decodes(self):
        """Regression: a valid DF17 still decodes exactly as before."""
        decoder = AdsbDecoder()
        msg = decoder.decode(IDENT_MSG)
        assert isinstance(msg, AdsbMessage)
        assert msg.icao == "406B90"
        assert msg.callsign == "EZY85MH"

    def test_df11_still_rejected(self):
        """A downlink format outside (4, 5, 17, 18) is still rejected."""
        decoder = AdsbDecoder()
        # DF11 short all-call reply (56 bits, padded to 28 hex = 112 bits).
        df11 = "5D406B90E11A9F" + "00" * 7
        assert decoder.decode(df11) is None

    def test_df4_crc_fail_rejected(self):
        """A frame failing CRC is rejected regardless of downlink format."""
        decoder = AdsbDecoder()
        # pyModeS resolves an ICAO from the address parity on short frames,
        # so a real DF4/DF5 always reports crc_valid=True. Drive the gate
        # directly: any result with crc_valid False must be rejected.
        decoder._pipe = MagicMock()
        decoder._pipe.decode.return_value = {
            "df": 4, "crc_valid": False, "icao": "6BC876", "altitude": 2850,
        }
        assert decoder.decode(DF4_MSG) is None

    def test_df4_df5_fields_unset(self):
        """Fields DF4/DF5 do not carry are None on the decoded message."""
        decoder = AdsbDecoder()
        for raw in (DF4_MSG, DF5_MSG):
            msg = decoder.decode(raw)
            assert isinstance(msg, AdsbMessage)
            assert msg.callsign is None
            assert msg.latitude is None
            assert msg.longitude is None
            assert msg.groundspeed is None
            assert msg.track is None

    def test_df4_df5_not_appended_to_bootstrap(self):
        """DF4/DF5 carry no CPR data, so they never enter the bootstrap buffer."""
        decoder = AdsbDecoder()
        assert decoder.decode(DF4_MSG) is not None
        assert decoder.decode(DF5_MSG) is not None
        assert decoder._pending_bootstrap == []
