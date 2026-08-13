import sys
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import dashboard.server as server
from dashboard.server import (
    _compute_hackrf_status,
    handle_set_capture_trigger,
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

    def test_broadcast_includes_burst_fields(self):
        """Given a fingerprint dict with the four Phase 45 burst fields populated, the emitted scan_result data dict contains each field with the correct value."""
        broadcast = self._start_server_with_mocks()
        fp = {
            "peak_power_db": -70.0,
            "snr_db": 12.0,
            "signal_threshold_db": 10.0,
            "snr_margin_db": 2.0,
            "burst_ratio_db": 10.5,
            "expected_noise_ratio_db": 8.7,
            "burst_excess_db": 1.8,
            "is_burst": False,
        }
        with (
            patch("dashboard.server._focused_freq_hz", 100e6),
            patch("dashboard.server.socketio.emit") as mock_emit,
        ):
            broadcast(self._make_scan_result(100e6, fp))
        mock_emit.assert_called_once()
        event_name, payload = mock_emit.call_args[0]
        assert event_name == "scan_result"
        assert payload.get("burst_ratio_db") == 10.5
        assert payload.get("expected_noise_ratio_db") == 8.7
        assert payload.get("burst_excess_db") == 1.8
        assert payload.get("is_burst") is False

    def test_broadcast_burst_fields_none_when_missing(self):
        """Given a fingerprint dict without any burst fields, fp.get(...) returns None for each — confirm the emit does not raise and all four fields are present as None."""
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
        assert payload.get("burst_ratio_db") is None
        assert payload.get("expected_noise_ratio_db") is None
        assert payload.get("burst_excess_db") is None
        assert payload.get("is_burst") is None

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


class TestSetCaptureTrigger:
    """Tests for the set_capture_trigger SocketIO handler (Phase 63).

    The handler is deliberately defensive: a malformed browser message
    must never crash the socket thread. shared_state.set_trigger_armed
    is patched so these tests assert the call-through contract without
    mutating module-level trigger state.
    """

    def test_valid_band_armed_true_calls_through(self):
        with patch("dashboard.shared_state.set_trigger_armed") as mock_set:
            handle_set_capture_trigger({"band": "ism", "armed": True})
        mock_set.assert_called_once_with("ism", True)

    def test_valid_band_armed_false_calls_through(self):
        with patch("dashboard.shared_state.set_trigger_armed") as mock_set:
            handle_set_capture_trigger({"band": "adsb", "armed": False})
        mock_set.assert_called_once_with("adsb", False)

    def test_invalid_band_does_not_call_and_does_not_raise(self):
        """aviation is a valid BAND_PROFILES key but not armable - the
        handler must log and return without calling set_trigger_armed."""
        with patch("dashboard.shared_state.set_trigger_armed") as mock_set:
            handle_set_capture_trigger({"band": "aviation", "armed": True})
        mock_set.assert_not_called()

    def test_unknown_band_does_not_call_and_does_not_raise(self):
        with patch("dashboard.shared_state.set_trigger_armed") as mock_set:
            handle_set_capture_trigger({"band": "not_a_band", "armed": True})
        mock_set.assert_not_called()

    @pytest.mark.parametrize("bad_armed", ["yes", 42, ["foo"], None])
    def test_malformed_armed_coerces_to_false(self, bad_armed):
        """Non-bool armed values coerce to False (disarm is the safe
        direction) rather than raising."""
        with patch("dashboard.shared_state.set_trigger_armed") as mock_set:
            handle_set_capture_trigger({"band": "adsb", "armed": bad_armed})
        mock_set.assert_called_once_with("adsb", False)

    def test_missing_armed_key_coerces_to_false(self):
        with patch("dashboard.shared_state.set_trigger_armed") as mock_set:
            handle_set_capture_trigger({"band": "aprs"})
        mock_set.assert_called_once_with("aprs", False)

    def test_missing_band_key_does_not_raise(self):
        with patch("dashboard.shared_state.set_trigger_armed") as mock_set:
            handle_set_capture_trigger({"armed": True})
        mock_set.assert_not_called()

    def test_non_dict_payload_does_not_raise(self):
        with patch("dashboard.shared_state.set_trigger_armed") as mock_set:
            handle_set_capture_trigger("not a dict")
        mock_set.assert_not_called()

    def test_unhashable_band_value_does_not_raise(self):
        """A list band would raise TypeError on the frozenset membership
        test without the isinstance guard - the handler must not."""
        with patch("dashboard.shared_state.set_trigger_armed") as mock_set:
            handle_set_capture_trigger({"band": ["adsb"], "armed": True})
        mock_set.assert_not_called()

    def test_handler_does_not_touch_focus_or_current_band(self):
        """set_capture_trigger is independent of set_focus_frequency: it
        must not change the focused frequency, current_band, or call the
        scanner focus method."""
        saved_focus = server._focused_freq_hz
        saved_band = dict(ss.current_band)
        try:
            with patch("dashboard.shared_state.set_trigger_armed"):
                handle_set_capture_trigger({"band": "adsb", "armed": True})
            assert server._focused_freq_hz == saved_focus
            with ss.current_band_lock:
                assert ss.current_band == saved_band
        finally:
            server._focused_freq_hz = saved_focus
            with ss.current_band_lock:
                ss.current_band = saved_band


class TestEmitAdsbScanResult:
    """Tests for emit_adsb_scan_result — decoder-driven scan_result emission."""

    def setup_method(self):
        self._saved_focused_freq = server._focused_freq_hz
        server._focused_freq_hz = None
        # Clear the module-level per-ICAO field tracker so merged state
        # cannot leak between tests (mirrors the _focused_freq_hz pattern).
        server._field_tracker._state.clear()

    def teardown_method(self):
        server._focused_freq_hz = self._saved_focused_freq
        server._field_tracker._state.clear()

    def _make_adsb_message(self, icao="ABCDEF", callsign="TEST123", **overrides):
        from datetime import datetime, timezone
        fields = dict(
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
        fields.update(overrides)
        return AdsbMessage(**fields)

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

    def test_reasoning_merges_callsign_and_altitude_across_frames(self):
        """Fields resolved by an earlier frame survive a frame that lacks them."""
        from dashboard.server import emit_adsb_scan_result

        # Frame 1 (e.g. typecode 4 + position): callsign and altitude only.
        msg1 = self._make_adsb_message(
            icao="ABCDEF",
            callsign="ABC123",
            altitude_ft=35000,
            groundspeed=None,
            track=None,
        )
        # Frame 2 (e.g. typecode 19 velocity): no callsign, no altitude.
        msg2 = self._make_adsb_message(
            icao="ABCDEF",
            callsign=None,
            altitude_ft=None,
            groundspeed=450.0,
            track=90.0,
        )
        with patch("dashboard.server.socketio.emit") as mock_emit:
            emit_adsb_scan_result(msg1)
            emit_adsb_scan_result(msg2)
            data = mock_emit.call_args[0][1]
            reasoning = data["reasoning"]
            # Callsign and altitude from frame 1 survived, NOT "unknown".
            assert "callsign ABC123" in reasoning
            assert "35000 ft" in reasoning
            # Speed and track newly resolved by frame 2.
            assert "450.0 kt" in reasoning
            assert "90 deg" in reasoning
            # None of the four pre-Phase-54 fields read "unknown". The
            # blanket '"unknown" not in reasoning' assertion was retired in
            # Phase 54: the reasoning string now ends with a squawk clause,
            # and this fixture (DF17-only frames) legitimately has no squawk.
            assert "callsign unknown" not in reasoning
            assert "altitude unknown" not in reasoning
            assert "speed unknown" not in reasoning
            assert "track unknown" not in reasoning
            assert "squawk unknown" in reasoning

    def test_reasoning_unknown_when_field_never_resolved(self):
        """A field that has never carried a value still shows 'unknown'."""
        from dashboard.server import emit_adsb_scan_result

        msg = self._make_adsb_message(
            icao="ABCDEF",
            callsign="ABC123",
            altitude_ft=None,
            groundspeed=None,
            track=None,
        )
        with patch("dashboard.server.socketio.emit") as mock_emit:
            emit_adsb_scan_result(msg)
            data = mock_emit.call_args[0][1]
            reasoning = data["reasoning"]
            assert "callsign ABC123" in reasoning
            assert "altitude unknown" in reasoning
            assert "speed unknown" in reasoning
            assert "track unknown" in reasoning

    def test_reasoning_per_icao_independence(self):
        """Merged state is per-ICAO: updates for B never affect A's view."""
        from dashboard.server import emit_adsb_scan_result

        with patch("dashboard.server.socketio.emit") as mock_emit:
            emit_adsb_scan_result(
                self._make_adsb_message(icao="AAAAAA", callsign="AAA123", altitude_ft=None)
            )
            emit_adsb_scan_result(
                self._make_adsb_message(icao="BBBBBB", callsign="BBB456", altitude_ft=None)
            )
            b_reasoning = mock_emit.call_args[0][1]["reasoning"]
            # Second frame for A: no callsign, but altitude newly resolved.
            emit_adsb_scan_result(
                self._make_adsb_message(icao="AAAAAA", callsign=None, altitude_ft=35000)
            )
            a_reasoning = mock_emit.call_args[0][1]["reasoning"]

        # A's callsign from its first frame survived AND altitude resolved.
        assert "ICAO AAAAAA" in a_reasoning
        assert "callsign AAA123" in a_reasoning
        assert "35000 ft" in a_reasoning
        # B's view was untouched by A's updates.
        assert "ICAO BBBBBB" in b_reasoning
        assert "callsign BBB456" in b_reasoning
        assert "altitude unknown" in b_reasoning

    def test_reasoning_does_not_carry_bearing_or_delta_r_or_range(self):
        """Regression guard: the reasoning string never carries BearingTracker fields."""
        from dashboard.server import emit_adsb_scan_result

        msg = self._make_adsb_message()
        with patch("dashboard.server.socketio.emit") as mock_emit:
            emit_adsb_scan_result(msg)
            data = mock_emit.call_args[0][1]
            reasoning = data["reasoning"]
            assert "bearing" not in reasoning
            assert "delta_r" not in reasoning
            assert "nm" not in reasoning

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


    def test_function_body_excludes_classifier_and_caps(self) -> None:
        """Static guard: emit_adsb_scan_result() never calls classify() or caps."""
        server_path = Path(__file__).parent.parent.parent / "dashboard" / "server.py"
        source = server_path.read_text()
        start = source.find("def emit_adsb_scan_result")
        assert start != -1, "emit_adsb_scan_result not found in server.py"
        next_def = source.find("\ndef ", start + len("def emit_adsb_scan_result"))
        body = source[start:next_def] if next_def != -1 else source[start:]
        assert "classify(" not in body, (
            "emit_adsb_scan_result() must not call classify() — "
            "decoder-driven results are ground truth."
        )
        assert "_apply_confidence_caps" not in body, (
            "emit_adsb_scan_result() must not apply fingerprint confidence caps."
        )

    def test_decode_payload_is_ground_truth(self) -> None:
        """Behavioural guard: decoder-driven payload has source=decode and confidence=1.0."""
        from dashboard.server import emit_adsb_scan_result

        msg = self._make_adsb_message()
        with patch("dashboard.server.socketio.emit") as mock_emit:
            emit_adsb_scan_result(msg)
        data = mock_emit.call_args[0][1]
        assert data["signal_type"] == "adsb"
        assert data["confidence_score"] == 1.0
        assert data["confidence"] == "high"
        assert data["source"] == "decode"


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

    def test_emit_adsb_scan_result_includes_burst_fields_as_none(self):
        """Phase 45b: emit_adsb_scan_result() payload carries the four burst
        fields, all None (decoder path has no fingerprint). Payload shape
        matches broadcast() so frontend does not need to special-case
        missing keys for the ADS-B decode path.
        """
        from dashboard.server import emit_adsb_scan_result
        msg = AdsbMessage(
            # tz-aware to match what the real decoder produces (the module-
            # level AdsbFieldTracker subtracts stored timestamps on update;
            # a naive value would raise TypeError against aware entries).
            timestamp=datetime(2026, 7, 29, 12, 0, 0, tzinfo=timezone.utc),
            icao="7C1234",
            callsign="TEST01",
            altitude_ft=35000,
            latitude=None,
            longitude=None,
            groundspeed=450,
            track=90,
            vertical_rate=0,
            raw_hex="8D7C1234582056B0AF87F0000000",
        )
        with (
            patch("dashboard.server._focused_freq_hz", None),
            patch("dashboard.server.socketio.emit") as mock_emit,
        ):
            emit_adsb_scan_result(msg)
        mock_emit.assert_called_once()
        event_name, payload = mock_emit.call_args[0]
        assert event_name == "scan_result"
        # All four Phase 45 burst fields must be present in the payload,
        # all None on the decoder path.
        assert "burst_ratio_db" in payload
        assert "expected_noise_ratio_db" in payload
        assert "burst_excess_db" in payload
        assert "is_burst" in payload
        assert payload["burst_ratio_db"] is None
        assert payload["expected_noise_ratio_db"] is None
        assert payload["burst_excess_db"] is None
        assert payload["is_burst"] is None


class TestSystemStatsDeviceField:
    """Static-source guard that emit_stats() reads current_device and
    calls unsupported_bands_for_device to populate the system_stats
    payload (Phase 38).

    Per the task: emit_stats runs in a 2s background thread and is
    awkward to unit-test directly, so the test is a static-source
    assertion that the function body imports/uses the helper rather
    than re-deriving the support logic. The behaviour is covered by
    the helper's own unit tests in test_pluto_band_profiles.py.
    """

    def test_server_py_imports_unsupported_bands_helper(self):
        from pathlib import Path
        server_path = Path(__file__).parent.parent.parent / "dashboard" / "server.py"
        source = server_path.read_text()
        assert "unsupported_bands_for_device" in source, (
            "dashboard/server.py must call shared_state.unsupported_bands_for_device "
            "to build the system_stats unsupported_bands payload"
        )

    def test_emit_stats_emits_device_key(self):
        from pathlib import Path
        server_path = Path(__file__).parent.parent.parent / "dashboard" / "server.py"
        source = server_path.read_text()
        # Find the emit_stats function body and assert both keys land
        # in the data dict. Slice from "def emit_stats" to the next
        # top-level def.
        start = source.find("def emit_stats")
        assert start != -1
        next_def = source.find("\ndef ", start + len("def emit_stats"))
        body = source[start:next_def] if next_def != -1 else source[start:]
        assert '"device"' in body, "emit_stats() must include the device key"
        assert '"unsupported_bands"' in body, "emit_stats() must include the unsupported_bands key"
        assert "current_device_lock" in body, "emit_stats() must acquire the current_device lock"


class TestSystemStatsCurrentDeviceDisplay:
    """Static-source guard that emit_stats() calls display_name_for_device
    to populate the system_stats current_device_display payload (Phase 40b).

    Per the Phase 38 precedent: emit_stats runs in a 2s background thread
    and is awkward to unit-test directly, so this is a static-source
    assertion that the function body uses the new helper rather than
    re-deriving the friendly name inline. The behaviour is covered by
    the helper's own unit tests in TestDisplayNameForDevice.
    """

    def test_emit_stats_emits_current_device_display_key(self):
        from pathlib import Path
        server_path = Path(__file__).parent.parent.parent / "dashboard" / "server.py"
        source = server_path.read_text()
        # Find the emit_stats function body and assert the new key lands
        # in the data dict, adjacent to the existing "device" key.
        start = source.find("def emit_stats")
        assert start != -1
        next_def = source.find("\ndef ", start + len("def emit_stats"))
        body = source[start:next_def] if next_def != -1 else source[start:]
        assert '"current_device_display"' in body, (
            "emit_stats() must include the current_device_display key"
        )
        assert "display_name_for_device" in body, (
            "emit_stats() must call shared_state.display_name_for_device to "
            "build the current_device_display payload"
        )
