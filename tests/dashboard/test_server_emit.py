"""
tests/dashboard/test_server_emit.py — SocketIO emit payload tests

Tests that decoder-driven emit functions include the raw decode fields
required by the dashboard RAW DECODE views.

Run with:
    uv run pytest tests/dashboard/test_server_emit.py -v
"""

import sys
import os
from datetime import datetime
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from dashboard.server import emit_acars_message, emit_ais_message
from modules.acars.message import AcarsMessage
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
