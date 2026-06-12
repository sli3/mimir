"""Tests for AisMessage dataclass and field validation."""

from datetime import datetime

from modules.ais.message import AisMessage


def test_ais_message_dataclass_fields():
    """All fields are stored correctly."""
    ts = datetime(2024, 1, 1, 12, 0, 0)
    msg = AisMessage(
        mmsi="366053209",
        lat=-33.8568,
        lon=151.2153,
        speed=12.5,
        course=45.0,
        vessel_name="TEST SHIP",
        msg_type=1,
        channel="A",
        timestamp=ts,
        raw_nmea="!AIVDM,1,1,,A,15Mj23P000G?q7fK>g:o7@1:0L3S,0*1B",
        freq_hz=162_000_000.0,
    )
    assert msg.mmsi == "366053209"
    assert msg.lat == -33.8568
    assert msg.lon == 151.2153
    assert msg.speed == 12.5
    assert msg.course == 45.0
    assert msg.vessel_name == "TEST SHIP"
    assert msg.msg_type == 1
    assert msg.channel == "A"
    assert msg.freq_hz == 162_000_000.0
    assert msg.timestamp == ts
    assert msg.raw_nmea == "!AIVDM,1,1,,A,15Mj23P000G?q7fK>g:o7@1:0L3S,0*1B"


def test_ais_message_optional_fields_none():
    """All optional fields accept None."""
    ts = datetime(2024, 1, 1, 12, 0, 0)
    msg = AisMessage(
        mmsi="503000001",
        lat=None,
        lon=None,
        speed=None,
        course=None,
        vessel_name=None,
        msg_type=1,
        channel="B",
        timestamp=ts,
        raw_nmea="!AIVDM,1,1,,B,15Mj23P000G?q7fK>g:o7@1:0L3S,0*1B",
        freq_hz=162_000_000.0,
    )
    assert msg.lat is None
    assert msg.lon is None
    assert msg.speed is None
    assert msg.course is None
    assert msg.vessel_name is None


def test_ais_message_channel_a():
    """Channel field accepts 'A'."""
    msg = AisMessage(
        mmsi="123",
        lat=None,
        lon=None,
        speed=None,
        course=None,
        vessel_name=None,
        msg_type=1,
        channel="A",
        timestamp=datetime(2024, 1, 1, 12, 0, 0),
        raw_nmea="",
        freq_hz=0.0,
    )
    assert msg.channel == "A"


def test_ais_message_channel_b():
    """Channel field accepts 'B'."""
    msg = AisMessage(
        mmsi="123",
        lat=None,
        lon=None,
        speed=None,
        course=None,
        vessel_name=None,
        msg_type=1,
        channel="B",
        timestamp=datetime(2024, 1, 1, 12, 0, 0),
        raw_nmea="",
        freq_hz=0.0,
    )
    assert msg.channel == "B"
