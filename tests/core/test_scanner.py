"""
tests/core/test_scanner.py
Mimir RF Scanner — ScanRunner Tests

Tests for core/pipeline/scanner.py
All tests use mocks — no hardware required.
"""

import logging
import os
import sys
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from core.config.loader import MimirConfig
from core.pipeline.scan_result import ScanResult
from core.pipeline.scanner import ScanRunner
from llm.classifier import ClassificationResult


@pytest.fixture
def config():
    return MimirConfig(
        frequencies_hz=[98_000_000.0, 145_175_000.0],
        dwell_time_sec=0.01,
        num_samples=2048,
        lna_gain_db=32.0,
        vga_gain_db=40.0,
        amp_enable=False,
        queue_maxsize=3,
        dashboard_host="127.0.0.1",
        dashboard_port=5000,
    )


@pytest.fixture
def mock_device():
    d = MagicMock()
    d.read_samples.return_value = (
        __import__("numpy").random.randn(2048).astype("float32")
        + 1j * __import__("numpy").random.randn(2048).astype("float32")
    )
    return d


@pytest.fixture
def mock_embedder():
    e = MagicMock()
    e.embed.return_value = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6]
    return e


@pytest.fixture
def mock_store():
    s = MagicMock()
    s.query.return_value = {
        "ids": [["a", "b"]],
        "distances": [[0.01, 0.05]],
        "metadatas": [[{"label": "fm_broadcast"}, {"label": "noise"}]],
    }
    return s


@pytest.fixture
def mock_classifier():
    c = MagicMock()
    c.classify.return_value = ClassificationResult(
        signal_type="fm_broadcast",
        confidence="high",
        confidence_score=0.95,
        novel=False,
        reasoning="Strong match to FM broadcast",
        au_legal_status="legal_rx",
        frequency_band="fm_broadcast_band",
        raw_response='{"signal_type": "fm_broadcast"}',
    )
    return c


@pytest.fixture
def scanner(config, mock_device, mock_embedder, mock_store, mock_classifier):
    return ScanRunner(mock_device, mock_embedder, mock_store, mock_classifier, config)


class TestScanRunner:
    def test_single_cycle_emits_scan_result(
        self, scanner, mock_device, mock_embedder, mock_store, mock_classifier
    ):
        emitted = []
        scanner._broadcast_fn = lambda sr: emitted.append(sr)

        t = threading.Thread(target=scanner.run, daemon=True)
        t.start()
        time.sleep(0.6)
        scanner.stop()
        t.join(timeout=3)

        assert len(emitted) >= 1
        assert isinstance(emitted[0], ScanResult)

    def test_queue_full_logs_warning_and_continues(self, scanner, config, caplog):
        config.queue_maxsize = 1
        scanner._queue.put_nowait({"freq_hz": 0, "fingerprint": {}, "vector": [0]*6})
        scanner._running = True

        with caplog.at_level(logging.WARNING, logger="core.pipeline.scanner"):
            t = threading.Thread(target=scanner._scan_loop, daemon=True)
            t.start()
            time.sleep(0.5)
            scanner.stop()
            t.join(timeout=3)

        assert any("Queue full" in msg for msg in caplog.messages)

    def test_stop_joins_both_threads(self, scanner):
        t = threading.Thread(target=scanner.run, daemon=True)
        t.start()
        time.sleep(0.05)
        scanner.stop()
        t.join(timeout=3)
        assert not t.is_alive()

    def test_scan_loop_stays_on_focus_frequency(self, scanner, mock_device):
        t = threading.Thread(target=scanner.run, daemon=True)
        t.start()
        time.sleep(0.5)
        scanner.stop()
        t.join(timeout=3)

        calls = mock_device.set_center_frequency.call_args_list
        assert len(calls) >= 1
        for call in calls:
            assert call[0][0] == 98_000_000.0

    def test_set_focus_frequency_flushes_queue(self, scanner):
        for i in range(3):
            scanner._queue.put_nowait({"freq_hz": i, "fingerprint": {}, "vector": [0] * 6})
        assert scanner._queue.qsize() == 3
        scanner.set_focus_frequency(1_090_000_000.0)
        assert scanner._queue.qsize() == 0
        assert scanner._focus_freq_hz == 1_090_000_000.0

    def test_read_error_calls_record_hw_error(
        self, config, mock_device, mock_embedder, mock_store, mock_classifier
    ):
        mock_device.read_samples.side_effect = RuntimeError("USB timeout")
        scanner = ScanRunner(mock_device, mock_embedder, mock_store, mock_classifier, config)

        with patch("core.pipeline.scanner.record_hw_error") as mock_record:
            t = threading.Thread(target=scanner.run, daemon=True)
            t.start()
            time.sleep(0.3)
            scanner.stop()
            t.join(timeout=3)

            mock_record.assert_called()

    def test_ai_thread_classifies_queued_item(
        self, scanner, mock_store, mock_classifier
    ):
        scanner._running = True
        scanner._queue.put_nowait({
            "freq_hz": 98_000_000.0,
            "fingerprint": {"center_freq_hz": 98_000_000.0},
            "vector": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6],
        })

        t = threading.Thread(target=scanner._ai_loop, daemon=True)
        t.start()
        time.sleep(0.1)
        scanner.stop()
        t.join(timeout=3)

        mock_classifier.classify.assert_called_once()
        call_args = mock_classifier.classify.call_args[0]
        assert call_args[0]["center_freq_hz"] == 98_000_000.0

    def test_get_stats_returns_expected_keys(self, scanner):
        stats = scanner.get_stats()
        assert set(stats.keys()) == {
            "active_frequency_hz", "scan_count", "queue_depth", "last_llm_ms"
        }

    def test_scan_count_increments_after_run(self, scanner):
        scanner._broadcast_fn = lambda sr: None
        t = threading.Thread(target=scanner.run, daemon=True)
        t.start()
        time.sleep(0.5)
        scanner.stop()
        t.join(timeout=3)
        assert scanner.get_stats()["scan_count"] > 0

    def test_active_freq_hz_set_after_run(self, scanner, config):
        scanner._broadcast_fn = lambda sr: None
        t = threading.Thread(target=scanner.run, daemon=True)
        t.start()
        time.sleep(0.5)
        scanner.stop()
        t.join(timeout=3)
        assert scanner.get_stats()["active_frequency_hz"] in config.frequencies_hz

    def test_queue_depth_is_non_negative(self, scanner):
        assert scanner.get_stats()["queue_depth"] >= 0

    def test_last_llm_ms_non_negative(self, scanner):
        assert scanner.get_stats()["last_llm_ms"] >= 0.0

    def test_last_llm_ms_populated_after_ai_loop(self, scanner):
        scanner._broadcast_fn = lambda sr: None
        t = threading.Thread(target=scanner.run, daemon=True)
        t.start()
        time.sleep(0.5)
        scanner.stop()
        t.join(timeout=3)
        assert scanner.get_stats()["last_llm_ms"] >= 0.0
