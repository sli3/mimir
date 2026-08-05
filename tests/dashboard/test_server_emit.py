"""
tests/dashboard/test_server_emit.py — SocketIO emit payload tests

Tests that decoder-driven emit functions include the raw decode fields
required by the dashboard RAW DECODE views.

Run with:
    uv run pytest tests/dashboard/test_server_emit.py -v
"""

import sys
import os
from datetime import datetime, timezone
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import dashboard.server as server
from dashboard.server import (
    AdsbFieldTracker,
    emit_acars_message,
    emit_adsb_aircraft,
    emit_adsb_scan_result,
    emit_ais_message,
)
from modules.acars.message import AcarsMessage
from modules.adsb.message import AdsbMessage
from modules.ais.message import AisMessage


class TestEmitAcarsMessage:
    def test_emit_acars_message_includes_raw(self):
        """emit_acars_message() must include the decoded text under key 'raw'."""
        msg = AcarsMessage(
            timestamp=datetime(2026, 6, 25, 12, 0, 0),
            freq_hz=129_125_000,
            mode="2",
            registration="VH-OGE",
            label="H1",
            block_id="A",
            text="TEST MESSAGE",
            crc_ok=True,
        )
        with patch("dashboard.server.socketio.emit") as mock_emit:
            emit_acars_message(msg)

        mock_emit.assert_called_once()
        event_name, payload = mock_emit.call_args[0]
        assert event_name == "acars_message"
        assert payload["raw"] == "TEST MESSAGE"
        assert payload["text"] == "TEST MESSAGE"
        assert payload["registration"] == "VH-OGE"


class TestEmitAisMessage:
    def test_emit_ais_message_includes_raw(self):
        """emit_ais_message() must include the raw NMEA sentence under key 'raw'."""
        raw_nmea = "!AIVDM,1,1,,A,15Mj23P000G?q7fK>g,0*1B"
        msg = AisMessage(
            mmsi="503000001",
            lat=-34.9285,
            lon=138.6007,
            speed=12.5,
            course=45.0,
            vessel_name="TEST VESSEL",
            msg_type=1,
            channel="A",
            timestamp=datetime(2026, 6, 25, 12, 0, 0),
            raw_nmea=raw_nmea,
            freq_hz=162_000_000,
        )
        with patch("dashboard.server.socketio.emit") as mock_emit:
            emit_ais_message(msg)

        mock_emit.assert_called_once()
        event_name, payload = mock_emit.call_args[0]
        assert event_name == "ais_message"
        assert payload["raw"] == raw_nmea
        assert payload["mmsi"] == "503000001"


def make_adsb_msg(**overrides):
    """Build an AdsbMessage with all optional fields None unless overridden."""
    fields = dict(
        icao="7C4B4C",
        callsign=None,
        altitude_ft=None,
        latitude=None,
        longitude=None,
        groundspeed=None,
        track=None,
        vertical_rate=None,
        raw_hex="8D7C4B4C00000000000000000000",
        timestamp=datetime(2026, 8, 5, 12, 0, 0, tzinfo=timezone.utc),
    )
    fields.update(overrides)
    return AdsbMessage(**fields)


class TestEmitAdsbMessage:
    """Squawk key on the adsb_aircraft payload and scan_result reasoning."""

    def test_emit_adsb_aircraft_payload_contains_squawk(self):
        """emit_adsb_aircraft() payload carries the message's squawk value."""
        msg = make_adsb_msg(squawk="7500")
        with patch("dashboard.server.socketio.emit") as mock_emit:
            emit_adsb_aircraft(msg)

        mock_emit.assert_called_once()
        event_name, payload = mock_emit.call_args[0]
        assert event_name == "adsb_aircraft"
        assert payload["squawk"] == "7500"

    def test_emit_adsb_scan_result_reasoning_contains_squawk_when_known(self):
        """Reasoning string includes the squawk once it has been resolved."""
        msg = make_adsb_msg(icao="A1B2C3", squawk="7500", altitude_ft=35000)
        with (
            patch.object(server, "_focused_freq_hz", None),
            patch.object(server, "_field_tracker", AdsbFieldTracker()),
            patch("dashboard.server.socketio.emit") as mock_emit,
        ):
            emit_adsb_scan_result(msg)

        mock_emit.assert_called_once()
        event_name, payload = mock_emit.call_args[0]
        assert event_name == "scan_result"
        assert "squawk 7500" in payload["reasoning"]

    def test_emit_adsb_scan_result_reasoning_says_unknown_when_never_resolved(self):
        """Reasoning string says 'unknown' for squawk when never resolved."""
        msg = make_adsb_msg(icao="D4E5F6", callsign="QFA456")
        with (
            patch.object(server, "_focused_freq_hz", None),
            patch.object(server, "_field_tracker", AdsbFieldTracker()),
            patch("dashboard.server.socketio.emit") as mock_emit,
        ):
            emit_adsb_scan_result(msg)

        mock_emit.assert_called_once()
        event_name, payload = mock_emit.call_args[0]
        assert event_name == "scan_result"
        assert "squawk unknown" in payload["reasoning"]
