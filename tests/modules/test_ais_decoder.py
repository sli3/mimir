"""Tests for AisDecoder — NMEA sentence decoding."""

import pytest

from modules.ais.decoder import AisDecoder
from modules.ais.message import AisMessage

# Real known-good AIS NMEA sentences (verified with pyais)
TYPE1_SENTENCE = b"!AIVDM,1,1,,B,15NG6V0P01G?cFhE`R2IU?wn28R>,0*05"
TYPE5_PART1 = b"!AIVDM,2,1,4,A,55O0W7`00001L@gCWGA2uItLth@DqtL5@F22220j1h742t0Ht0000000,0*08"
TYPE5_PART2 = b"!AIVDM,2,2,4,A,000000000000000,2*20"


class TestAisDecoder:
    def setup_method(self):
        self.decoder = AisDecoder()

    def test_decode_type1_message(self):
        """decode() with a valid Type 1 NMEA sentence returns an AisMessage."""
        msg = self.decoder.decode(TYPE1_SENTENCE, "B")
        assert isinstance(msg, AisMessage)
        assert msg.mmsi == "367380120"
        assert msg.msg_type == 1
        assert msg.channel == "B"
        assert msg.lat is not None
        assert msg.lon is not None
        assert msg.speed is not None
        assert msg.course is not None

    def test_decode_malformed_payload_returns_none(self):
        """decode() with a malformed payload returns None (no exception)."""
        msg = self.decoder.decode(b"not a valid sentence", "A")
        assert msg is None

    def test_decode_type1_populates_fields(self):
        """Type 1 message populates mmsi, lat, lon, speed, course."""
        msg = self.decoder.decode(TYPE1_SENTENCE, "B")
        assert msg is not None
        assert msg.mmsi == "367380120"
        assert msg.lat == pytest.approx(37.8069, abs=0.01)
        assert msg.lon == pytest.approx(-122.4043, abs=0.01)
        assert msg.speed == pytest.approx(0.1, abs=0.1)
        assert msg.course == pytest.approx(245.2, abs=0.1)

    def test_decode_type5_populates_vessel_name(self):
        """Type 5 message populates vessel_name."""
        msg = self.decoder.decode([TYPE5_PART1, TYPE5_PART2], "A")
        assert msg is not None
        assert msg.msg_type == 5
        assert msg.vessel_name is not None

    def test_decode_type5_multi_fragment(self):
        """Type 5 multi-fragment message is decoded."""
        msg = self.decoder.decode([TYPE5_PART1, TYPE5_PART2], "A")
        assert msg is not None
        assert msg.mmsi is not None

    def test_decode_invalid_bytes(self):
        """decode() with random bytes returns None."""
        msg = self.decoder.decode(b"\x00\x01\x02\x03", "A")
        assert msg is None
