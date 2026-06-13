"""Tests for AdsbMessage dataclass and field validation."""

from datetime import datetime

from modules.adsb.message import AdsbMessage


class TestAdsbMessage:
    def test_default_timestamp_is_set(self):
        """AdsbMessage with all fields populated has a datetime timestamp."""
        msg = AdsbMessage(
            icao="7C4B4C",
            callsign="QFA456",
            altitude_ft=32_500,
            latitude=-34.93,
            longitude=138.60,
            groundspeed=450.0,
            track=90.0,
            vertical_rate=1500,
            raw_hex="8D7C4B4C00000000000000000000",
        )
        assert isinstance(msg.timestamp, datetime)

    def test_optional_fields_accept_none(self):
        """Optional fields can all be None without raising."""
        msg = AdsbMessage(
            icao="7C4B4C",
            callsign=None,
            altitude_ft=None,
            latitude=None,
            longitude=None,
            groundspeed=None,
            track=None,
            vertical_rate=None,
            raw_hex="8D7C4B4C00000000000000000000",
        )
        assert msg.callsign is None
        assert msg.altitude_ft is None
        assert msg.latitude is None
        assert msg.longitude is None
        assert msg.groundspeed is None
        assert msg.track is None
        assert msg.vertical_rate is None

    def test_icao_stored_as_string(self):
        """icao field is a str."""
        msg = AdsbMessage(
            icao="406B90",
            callsign=None,
            altitude_ft=None,
            latitude=None,
            longitude=None,
            groundspeed=None,
            track=None,
            vertical_rate=None,
            raw_hex="8D406B902015A678D4D220AA4BDA",
        )
        assert isinstance(msg.icao, str)
        assert msg.icao == "406B90"
