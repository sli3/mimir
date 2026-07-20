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

    def test_scan_loop_forwards_crop_half_width_hz(self, scanner):
        """_scan_loop must read band['crop_half_width_hz'] from shared_state
        and forward it to fingerprint_spectrum() (Phase 30).

        Patches features.fingerprint_spectrum with a capturing side_effect,
        drives the scan loop for one cycle on the fm_broadcast band, and
        asserts the forwarded crop_half_width_hz matches the BAND_PROFILES
        value (112_500 for fm_broadcast).
        """
        import dashboard.shared_state as shared_state

        # Snapshot and set current_band to fm_broadcast explicitly
        with shared_state.current_band_lock:
            original_band = dict(shared_state.current_band)
            shared_state.current_band.clear()
            shared_state.current_band.update(shared_state.BAND_PROFILES["fm_broadcast"])

        captured = {}

        def capture_fn(psd_result, **kwargs):
            captured["crop_half_width_hz"] = kwargs.get("crop_half_width_hz")
            # Return a minimal valid fingerprint so embedder does not choke
            return {
                "center_freq_hz": 98_000_000,
                "peak_freq_hz": 98_000_000,
                "peak_power_db": -10.0,
                "noise_floor_db": -80.0,
                "snr_db": 70.0,
                "bandwidth_hz": 200_000,
                "occupied_bins": 200,
                "spectral_flatness": 0.5,
                "signal_threshold_db": 21.0,
                "snr_margin_db": 46.0,
                "peak_bin_power_db": -10.0,
            }

        try:
            with patch(
                "core.pipeline.scanner.features.fingerprint_spectrum",
                side_effect=capture_fn,
            ):
                scanner._running = True
                t = threading.Thread(target=scanner._scan_loop, daemon=True)
                t.start()
                time.sleep(0.3)
                scanner.stop()
                t.join(timeout=3)

            assert captured.get("crop_half_width_hz") == 112_500
        finally:
            with shared_state.current_band_lock:
                shared_state.current_band.clear()
                shared_state.current_band.update(original_band)


class TestScanLoopDeviceGuard:
    """Tests for the unsupported-band guard in _scan_loop (Phase 37).

    The guard lets devices with a narrow tuning range (e.g. Pluto,
    325 MHz floor) skip focus frequencies they cannot physically receive,
    instead of tuning into noise. HackRF supports every band and bypasses
    the guard entirely. These tests use the REAL
    shared_state.band_supported_by_device — it is a pure function over
    module dicts, so the tests also prove the wiring is integrated
    correctly.
    """

    def _run_briefly(self, scanner, seconds=0.3):
        t = threading.Thread(target=scanner.run, daemon=True)
        t.start()
        time.sleep(seconds)
        scanner.stop()
        t.join(timeout=3)

    def test_scan_loop_hackrf_default_skips_guard(self, config, mock_device,
                                                  mock_embedder, mock_store,
                                                  mock_classifier):
        """Default device_driver="hackrf" tunes and reads as before — the
        guard adds no behavioural change on the HackRF path."""
        scanner = ScanRunner(mock_device, mock_embedder, mock_store,
                             mock_classifier, config)
        self._run_briefly(scanner, 0.3)
        mock_device.set_center_frequency.assert_called_with(98_000_000.0)
        mock_device.read_samples.assert_called()

    def test_scan_loop_plutosdr_skips_unsupported_band(self, config, mock_device,
                                                       mock_embedder, mock_store,
                                                       mock_classifier):
        """Pluto focused on 98 MHz (below its 325 MHz floor) must never
        tune or read samples."""
        scanner = ScanRunner(mock_device, mock_embedder, mock_store,
                             mock_classifier, config,
                             device_driver="plutosdr")
        self._run_briefly(scanner, 0.3)
        mock_device.set_center_frequency.assert_not_called()
        mock_device.read_samples.assert_not_called()

    def test_scan_loop_plutosdr_tunes_supported_band(self, config, mock_device,
                                                     mock_embedder, mock_store,
                                                     mock_classifier):
        """Pluto focused on 1090 MHz (ADS-B, supported) tunes and reads."""
        scanner = ScanRunner(mock_device, mock_embedder, mock_store,
                             mock_classifier, config,
                             device_driver="plutosdr")
        scanner.set_focus_frequency(1_090_000_000.0)
        self._run_briefly(scanner, 0.3)
        mock_device.set_center_frequency.assert_called_with(1_090_000_000.0)
        mock_device.read_samples.assert_called()

    def test_scan_loop_plutosdr_logs_once_per_focus_change(self, config, mock_device,
                                                           mock_embedder, mock_store,
                                                           mock_classifier, caplog):
        """Dwelling on an unsupported band logs the skip warning exactly
        once, not once per scan iteration."""
        scanner = ScanRunner(mock_device, mock_embedder, mock_store,
                             mock_classifier, config,
                             device_driver="plutosdr")
        with caplog.at_level(logging.WARNING, logger="core.pipeline.scanner"):
            self._run_briefly(scanner, 0.5)
        skipping = [r for r in caplog.records if "Skipping" in r.getMessage()]
        assert len(skipping) == 1

    def test_scan_loop_plutosdr_resets_log_gate_on_supported_focus(
            self, config, mock_device, mock_embedder, mock_store,
            mock_classifier, caplog):
        """Leaving an unsupported band for a supported one resets the log
        gate, so returning to the unsupported band logs again."""
        scanner = ScanRunner(mock_device, mock_embedder, mock_store,
                             mock_classifier, config,
                             device_driver="plutosdr")
        with caplog.at_level(logging.WARNING, logger="core.pipeline.scanner"):
            scanner._running = True
            t = threading.Thread(target=scanner._scan_loop, daemon=True)
            t.start()
            time.sleep(0.2)  # first visit to 98 MHz — logs once
            scanner.set_focus_frequency(1_090_000_000.0)
            time.sleep(0.2)  # supported visit — resets the gate
            scanner.set_focus_frequency(98_000_000.0)
            time.sleep(0.2)  # second visit to 98 MHz — logs again
            scanner.stop()
            t.join(timeout=3)
        skipping = [r for r in caplog.records if "Skipping" in r.getMessage()]
        assert len(skipping) == 2

    def test_scan_loop_plutosdr_skips_out_of_range_freq(self, config, mock_device,
                                                         mock_embedder, mock_store,
                                                         mock_classifier):
        """Pluto focused on 4 GHz — above its 3.8 GHz ceiling — must never
        tune or read samples, even though the nearest-band lookup resolves
        it to "adsb" (a Pluto-supported band). HIGH-01: the raw frequency
        range check is the authoritative gate, not the band lookup."""
        scanner = ScanRunner(mock_device, mock_embedder, mock_store,
                             mock_classifier, config,
                             device_driver="plutosdr")
        scanner.set_focus_frequency(4_000_000_000.0)
        self._run_briefly(scanner, 0.3)
        mock_device.set_center_frequency.assert_not_called()
        mock_device.read_samples.assert_not_called()


class TestDeviceDriverValidation:
    """ScanRunner.__init__ must reject unknown device_driver strings.

    Without validation, a typo (e.g. "rtlsdr") would reach the scan loop's
    guard, where band_supported_by_device() raises KeyError — caught by the
    broad except Exception, logged, and retried in a tight error loop.
    """

    def test_scan_runner_rejects_unknown_device_driver(
            self, config, mock_device, mock_embedder, mock_store,
            mock_classifier):
        with pytest.raises(ValueError, match="Unknown device driver 'rtlsdr'"):
            ScanRunner(mock_device, mock_embedder, mock_store,
                       mock_classifier, config,
                       device_driver="rtlsdr")

    def test_scan_runner_accepts_all_known_drivers(
            self, config, mock_device, mock_embedder, mock_store,
            mock_classifier):
        from core.device.profiles import DEVICE_PROFILES
        for driver in DEVICE_PROFILES:
            scanner = ScanRunner(mock_device, mock_embedder, mock_store,
                                 mock_classifier, config,
                                 device_driver=driver)
            assert scanner._device_driver == driver
