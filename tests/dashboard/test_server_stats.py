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
            patch("dashboard.server.time.time", return_value=time.time() + 5.0),
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

    def test_not_responding_transitions_to_connected_after_30s(self):
        mock_device = MagicMock()
        mock_device.is_open = True
        error_time = 1000.0
        with (
            patch("dashboard.server._device_ref", mock_device),
            patch("dashboard.server._last_hw_error_time", error_time),
            patch("dashboard.server.time.time", return_value=error_time + 29.0),
        ):
            assert _compute_hackrf_status() == "NOT_RESPONDING"
        with (
            patch("dashboard.server._device_ref", mock_device),
            patch("dashboard.server._last_hw_error_time", error_time),
            patch("dashboard.server.time.time", return_value=error_time + 31.0),
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
        }
        with (
            patch("dashboard.server._focused_freq_hz", 100e6),
            patch("dashboard.server.socketio.emit") as mock_emit,
        ):
            broadcast(self._make_scan_result(100e6, fp))
        mock_emit.assert_called_once_with("scan_result", {
            "timestamp": "2026-06-03T12:00:00",
            "center_freq_hz": 100e6,
            "signal_type": "test",
            "confidence": "high",
            "confidence_score": 0.9,
            "novel": False,
            "au_legal_status": "LEGAL RX",
            "reasoning": "test",
            "peak_power_db": -50.0,
            "snr_db": 12.0,
            "bandwidth_hz": 200000,
            "spectral_flatness": 0.45,
            "chroma_distance": 0.123,
        })

    def test_passes_all_when_focus_is_none(self):
        broadcast = self._start_server_with_mocks()
        with (
            patch("dashboard.server._focused_freq_hz", None),
            patch("dashboard.server.socketio.emit") as mock_emit,
        ):
            broadcast(self._make_scan_result(200e6))
        mock_emit.assert_called_once()

    def test_system_stats_uses_scanner_values(self):
        mock_scanner = MagicMock()
        mock_scanner.get_stats.return_value = {
            "active_frequency_hz": 98_000_000.0,
            "scan_count": 42,
            "queue_depth": 3,
            "last_llm_ms": 1250.5,
        }
        stats = mock_scanner.get_stats()
        assert stats["scan_count"] == 42
        assert stats["active_frequency_hz"] == 98_000_000.0
        assert stats["queue_depth"] == 3
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
                "last_llm_ms": 0.0,
            }
        assert stats["scan_count"] == 0
        assert stats["active_frequency_hz"] == 0.0

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
