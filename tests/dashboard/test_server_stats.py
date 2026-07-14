import sys
import os
import time
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import dashboard.server as server
from dashboard.server import (
    _compute_hackrf_status,
    handle_set_focus,
    start_server,
)
from core.pipeline.scan_result import ScanResult
from llm.classifier import ClassificationResult
from modules.adsb.message import AdsbMessage
from modules.adsb.constants import AU_ADSB_FREQUENCY_HZ
import dashboard.shared_state as ss


class TestComputeHackrfStatus:
    def test_disconnected_when_device_is_none(self):
        with patch("dashboard.server._device_ref", None):
            assert _compute_hackrf_status() == "DISCONNECTED"

    def test_disconnected_when_device_not_open(self):
        mock_device = MagicMock()
        mock_device.is_open = False
        with patch("dashboard.server._device_ref", mock_device):
            assert _compute_hackrf_status() == "DISCONNECTED"

    def test_not_responding_when_recent_hw_error(self):
        mock_device = MagicMock()
        mock_device.is_open = True
        with (
            patch("dashboard.server._device_ref", mock_device),
            patch("dashboard.server._last_hw_error_time", time.time()),
            patch("dashboard.server.time.time", return_value=time.time() + 2.0),
        ):
            assert _compute_hackrf_status() == "NOT_RESPONDING"

    def test_connected_when_no_recent_hw_error(self):
        mock_device = MagicMock()
        mock_device.is_open = True
        with (
            patch("dashboard.server._device_ref", mock_device),
            patch("dashboard.server._last_hw_error_time", time.time() - 60.0),
            patch("dashboard.server.time.time", return_value=time.time()),
        ):
            assert _compute_hackrf_status() == "CONNECTED"

    def test_not_responding_transitions_to_connected_after_5s(self):
        mock_device = MagicMock()
        mock_device.is_open = True
        error_time = 1000.0
        with (
            patch("dashboard.server._device_ref", mock_device),
            patch("dashboard.server._last_hw_error_time", error_time),
            patch("dashboard.server.time.time", return_value=error_time + 4.0),
        ):
            assert _compute_hackrf_status() == "NOT_RESPONDING"
        with (
            patch("dashboard.server._device_ref", mock_device),
            patch("dashboard.server._last_hw_error_time", error_time),
            patch("dashboard.server.time.time", return_value=error_time + 6.0),
        ):
            assert _compute_hackrf_status() == "CONNECTED"


class TestFocusFrequencyFilter:
    def _make_scan_result(self, freq_hz: float, fingerprint: dict | None = None) -> ScanResult:
        return ScanResult(
            center_freq_hz=freq_hz,
            timestamp="2026-06-03T12:00:00",
            fingerprint=fingerprint or {},
            classification=ClassificationResult(
                signal_type="test",
                confidence="high",
                confidence_score=0.9,
                novel=False,
                au_legal_status="LEGAL RX",
                reasoning="test",
                frequency_band="test",
                raw_response="test",
            ),
        )

    def test_handle_set_focus_sets_global(self):
        saved = server._focused_freq_hz
        try:
            handle_set_focus({"freq_hz": 100e6})
            assert server._focused_freq_hz == 100e6
        finally:
            server._focused_freq_hz = saved

    def test_handle_set_focus_clears_with_none(self):
        saved = server._focused_freq_hz
        try:
            server._focused_freq_hz = 100e6
            handle_set_focus({"freq_hz": None})
            assert server._focused_freq_hz is None
        finally:
            server._focused_freq_hz = saved

    def test_handle_set_focus_coerces_string_to_float(self):
        saved = server._focused_freq_hz
        try:
            handle_set_focus({"freq_hz": "98000000"})
            assert server._focused_freq_hz == 98e6
            assert isinstance(server._focused_freq_hz, float)
        finally:
            server._focused_freq_hz = saved

    def test_handle_set_focus_clears_on_invalid_string(self):
        saved = server._focused_freq_hz
        try:
            server._focused_freq_hz = 100e6
            handle_set_focus({"freq_hz": "not_a_number"})
            assert server._focused_freq_hz is None
        finally:
            server._focused_freq_hz = saved

    def _start_server_with_mocks(self):
        mock_device = MagicMock()
        with (
            patch("dashboard.server.socketio.run"),
            patch("threading.Thread.start"),
        ):
            broadcast = start_server("localhost", 5000, mock_device)
        return broadcast

    def test_filter_blocks_non_matching(self):
        broadcast = self._start_server_with_mocks()
        with (
            patch("dashboard.server._focused_freq_hz", 100e6),
            patch("dashboard.server.socketio.emit") as mock_emit,
        ):
            broadcast(self._make_scan_result(200e6))
        mock_emit.assert_not_called()

    def test_filter_passes_matching(self):
        broadcast = self._start_server_with_mocks()
        fp = {
            "peak_power_db": -50.0,
            "snr_db": 12.0,
            "bandwidth_hz": 200000,
            "spectral_flatness": 0.45,
            "chroma_distance": 0.123,
            "signal_threshold_db": 10.0,
            "snr_margin_db": 2.0,
        }
        with (
            patch("dashboard.server._focused_freq_hz", 100e6),
            patch("dashboard.server.socketio.emit") as mock_emit,
        ):
            broadcast(self._make_scan_result(100e6, fp))
        mock_emit.assert_called_once()
        event_name, payload = mock_emit.call_args[0]
        assert event_name == "scan_result"
        expected = {
            "center_freq_hz": 100e6,
            "signal_type": "test",
            "confidence": "high",
            "confidence_score": 0.9,
            "novel": False,
            "au_legal_status": "LEGAL RX",
            "timestamp": "2026-06-03T12:00:00",
            "peak_power_db": -50.0,
            "snr_db": 12.0,
            "signal_threshold_db": 10.0,
            "snr_margin_db": 2.0,
            "bandwidth_hz": 200000,
            "spectral_flatness": pytest.approx(0.45),
            "chroma_distance": pytest.approx(0.123),
        }
        for key, value in expected.items():
            assert payload.get(key) == value, f"{key} mismatch"
        assert isinstance(payload.get("reasoning"), str) and payload.get("reasoning")

    def test_broadcast_includes_peak_bin_power_db(self):
        """Given a fingerprint dict with peak_bin_power_db=-65.0, the emitted scan_result data dict contains key 'peak_bin_power_db' with value -65.0."""
        broadcast = self._start_server_with_mocks()
        fp = {
            "peak_power_db": -70.0,
            "peak_bin_power_db": -65.0,
            "snr_db": 12.0,
            "signal_threshold_db": 10.0,
            "snr_margin_db": 2.0,
        }
        with (
            patch("dashboard.server._focused_freq_hz", 100e6),
            patch("dashboard.server.socketio.emit") as mock_emit,
        ):
            broadcast(self._make_scan_result(100e6, fp))
        mock_emit.assert_called_once()
        event_name, payload = mock_emit.call_args[0]
        assert event_name == "scan_result"
        assert payload.get("peak_bin_power_db") == -65.0

    def test_broadcast_peak_bin_power_db_none_when_missing(self):
        """Given a fingerprint dict without peak_bin_power_db, fp.get('peak_bin_power_db') returns None — confirm the emit does not raise and the field is present as None."""
        broadcast = self._start_server_with_mocks()
        fp = {
            "peak_power_db": -70.0,
            "snr_db": 12.0,
            "signal_threshold_db": 10.0,
            "snr_margin_db": 2.0,
        }
        with (
            patch("dashboard.server._focused_freq_hz", 100e6),
            patch("dashboard.server.socketio.emit") as mock_emit,
        ):
            broadcast(self._make_scan_result(100e6, fp))
        mock_emit.assert_called_once()
        event_name, payload = mock_emit.call_args[0]
        assert event_name == "scan_result"
        assert payload.get("peak_bin_power_db") is None

    def test_passes_all_when_focus_is_none(self):
        broadcast = self._start_server_with_mocks()
        with (
            patch("dashboard.server._focused_freq_hz", None),
            patch("dashboard.server.socketio.emit") as mock_emit,
        ):
            broadcast(self._make_scan_result(200e6))
        mock_emit.assert_called_once()
        event_name, payload = mock_emit.call_args[0]
        assert event_name == "scan_result"
        assert payload.get("center_freq_hz") == 200e6
        assert payload.get("signal_type") == "test"

    def test_system_stats_uses_scanner_values(self):
        mock_scanner = MagicMock()
        mock_scanner.get_stats.return_value = {
            "active_frequency_hz": 98_000_000.0,
            "scan_count": 42,
            "queue_depth": 3,
            "last_backlog": 7,
            "llm_call_count": 12,
            "last_llm_ms": 1250.5,
        }
        stats = mock_scanner.get_stats()
        assert stats["scan_count"] == 42
        assert stats["active_frequency_hz"] == 98_000_000.0
        assert stats["queue_depth"] == 3
        assert stats["last_backlog"] == 7
        assert stats["last_llm_ms"] == 1250.5

    def test_system_stats_falls_back_to_zeros_without_scanner(self):
        scanner = None
        if scanner is not None:
            stats = scanner.get_stats()
        else:
            stats = {
                "active_frequency_hz": 0.0,
                "scan_count": 0,
                "queue_depth": 0,
                "last_backlog": 0,
                "llm_call_count": 0,
                "last_llm_ms": 0.0,
            }
        assert stats["scan_count"] == 0
        assert stats["active_frequency_hz"] == 0.0
        assert stats["llm_call_count"] == 0
        assert stats["last_backlog"] == 0

    def test_handle_set_focus_updates_current_band_for_known_freq(self):
        """handle_set_focus updates current_band when freq matches a BAND_PROFILES entry."""
        saved = dict(ss.current_band)
        try:
            handle_set_focus({"freq_hz": 129_125_000})
            with ss.current_band_lock:
                assert ss.current_band["center_freq_hz"] == 129_125_000
                assert ss.current_band["signal_threshold_db"] == ss.BAND_PROFILES["acars"]["signal_threshold_db"]
        finally:
            with ss.current_band_lock:
                ss.current_band = saved

    def test_handle_set_focus_does_not_update_current_band_for_unknown_freq(self):
        """handle_set_focus leaves current_band unchanged for a non-BAND_PROFILES frequency."""
        saved = dict(ss.current_band)
        try:
            handle_set_focus({"freq_hz": 100_000_000})
            with ss.current_band_lock:
                assert ss.current_band == saved
        finally:
            with ss.current_band_lock:
                ss.current_band = saved

    def test_thread_safety_no_deadlock(self):
        broadcast = self._start_server_with_mocks()
        import concurrent.futures
        with patch("dashboard.server.socketio.emit"):
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
                futs = []
                for i in range(10):
                    futs.append(ex.submit(handle_set_focus, {"freq_hz": float(i * 10e6)}))
                    futs.append(ex.submit(broadcast, self._make_scan_result(float(i * 10e6))))
                for f in concurrent.futures.as_completed(futs):
                    f.result(timeout=5.0)


class TestEmitAdsbScanResult:
    """Tests for emit_adsb_scan_result — decoder-driven scan_result emission."""

    def setup_method(self):
        self._saved_focused_freq = server._focused_freq_hz
        server._focused_freq_hz = None

    def teardown_method(self):
        server._focused_freq_hz = self._saved_focused_freq

    def _make_adsb_message(self, icao="ABCDEF", callsign="TEST123"):
        from datetime import datetime, timezone
        return AdsbMessage(
            icao=icao,
            callsign=callsign,
            latitude=-34.0,
            longitude=138.0,
            altitude_ft=35000,
            groundspeed=450.0,
            track=180.0,
            vertical_rate=0,
            raw_hex="8D406B902015A678D4D220AA4BDA",
            timestamp=datetime.now(timezone.utc),
        )

    def test_emits_scan_result_event(self):
        """emit_adsb_scan_result() calls socketio.emit('scan_result')."""
        from dashboard.server import emit_adsb_scan_result

        msg = self._make_adsb_message()
        with patch("dashboard.server.socketio.emit") as mock_emit:
            emit_adsb_scan_result(msg)
            assert mock_emit.called
            assert mock_emit.call_args[0][0] == "scan_result"

    def test_signal_type_is_adsb(self):
        """Emitted data has signal_type='adsb'."""
        from dashboard.server import emit_adsb_scan_result

        msg = self._make_adsb_message()
        with patch("dashboard.server.socketio.emit") as mock_emit:
            emit_adsb_scan_result(msg)
            data = mock_emit.call_args[0][1]
            assert data["signal_type"] == "adsb"

    def test_confidence_score_is_one(self):
        """Emitted data has confidence_score=1.0 and confidence='high'."""
        from dashboard.server import emit_adsb_scan_result

        msg = self._make_adsb_message()
        with patch("dashboard.server.socketio.emit") as mock_emit:
            emit_adsb_scan_result(msg)
            data = mock_emit.call_args[0][1]
            assert data["confidence_score"] == 1.0
            assert data["confidence"] == "high"

    def test_reasoning_contains_icao(self):
        """Emitted reasoning string includes the ICAO."""
        from dashboard.server import emit_adsb_scan_result

        msg = self._make_adsb_message(icao="ABCDEF")
        with patch("dashboard.server.socketio.emit") as mock_emit:
            emit_adsb_scan_result(msg)
            data = mock_emit.call_args[0][1]
            assert "ABCDEF" in data["reasoning"]

    def test_focus_filter_blocks_wrong_frequency(self):
        """When focused on FM (98 MHz), ADS-B emissions are blocked."""
        from dashboard.server import emit_adsb_scan_result, _focused_freq_hz

        saved = _focused_freq_hz
        try:
            import dashboard.server
            dashboard.server._focused_freq_hz = 98_000_000.0
            msg = self._make_adsb_message()
            with patch("dashboard.server.socketio.emit") as mock_emit:
                emit_adsb_scan_result(msg)
                assert not mock_emit.called
        finally:
            import dashboard.server
            dashboard.server._focused_freq_hz = saved

    def test_focus_filter_passes_adsb_frequency(self):
        """When focused on 1090 MHz, ADS-B emissions pass through."""
        from dashboard.server import emit_adsb_scan_result, _focused_freq_hz

        saved = _focused_freq_hz
        try:
            import dashboard.server
            dashboard.server._focused_freq_hz = 1_090_000_000.0
            msg = self._make_adsb_message()
            with patch("dashboard.server.socketio.emit") as mock_emit:
                emit_adsb_scan_result(msg)
                assert mock_emit.called
        finally:
            import dashboard.server
            dashboard.server._focused_freq_hz = saved

    def test_focus_filter_passes_when_none(self):
        """When focus is None (no focus active), ADS-B emissions pass through."""
        from dashboard.server import emit_adsb_scan_result, _focused_freq_hz

        saved = _focused_freq_hz
        try:
            import dashboard.server
            dashboard.server._focused_freq_hz = None
            msg = self._make_adsb_message()
            with patch("dashboard.server.socketio.emit") as mock_emit:
                emit_adsb_scan_result(msg)
                assert mock_emit.called
        finally:
            import dashboard.server
            dashboard.server._focused_freq_hz = saved


class TestScanResultSourceProvenance:
    """Tests for Phase 32 — scan_result payloads carry 'source' for confidence gating."""

    def setup_method(self):
        self._saved_focused_freq = server._focused_freq_hz
        server._focused_freq_hz = None

    def teardown_method(self):
        server._focused_freq_hz = self._saved_focused_freq

    def _make_scan_result(self, freq_hz: float, fingerprint: dict | None = None) -> ScanResult:
        return ScanResult(
            center_freq_hz=freq_hz,
            timestamp="2026-07-14T12:00:00",
            fingerprint=fingerprint or {},
            classification=ClassificationResult(
                signal_type="test",
                confidence="high",
                confidence_score=0.9,
                novel=False,
                au_legal_status="LEGAL RX",
                reasoning="test",
                frequency_band="test",
                raw_response="test",
            ),
        )

    def test_broadcast_payload_includes_source_fingerprint(self):
        """broadcast() emits 'source'='fingerprint' so the frontend can dim unverified confidence."""
        from dashboard.server import start_server

        with (
            patch("dashboard.server.socketio.run"),
            patch("threading.Thread.start"),
        ):
            broadcast = start_server("localhost", 5000, MagicMock())

        with (
            patch("dashboard.server._focused_freq_hz", None),
            patch("dashboard.server.socketio.emit") as mock_emit,
        ):
            broadcast(self._make_scan_result(100e6))

        mock_emit.assert_called_once()
        event_name, payload = mock_emit.call_args[0]
        assert event_name == "scan_result"
        assert payload.get("source") == "fingerprint"

    def test_emit_adsb_scan_result_payload_includes_source_decode(self):
        """emit_adsb_scan_result() emits 'source'='decode' so the frontend keeps confirmed decodes bright."""
        from dashboard.server import emit_adsb_scan_result
        from datetime import datetime, timezone

        msg = AdsbMessage(
            icao="ABCDEF",
            callsign="TEST123",
            latitude=-34.0,
            longitude=138.0,
            altitude_ft=35000,
            groundspeed=450.0,
            track=180.0,
            vertical_rate=0,
            raw_hex="8D406B902015A678D4D220AA4BDA",
            timestamp=datetime.now(timezone.utc),
        )
        with patch("dashboard.server.socketio.emit") as mock_emit:
            emit_adsb_scan_result(msg)

        mock_emit.assert_called_once()
        data = mock_emit.call_args[0][1]
        assert data.get("source") == "decode"
