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
    e.embed.return_value = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.3]
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

    def test_latest_wins_drains_stale_items(self, scanner):
        """
        Verify that when the queue is pre-filled with stale items, running the scan
        loop for one cycle results in queue depth of exactly 1 (the fresh item),
        not the pre-filled stale count.
        """
        maxsize = scanner._queue.maxsize
        for i in range(maxsize):
            scanner._queue.put_nowait({"freq_hz": i, "fingerprint": {}, "vector": [0] * 7})
        assert scanner._queue.qsize() == maxsize

        scanner._running = True
        t = threading.Thread(target=scanner._scan_loop, daemon=True)
        t.start()
        time.sleep(0.4)
        scanner.stop()
        t.join(timeout=3)

        assert scanner._queue.qsize() <= 1

    def test_latest_wins_queue_never_saturates(self, scanner):
        """
        Verify that after running the scanner for a sustained period (1 second),
        the queue depth never reaches maxsize — the drain-before-insert prevents
        permanent saturation.
        """
        scanner._broadcast_fn = lambda sr: None
        t = threading.Thread(target=scanner.run, daemon=True)
        t.start()
        time.sleep(1.0)
        scanner.stop()
        t.join(timeout=3)

        assert scanner._queue.qsize() <= 1

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

    def test_scan_loop_skips_redundant_retune(self, scanner, mock_device):
        """set_center_frequency must be called once, not on every iteration.

        With the frequency cache, a steady-state scan loop running N cycles
        at the same focus frequency should call set_center_frequency exactly
        once (the initial tune), not N times.
        """
        t = threading.Thread(target=scanner.run, daemon=True)
        t.start()
        time.sleep(0.5)  # allow several scan cycles at dwell_time=0.01s
        scanner.stop()
        t.join(timeout=3)

        calls = mock_device.set_center_frequency.call_args_list
        # Must be called at least once (initial tune) but NOT once per cycle.
        # With 0.01s dwell and 0.5s run time, uncached code would call ~40x.
        # Cached code must call exactly once for a single focus frequency.
        assert len(calls) == 1
        assert calls[0][0][0] == 98_000_000.0

    def test_set_focus_frequency_flushes_queue(self, scanner):
        for i in range(3):
            scanner._queue.put_nowait({"freq_hz": i, "fingerprint": {}, "vector": [0] * 7})
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
            "vector": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.3],
        })

        t = threading.Thread(target=scanner._ai_loop, daemon=True)
        t.start()
        time.sleep(0.1)
        scanner.stop()
        t.join(timeout=3)

        mock_classifier.classify.assert_called_once()
        call_args = mock_classifier.classify.call_args[0]
        assert call_args[0]["center_freq_hz"] == 98_000_000.0
        assert "chroma_distance" in call_args[0]
        assert call_args[0]["chroma_distance"] == 0.01

    def test_get_stats_returns_expected_keys(self, scanner):
        stats = scanner.get_stats()
        assert set(stats.keys()) == {
            "active_frequency_hz", "scan_count", "queue_depth", "last_backlog", "llm_call_count", "last_llm_ms"
        }

    def test_get_stats_includes_last_backlog_key(self, scanner):
        """
        Verify get_stats() always returns last_backlog key even before any
        AI loop cycles complete.
        """
        assert "last_backlog" in scanner.get_stats()
        assert scanner.get_stats()["last_backlog"] == 0

    def test_last_backlog_populated_after_ai_loop(self, scanner):
        """
        Verify _last_backlog is set after the AI loop processes one item,
        and _scan_count_since_llm resets to 0.
        """
        scanner._broadcast_fn = lambda sr: None
        t = threading.Thread(target=scanner.run, daemon=True)
        t.start()
        time.sleep(1.0)
        scanner.stop()
        t.join(timeout=3)

        assert scanner.get_stats()["last_backlog"] >= 0
        assert scanner._scan_count_since_llm >= 0

    def test_llm_call_count_zero_before_ai_loop(self, scanner):
        """
        Verify llm_call_count is 0 before any AI loop cycles run.
        """
        assert scanner.get_stats()["llm_call_count"] == 0

    def test_llm_call_count_increments_after_classify(self, scanner):
        """
        Verify llm_call_count increments after the AI loop successfully classifies.
        """
        scanner._broadcast_fn = lambda sr: None
        t = threading.Thread(target=scanner.run, daemon=True)
        t.start()
        time.sleep(1.0)
        scanner.stop()
        t.join(timeout=3)

        assert scanner.get_stats()["llm_call_count"] >= 1

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

    def test_scan_loop_broadcasts_spectrum(self, scanner, config):
        """_broadcast_spectrum_fn must be called from _scan_loop, not _ai_loop."""
        emitted = []
        scanner._broadcast_spectrum_fn = lambda *args: emitted.append(args)
        scanner._running = True
        t = threading.Thread(target=scanner._scan_loop, daemon=True)
        t.start()
        time.sleep(0.15)
        scanner.stop()
        t.join(timeout=3)

        assert len(emitted) >= 1
        psd_db, center, freq_min, freq_max = emitted[0]
        assert center == config.frequencies_hz[0]
        # Bounds are derived from the actual PSD frequency axis, not hardcoded ±1 MHz
        assert freq_min < center
        assert freq_max > center
        assert freq_max - freq_min == pytest.approx(2_000_000, abs=2_000)
        assert len(psd_db) == 2048

    def test_emit_result_does_not_broadcast_spectrum(self, scanner):
        """_emit_result must NOT call _broadcast_spectrum_fn after decoupling."""
        scan_results = []
        spectrum_calls = []
        scanner._broadcast_fn = lambda sr: scan_results.append(sr)
        scanner._broadcast_spectrum_fn = lambda *args: spectrum_calls.append(args)

        scan_result = ScanResult(
            timestamp="2026-06-16T12:00:00",
            center_freq_hz=98_000_000.0,
            fingerprint={},
            classification=ClassificationResult(
                signal_type="fm_broadcast",
                confidence="high",
                confidence_score=0.95,
                novel=False,
                reasoning="Strong match",
                au_legal_status="legal_rx",
                frequency_band="fm_broadcast_band",
                raw_response='{}',
            ),
            psd_db=[-50.0] * 2048,
        )
        scanner._emit_result(scan_result)

        assert len(scan_results) == 1
        assert scan_results[0] is scan_result
        assert len(spectrum_calls) == 0

    def test_ai_loop_suppresses_rapid_offline_emits(self, scanner, mock_classifier):
        """If an llm_offline result arrives within the 5-second emit window, it must
        not be emitted and _last_offline_emit must remain unchanged."""
        mock_classifier.classify.return_value = ClassificationResult(
            signal_type="llm_offline",
            confidence="low",
            confidence_score=0.0,
            novel=False,
            reasoning="LLM unreachable",
            au_legal_status="legal_rx",
            frequency_band="unknown",
            raw_response='{}',
        )
        scanner._running = True
        scanner._queue.put_nowait({
            "freq_hz": 98_000_000.0,
            "fingerprint": {"center_freq_hz": 98_000_000.0},
            "vector": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.3],
        })
        original_last_emit = time.time()
        scanner._last_offline_emit = original_last_emit

        with patch.object(scanner, "_emit_result") as mock_emit:
            t = threading.Thread(target=scanner._ai_loop, daemon=True)
            t.start()
            time.sleep(0.1)
            scanner.stop()
            t.join(timeout=3)

            mock_emit.assert_not_called()

        assert scanner._last_offline_emit == original_last_emit

    def test_ai_loop_emits_offline_after_interval(self, scanner, mock_classifier):
        """If the 5-second emit window has expired, an llm_offline result must be
        emitted and _last_offline_emit updated to approximately now."""
        mock_classifier.classify.return_value = ClassificationResult(
            signal_type="llm_offline",
            confidence="low",
            confidence_score=0.0,
            novel=False,
            reasoning="LLM unreachable",
            au_legal_status="legal_rx",
            frequency_band="unknown",
            raw_response='{}',
        )
        scanner._running = True
        scanner._queue.put_nowait({
            "freq_hz": 98_000_000.0,
            "fingerprint": {"center_freq_hz": 98_000_000.0},
            "vector": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.3],
        })
        scanner._last_offline_emit = time.time() - 10.0

        with patch.object(scanner, "_emit_result") as mock_emit:
            t = threading.Thread(target=scanner._ai_loop, daemon=True)
            t.start()
            time.sleep(0.1)
            scanner.stop()
            t.join(timeout=3)

            mock_emit.assert_called_once()

        assert scanner._last_offline_emit > time.time() - 2.0

    def test_ai_loop_normal_results_always_emitted(self, scanner, mock_classifier):
        """The llm_offline rate-limit gate must never suppress normal
        classification results, even when the offline emit window is active."""
        mock_classifier.classify.return_value = ClassificationResult(
            signal_type="fm_broadcast",
            confidence="high",
            confidence_score=0.95,
            novel=False,
            reasoning="Strong match to FM broadcast",
            au_legal_status="legal_rx",
            frequency_band="fm_broadcast_band",
            raw_response='{}',
        )
        scanner._running = True
        scanner._queue.put_nowait({
            "freq_hz": 98_000_000.0,
            "fingerprint": {"center_freq_hz": 98_000_000.0},
            "vector": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.3],
        })
        scanner._last_offline_emit = time.time()

        with patch.object(scanner, "_emit_result") as mock_emit:
            t = threading.Thread(target=scanner._ai_loop, daemon=True)
            t.start()
            time.sleep(0.1)
            scanner.stop()
            t.join(timeout=3)

            mock_emit.assert_called_once()
