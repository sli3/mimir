"""
tests/dashboard/test_server_emit.py — SocketIO emit payload tests

Tests that decoder-driven emit functions include the raw decode fields
required by the dashboard RAW DECODE views, and that spectrum updates
preserve their payload contract while rounding values and limiting the rate.

Run with:
    uv run pytest tests/dashboard/test_server_emit.py -v
"""

import sys
import os
from collections.abc import Callable
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import dashboard.server as server
from dashboard.server import (
    AdsbFieldTracker,
    emit_acars_message,
    emit_adsb_aircraft,
    emit_adsb_scan_result,
    emit_ais_message,
    start_server,
)
from modules.acars.message import AcarsMessage
from modules.adsb.message import AdsbMessage
from modules.ais.message import AisMessage
from core.pipeline.scan_result import ScanResult


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


class TestBroadcastSpectrum:
    """Spectrum payload rounding and per-server rate limiting."""

    def _start_server_with_mocks(self) -> Callable:
        """Obtain the spectrum callback without starting threads or binding ports."""
        with (
            patch("dashboard.server.socketio.run"),
            patch("threading.Thread.start"),
        ):
            start_server("localhost", 5000)
        return start_server._broadcast_spectrum_fn

    def test_payload_rounding_and_python_float_values(self) -> None:
        """Lists and numpy arrays yield rounded Python floats with the same keys."""
        broadcast = self._start_server_with_mocks()
        with (
            patch("dashboard.server.socketio.emit") as mock_emit,
            patch("dashboard.server.time.monotonic", side_effect=[0.0, 0.1]),
        ):
            for values in (
                [-80.123, -42.987, -30],
                np.array([-80.123, -42.987, -30], dtype=np.float32),
            ):
                broadcast(values, 1_090_000_000, 1_089_000_000, 1_091_000_000)

        assert mock_emit.call_count == 2
        for emit_call in mock_emit.call_args_list:
            event_name, payload = emit_call.args
            assert event_name == "spectrum_update"
            assert payload == {
                "psd_db": [-80.1, -43.0, -30.0],
                "center_freq_hz": 1_090_000_000,
                "freq_min_hz": 1_089_000_000,
                "freq_max_hz": 1_091_000_000,
            }
            assert type(payload["psd_db"]) is list
            assert all(type(value) is float for value in payload["psd_db"])

    def test_rate_cap_measures_from_last_emit(self) -> None:
        """Drop early calls across frequencies without moving the emit deadline."""
        broadcast = self._start_server_with_mocks()
        interval = 1 / server.SPECTRUM_MAX_RATE_HZ
        t0 = 0.0
        with (
            patch("dashboard.server.socketio.emit") as mock_emit,
            patch(
                "dashboard.server.time.monotonic",
                side_effect=[
                    t0, t0 + interval / 2, t0 + interval * 0.999, t0 + interval,
                ],
            ),
        ):
            broadcast([-80.0], 1_090_000_000, 1_089_000_000, 1_091_000_000)
            broadcast([-70.0], 98_000_000, 97_000_000, 99_000_000)
            assert mock_emit.call_count == 1
            broadcast([-65.0], 98_000_000, 97_000_000, 99_000_000)
            assert mock_emit.call_count == 1
            broadcast([-60.0], 98_000_000, 97_000_000, 99_000_000)

        assert mock_emit.call_count == 2
        assert [call.args[1]["psd_db"] for call in mock_emit.call_args_list] == [
            [-80.0], [-60.0],
        ]

    def test_successive_boundaries_from_nonzero_time_emit(self) -> None:
        """Accept successive deadlines built from the configured rate interval."""
        broadcast = self._start_server_with_mocks()
        interval = 1 / server.SPECTRUM_MAX_RATE_HZ
        t0 = 0.3
        t1 = t0 + interval
        t2 = t1 + interval
        with (
            patch("dashboard.server.socketio.emit") as mock_emit,
            patch("dashboard.server.time.monotonic", side_effect=[t0, t1, t2]),
        ):
            for value in (-80.0, -70.0, -60.0):
                broadcast([value], 1_090_000_000, 1_089_000_000, 1_091_000_000)

        assert mock_emit.call_count == 3
        assert [call.args[1]["psd_db"] for call in mock_emit.call_args_list] == [
            [-80.0], [-70.0], [-60.0],
        ]

    def test_separate_server_calls_have_independent_throttles(self) -> None:
        """Each start_server call permits its first update at the same time."""
        first_broadcast = self._start_server_with_mocks()
        with (
            patch("dashboard.server.socketio.emit") as mock_emit,
            patch("dashboard.server.time.monotonic", return_value=0.0),
        ):
            first_broadcast([-80.0], 1_090_000_000, 1_089_000_000, 1_091_000_000)
            second_broadcast = self._start_server_with_mocks()
            second_broadcast([-70.0], 1_090_000_000, 1_089_000_000, 1_091_000_000)
            first_broadcast([-60.0], 1_090_000_000, 1_089_000_000, 1_091_000_000)

        assert mock_emit.call_count == 2
        assert [call.args[1]["psd_db"] for call in mock_emit.call_args_list] == [
            [-80.0], [-70.0],
        ]


class TestBroadcastFocusFilter:
    """broadcast() must use tolerance-based focus matching, not strict equality.

    Mirrors the frontend Phase 76 Fix 4 (dashboard/frontend/src/utils/frequency.js).
    Without this fix, demo-mode scan results from a real captured file
    (e.g. 1_090_030_000 Hz from capture_1090030000hz_*.sigmf-meta) are silently
    dropped because the focus is set to a rounded canonical band value
    (1_090_000_000 Hz) by the ADS-B button — strict equality fails every time.
    """

    def _start_server_with_mocks(self):
        """Obtain broadcast() by calling start_server() with mocked threading/socketio.run.

        Mirrors the established pattern in tests/dashboard/test_server_stats.py:128-135.
        Patches threading.Thread.start (so no Flask/stats threads actually run) and
        dashboard.server.socketio.run (so no port binding occurs).
        """
        mock_device = MagicMock()
        with (
            patch("dashboard.server.socketio.run"),
            patch("threading.Thread.start"),
        ):
            broadcast = start_server("localhost", 5000, mock_device)
        return broadcast

    def _make_scan_result(self, freq_hz: float) -> ScanResult:
        """Construct a minimal ScanResult carrying only center_freq_hz.

        broadcast() only inspects scan_result.center_freq_hz (for the
        focus filter) and scan_result.classification / .fingerprint /
        .timestamp (for the payload). The classification object is a
        MagicMock because we never assert on its field contents — only
        that the emit was attempted or not.
        """
        return ScanResult(
            center_freq_hz=freq_hz,
            timestamp="2026-08-20T15:33:07",
            fingerprint={},
            classification=MagicMock(
                signal_type="adsb",
                confidence="high",
                confidence_score=0.95,
                novel=False,
                au_legal_status="legal_rx",
                reasoning="test",
            ),
        )

    def test_offset_frequency_within_tolerance_emits(self):
        """The real bug scenario: focus on 1_090_000_000, scan at 1_090_030_000 (30 kHz off) MUST emit.

        Pre-fix behaviour: strict equality 1_090_030_000 != 1_090_000_000
        returns True, broadcast() exits early, scan_result is dropped.
        Post-fix behaviour: freq_matches within 100 kHz tolerance, emit proceeds.
        """
        broadcast = self._start_server_with_mocks()
        with (
            patch("dashboard.server._focused_freq_hz", 1_090_000_000),
            patch("dashboard.server.socketio.emit") as mock_emit,
        ):
            broadcast(self._make_scan_result(1_090_030_000))
        scan_result_calls = [
            call for call in mock_emit.call_args_list if call[0][0] == "scan_result"
        ]
        assert len(scan_result_calls) == 1, (
            "Real bug: 30 kHz offset must emit under tolerance-based filter"
        )

    def test_genuinely_different_band_does_not_emit(self):
        """Regression guard: focus on ADS-B (1090 MHz), scan at FM (98 MHz, 992 MHz gap) MUST NOT emit.

        Proves the filter still filters correctly with the new tolerance,
        just with the right granularity. The 992 MHz gap is 9920x the
        tolerance — no chance of a false match.
        """
        broadcast = self._start_server_with_mocks()
        with (
            patch("dashboard.server._focused_freq_hz", 1_090_000_000),
            patch("dashboard.server.socketio.emit") as mock_emit,
        ):
            broadcast(self._make_scan_result(98_000_000))
        scan_result_calls = [
            call for call in mock_emit.call_args_list if call[0][0] == "scan_result"
        ]
        assert len(scan_result_calls) == 0, (
            "Regression guard: 992 MHz off-band scan must be filtered"
        )

    def test_focused_none_passes_any_frequency(self):
        """focused=None still means 'no filter' — an off-band scan must emit.

        Mirrors the existing test_passes_all_when_focus_is_none in
        test_server_stats.py:272 but uses off-band frequency (98 MHz vs
        1090 MHz) to prove the None path is not accidentally blocked.
        """
        broadcast = self._start_server_with_mocks()
        with (
            patch("dashboard.server._focused_freq_hz", None),
            patch("dashboard.server.socketio.emit") as mock_emit,
        ):
            broadcast(self._make_scan_result(98_000_000))
        scan_result_calls = [
            call for call in mock_emit.call_args_list if call[0][0] == "scan_result"
        ]
        assert len(scan_result_calls) == 1
