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
from core.pipeline import features
from core.pipeline.scan_result import ScanResult
from core.pipeline.scanner import ScanRunner, _should_fire_trigger
import dashboard.shared_state as shared_state
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
    # Phase 41: the AI loop calls is_noise_shaped() before classify(). A bare
    # MagicMock attribute is truthy, which would silently route every test
    # through the deterministic noise gate. Default to False so existing
    # tests exercise the query+classify path; the noise-gate tests set it
    # to True explicitly.
    c.is_noise_shaped.return_value = False
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


class TestScanLoopTraceKey:
    """_scan_loop must forward the band's fingerprint_trace_key to
    fingerprint_spectrum() (Phase 65, Finding B).

    ADS-B is a pulsed/bursty signal (~120 us squitters at ~1% duty
    cycle); fingerprinting the averaged trace loses ~9.6 dB of measured
    SNR, so the adsb band profile carries
    fingerprint_trace_key="psd_max_hold_db". Continuous-signal bands
    must keep the 'psd_db' default.
    """

    def _run_loop_and_capture_trace_key(self, scanner, band_key, freq_hz):
        """Drive the scan loop briefly on freq_hz with current_band set to
        BAND_PROFILES[band_key] and return the trace_key kwarg that was
        forwarded to fingerprint_spectrum()."""
        with shared_state.current_band_lock:
            original_band = dict(shared_state.current_band)
            shared_state.current_band.clear()
            shared_state.current_band.update(shared_state.BAND_PROFILES[band_key])

        captured = {}

        def capture_fn(psd_result, **kwargs):
            captured["trace_key"] = kwargs.get("trace_key")
            # Minimal valid fingerprint so the embedder does not choke.
            return {
                "center_freq_hz": freq_hz,
                "peak_freq_hz": freq_hz,
                "peak_power_db": -10.0,
                "noise_floor_db": -80.0,
                "snr_db": 70.0,
                "bandwidth_hz": 200_000,
                "occupied_bins": 200,
                "spectral_flatness": 0.5,
                "signal_threshold_db": 3.0,
                "snr_margin_db": 46.0,
                "peak_bin_power_db": -10.0,
            }

        try:
            scanner.set_focus_frequency(freq_hz)
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
            return captured.get("trace_key")
        finally:
            with shared_state.current_band_lock:
                shared_state.current_band.clear()
                shared_state.current_band.update(original_band)

    def test_adsb_band_passes_psd_max_hold_trace_key(self, scanner):
        """On the adsb band the scan loop must fingerprint the max-hold
        trace, using the real BAND_PROFILES entry so the test tracks the
        configured value rather than a hardcoded string."""
        expected = shared_state.BAND_PROFILES["adsb"]["fingerprint_trace_key"]
        assert expected == "psd_max_hold_db"  # sanity: the key exists
        trace_key = self._run_loop_and_capture_trace_key(
            scanner, "adsb", 1_090_000_000.0
        )
        assert trace_key == expected

    def test_non_adsb_band_passes_default_psd_db_trace_key(self, scanner):
        """Bands without fingerprint_trace_key must keep the 'psd_db'
        default — no silent spread of max-hold to continuous-signal
        bands. fm_broadcast covers the HackRF path; ism covers a
        Pluto-supported band."""
        assert "fingerprint_trace_key" not in shared_state.BAND_PROFILES["fm_broadcast"]
        assert "fingerprint_trace_key" not in shared_state.BAND_PROFILES["ism"]
        assert self._run_loop_and_capture_trace_key(
            scanner, "fm_broadcast", 98_000_000.0
        ) == "psd_db"
        assert self._run_loop_and_capture_trace_key(
            scanner, "ism", 915_000_000.0
        ) == "psd_db"


class TestAiLoopNoiseGate:
    """Tests for the pre-LLM deterministic noise gate in _ai_loop (Phase 41).

    When is_noise_shaped() returns True for a fingerprint, the AI loop must
    emit a deterministic "noise" ScanResult and skip BOTH the ChromaDB query
    and the LLM call. When it returns False, the existing query+classify
    path must run unchanged.
    """

    @staticmethod
    def _noise_result() -> ClassificationResult:
        """The deterministic verdict the gate emits for noise-shaped scans."""
        return ClassificationResult(
            signal_type="noise",
            confidence="low",
            confidence_score=0.9,
            novel=False,
            reasoning="Deterministic noise gate: LLM classification skipped.",
            au_legal_status="legal_rx",
            frequency_band="unknown",
            raw_response="",
        )

    @staticmethod
    def _queue_noise_item(scanner):
        """Pre-fill the queue with a single noise-shaped scan item."""
        scanner._queue.put_nowait({
            "freq_hz": 98_000_000.0,
            "fingerprint": {
                "center_freq_hz": 98_000_000.0,
                "occupied_bins": 0,
                "spectral_flatness": 0.99,
            },
            "vector": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.3],
        })

    def _drive_ai_loop(self, scanner):
        """Run _ai_loop briefly in a daemon thread and stop it."""
        t = threading.Thread(target=scanner._ai_loop, daemon=True)
        t.start()
        time.sleep(0.1)
        scanner.stop()
        t.join(timeout=3)

    def test_noise_shaped_skips_chroma_query(
        self, scanner, mock_store, mock_classifier
    ):
        """A noise-shaped fingerprint skips the ChromaDB query and the LLM
        call, but still emits a ScanResult with signal_type "noise"."""
        mock_classifier.is_noise_shaped.return_value = True
        mock_classifier.classify_noise_deterministic.return_value = (
            self._noise_result()
        )
        scanner._running = True
        self._queue_noise_item(scanner)

        with patch.object(scanner, "_emit_result") as mock_emit:
            self._drive_ai_loop(scanner)

            mock_store.query.assert_not_called()
            mock_classifier.classify.assert_not_called()
            mock_emit.assert_called_once()
            emitted = mock_emit.call_args[0][0]
            assert isinstance(emitted, ScanResult)
            assert emitted.classification.signal_type == "noise"

    def test_noise_shaped_does_not_increment_llm_call_count(
        self, scanner, mock_classifier
    ):
        """No LLM call was made, so _llm_call_count stays at 0."""
        mock_classifier.is_noise_shaped.return_value = True
        mock_classifier.classify_noise_deterministic.return_value = (
            self._noise_result()
        )
        scanner._running = True
        self._queue_noise_item(scanner)

        with patch.object(scanner, "_emit_result"):
            self._drive_ai_loop(scanner)

        assert scanner._llm_call_count == 0

    def test_noise_shaped_emits_chroma_distance_none(
        self, scanner, mock_classifier
    ):
        """chroma_distance must be None (no query ran), not 0.0 — an honest
        null, not a fake perfect match."""
        mock_classifier.is_noise_shaped.return_value = True
        mock_classifier.classify_noise_deterministic.return_value = (
            self._noise_result()
        )
        scanner._running = True
        self._queue_noise_item(scanner)

        with patch.object(scanner, "_emit_result") as mock_emit:
            self._drive_ai_loop(scanner)

            mock_emit.assert_called_once()
            emitted = mock_emit.call_args[0][0]
            assert emitted.fingerprint["chroma_distance"] is None

    def test_real_signal_path_unchanged(
        self, scanner, mock_store, mock_classifier
    ):
        """When is_noise_shaped returns False, the existing query+classify
        path runs unchanged."""
        mock_classifier.is_noise_shaped.return_value = False
        scanner._running = True
        scanner._queue.put_nowait({
            "freq_hz": 98_000_000.0,
            "fingerprint": {"center_freq_hz": 98_000_000.0},
            "vector": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.3],
        })

        with patch.object(scanner, "_emit_result") as mock_emit:
            self._drive_ai_loop(scanner)

            mock_store.query.assert_called_once()
            mock_classifier.classify.assert_called_once()
            mock_emit.assert_called_once()


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


class TestScanLoopRetuneDiscard:
    """Tests for the Phase 44 discard read after a retune.

    The first read after a retune would return the PLL settling transient,
    so the scan loop performs a throwaway discard read immediately after
    set_center_frequency — inside the retune conditional, so it cannot
    fire when the frequency is unchanged.
    """

    def test_discard_read_immediately_follows_retune(self, scanner, mock_device):
        """T6: the first set_center_frequency must be followed directly by
        a read_samples (the discard), with nothing in between."""
        manager = MagicMock()
        manager.attach_mock(mock_device.set_center_frequency, "set_center_frequency")
        manager.attach_mock(mock_device.read_samples, "read_samples")
        t = threading.Thread(target=scanner.run, daemon=True)
        t.start()
        time.sleep(0.3)
        scanner.stop()
        t.join(timeout=3)
        calls = [c[0] for c in manager.mock_calls]
        # First retune must be immediately followed by a discard read
        assert "set_center_frequency" in calls, "set_center_frequency was never called"
        retune_idx = calls.index("set_center_frequency")
        # The very next call must be read_samples (the discard)
        assert calls[retune_idx + 1] == "read_samples", (
            f"Expected discard read_samples immediately after retune, "
            f"but got: {calls[retune_idx:retune_idx+3]}"
        )

    def test_no_discard_read_when_freq_unchanged(self, scanner, mock_device):
        """T7: across many steady-state cycles there is exactly ONE
        read_samples immediately preceded by set_center_frequency — the
        single discard after the single initial retune."""
        manager = MagicMock()
        manager.attach_mock(mock_device.set_center_frequency, "set_center_frequency")
        manager.attach_mock(mock_device.read_samples, "read_samples")
        t = threading.Thread(target=scanner.run, daemon=True)
        t.start()
        time.sleep(0.5)  # many scan cycles at dwell_time=0.01s
        scanner.stop()
        t.join(timeout=3)
        calls = [c[0] for c in manager.mock_calls]
        # Count the number of "read_samples immediately after set_center_frequency"
        retune_then_read = sum(
            1 for i in range(len(calls) - 1)
            if calls[i] == "set_center_frequency" and calls[i + 1] == "read_samples"
        )
        assert retune_then_read == 1, (
            f"Expected exactly 1 discard read (the one after the single retune), "
            f"but found {retune_then_read} read_samples calls preceded by set_center_frequency"
        )


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


class TestEmitResultThrottle:
    """Tests for the per-frequency unchanged-verdict throttle in
    _emit_result() (Phase 43).

    Three emit rules under test:
      a) First emit for a frequency always passes.
      b) A CHANGED signal_type at a frequency always emits immediately.
      c) An UNCHANGED verdict (same freq, same signal_type) is suppressed
         until unchanged_emit_interval_sec has elapsed.

    All tests patch time.monotonic — never time.sleep — to control the
    clock deterministically.
    """

    @staticmethod
    def _make_result(freq_hz, signal_type="fm_broadcast"):
        """Build a minimal ScanResult for a given frequency and verdict."""
        return ScanResult(
            timestamp="2026-07-25T12:00:00",
            center_freq_hz=freq_hz,
            fingerprint={},
            classification=ClassificationResult(
                signal_type=signal_type,
                confidence="high",
                confidence_score=0.95,
                novel=False,
                reasoning="test",
                au_legal_status="legal_rx",
                frequency_band="fm_broadcast_band",
                raw_response="{}",
            ),
            psd_db=None,
        )

    @staticmethod
    def _reset(scanner):
        """Fresh throttle state + observable broadcast mock per test."""
        scanner._last_emit_by_freq = {}
        scanner._broadcast_fn = MagicMock()
        return scanner

    def test_first_emit_for_freq_always_passes(self, scanner):
        scanner = self._reset(scanner)
        result = self._make_result(98_000_000.0)
        scanner._emit_result(result)
        scanner._broadcast_fn.assert_called_once_with(result)

    def test_identical_verdict_within_interval_suppressed(self, scanner, capsys):
        scanner = self._reset(scanner)
        interval = scanner._config.unchanged_emit_interval_sec
        clock = [1000.0]
        with patch("time.monotonic", side_effect=lambda: clock[0]):
            scanner._emit_result(self._make_result(98_000_000.0, "fm_broadcast"))
            capsys.readouterr()  # drain the first emit's terminal output
            clock[0] += interval / 2  # still inside the interval
            scanner._emit_result(self._make_result(98_000_000.0, "fm_broadcast"))
        scanner._broadcast_fn.assert_called_once()
        assert capsys.readouterr().out == ""

    def test_identical_verdict_after_interval_emits(self, scanner):
        scanner = self._reset(scanner)
        interval = scanner._config.unchanged_emit_interval_sec
        clock = [1000.0]
        with patch("time.monotonic", side_effect=lambda: clock[0]):
            scanner._emit_result(self._make_result(98_000_000.0, "fm_broadcast"))
            clock[0] += interval  # interval fully elapsed
            scanner._emit_result(self._make_result(98_000_000.0, "fm_broadcast"))
        assert scanner._broadcast_fn.call_count == 2

    def test_changed_signal_type_emits_immediately_within_window(self, scanner):
        scanner = self._reset(scanner)
        interval = scanner._config.unchanged_emit_interval_sec
        clock = [1000.0]
        with patch("time.monotonic", side_effect=lambda: clock[0]):
            scanner._emit_result(self._make_result(98_000_000.0, "noise"))
            clock[0] += interval / 100  # barely advanced — well inside window
            # Rule b: a changed verdict always wins over the interval gate.
            scanner._emit_result(self._make_result(98_000_000.0, "fm_broadcast"))
        assert scanner._broadcast_fn.call_count == 2

    def test_per_frequency_independence(self, scanner):
        scanner = self._reset(scanner)
        interval = scanner._config.unchanged_emit_interval_sec
        clock = [1000.0]
        with patch("time.monotonic", side_effect=lambda: clock[0]):
            scanner._emit_result(self._make_result(98_000_000.0, "fm_broadcast"))
            clock[0] += interval / 2
            # Second emit for freq A is suppressed (same verdict, in window)...
            scanner._emit_result(self._make_result(98_000_000.0, "fm_broadcast"))
            # ...but freq B's first emit must not be blocked by A's throttle.
            result_b = self._make_result(145_175_000.0, "aprs")
            scanner._emit_result(result_b)
        assert scanner._broadcast_fn.call_count == 2
        scanner._broadcast_fn.assert_called_with(result_b)

    def test_verdict_flapping_back_emits_on_each_change(self, scanner):
        scanner = self._reset(scanner)
        clock = [1000.0]
        with patch("time.monotonic", side_effect=lambda: clock[0]):
            # noise -> fm_broadcast -> noise at the same freq: every step is
            # a change relative to the previous emit, so all three must emit.
            scanner._emit_result(self._make_result(98_000_000.0, "noise"))
            clock[0] += 0.001
            scanner._emit_result(self._make_result(98_000_000.0, "fm_broadcast"))
            clock[0] += 0.001
            scanner._emit_result(self._make_result(98_000_000.0, "noise"))
        assert scanner._broadcast_fn.call_count == 3

    def test_suppressed_emit_does_not_print_to_terminal(self, scanner, capsys):
        scanner = self._reset(scanner)
        interval = scanner._config.unchanged_emit_interval_sec
        clock = [1000.0]
        with patch("time.monotonic", side_effect=lambda: clock[0]):
            scanner._emit_result(self._make_result(98_000_000.0, "fm_broadcast"))
            first_out = capsys.readouterr().out
            assert first_out != ""  # sanity: the first emit does print
            clock[0] += interval / 2
            scanner._emit_result(self._make_result(98_000_000.0, "fm_broadcast"))
            assert capsys.readouterr().out == ""


class TestShouldFireTrigger:
    """Unit tests for the _should_fire_trigger edge-detector (Phase 63).

    The fire condition is prev_snr < threshold <= current_snr: a rising
    edge across the band's signal threshold. The asymmetry (strict on
    the previous side, inclusive on the current side) is the re-arm
    contract: once a reading at or above threshold is recorded as
    prev_snr, the trigger cannot fire again until SNR drops below
    threshold and rises back.
    """

    def test_prev_none_never_fires(self):
        """First cycle after startup has no previous reading - no edge."""
        assert _should_fire_trigger(None, 5.0, 3.0) is False

    def test_crossing_fires(self):
        assert _should_fire_trigger(2.0, 4.0, 3.0) is True

    def test_exact_threshold_counts_as_fire(self):
        """Less-than-or-equal on the current side: landing exactly on the
        threshold counts as a crossing."""
        assert _should_fire_trigger(2.999, 3.0, 3.0) is True

    def test_staying_above_does_not_fire(self):
        """A continuous strong signal produces one capture at the rising
        edge, not one per cycle."""
        assert _should_fire_trigger(4.0, 5.0, 3.0) is False

    def test_rearm_after_drop_below_threshold(self):
        """Dropping below and crossing again re-arms and fires."""
        # Still above threshold on the way: no fire while above.
        assert _should_fire_trigger(4.0, 2.0, 3.0) is False
        # Now prev is below threshold; rising back across fires.
        assert _should_fire_trigger(2.0, 3.5, 3.0) is True

    def test_current_none_never_fires(self):
        """A fingerprint that produced no SNR reading cannot fire."""
        assert _should_fire_trigger(2.0, None, 3.0) is False

    def test_threshold_none_never_fires(self):
        """A band profile missing signal_threshold_db cannot fire
        (defensive - all current profiles define it)."""
        assert _should_fire_trigger(2.0, 5.0, None) is False

    def test_threshold_not_a_number_never_fires(self):
        """Defensive: a non-numeric threshold is not a usable edge."""
        assert _should_fire_trigger(2.0, 5.0, "3.0") is False

    def test_staying_below_does_not_fire(self):
        assert _should_fire_trigger(1.0, 2.0, 3.0) is False

    def test_dropping_from_above_to_below_does_not_fire(self):
        assert _should_fire_trigger(5.0, 1.0, 3.0) is False


class TestScanLoopCaptureTrigger:
    """Integration tests for the SNR-edge auto-capture trigger inside
    _scan_loop() (Phase 63).

    Drives the real scan loop with a mocked device and a patched
    fingerprint_spectrum that returns a controlled SNR sequence (first
    cycle below the fm_broadcast threshold of 21.0 dB, all subsequent
    cycles above it), with save_capture patched out. Asserts the
    crossing fires exactly one save, and only when the band is armed.

    The trigger state and current_band are module-level in
    dashboard.shared_state, so the autouse fixture snapshots and
    restores them around every test.
    """

    @pytest.fixture(autouse=True)
    def reset_shared_state(self):
        with shared_state.trigger_state_lock:
            saved_armed = dict(shared_state.trigger_armed)
            saved_snr = dict(shared_state._trigger_last_snr)
        with shared_state.current_band_lock:
            saved_band = dict(shared_state.current_band)
            shared_state.current_band.clear()
            shared_state.current_band.update(
                shared_state.BAND_PROFILES["fm_broadcast"]
            )
        yield
        with shared_state.trigger_state_lock:
            shared_state.trigger_armed.clear()
            shared_state.trigger_armed.update(saved_armed)
            shared_state._trigger_last_snr.clear()
            shared_state._trigger_last_snr.update(saved_snr)
        with shared_state.current_band_lock:
            shared_state.current_band.clear()
            shared_state.current_band.update(saved_band)

    @staticmethod
    def _fingerprint(snr_db):
        """Minimal fingerprint dict carrying a controlled snr_db."""
        return {
            "center_freq_hz": 98_000_000,
            "peak_freq_hz": 98_000_000,
            "peak_power_db": -10.0,
            "noise_floor_db": -80.0,
            "snr_db": snr_db,
            "bandwidth_hz": 200_000,
            "occupied_bins": 200,
            "spectral_flatness": 0.5,
        }

    def _drive_scan_loop(self, scanner, low_snr, high_snr, seconds=0.4):
        """Run _scan_loop briefly: first cycle returns low_snr, every
        later cycle returns high_snr (fm_broadcast threshold is 21.0 dB,
        so low=10.0 / high=25.0 describes a single rising edge)."""
        low = self._fingerprint(low_snr)
        high = self._fingerprint(high_snr)
        calls = {"n": 0}

        def fake_fingerprint(psd, **kwargs):
            calls["n"] += 1
            return low if calls["n"] == 1 else high

        with patch(
            "core.pipeline.scanner.features.fingerprint_spectrum",
            side_effect=fake_fingerprint,
        ):
            scanner._running = True
            t = threading.Thread(target=scanner._scan_loop, daemon=True)
            t.start()
            time.sleep(seconds)
            scanner.stop()
            t.join(timeout=3)
        assert calls["n"] >= 2, "scan loop did not complete enough cycles"

    def test_armed_band_saves_once_on_snr_crossing(self, scanner):
        """Armed band, SNR crossing 10 -> 25 dB against the 21 dB
        fm_broadcast threshold: save_capture fires exactly once (rising
        edge only, not once per cycle above threshold)."""
        shared_state.set_trigger_armed("fm_broadcast", True)
        with patch("core.pipeline.scanner.save_capture") as mock_save:
            self._drive_scan_loop(scanner, low_snr=10.0, high_snr=25.0)
        assert mock_save.call_count == 1
        args, kwargs = mock_save.call_args
        # Raw samples passed positionally; everything else by keyword.
        assert len(args) == 1
        assert kwargs["freq_hz"] == 98_000_000.0
        assert kwargs["sample_rate_hz"] == 2_000_000
        assert kwargs["device"] == "hackrf"
        assert kwargs["fingerprint"]["snr_db"] == 25.0
        # bandwidth_hz deliberately omitted: HackRF has no settable RF
        # filter and a live-loop capture has no declared width.
        assert "bandwidth_hz" not in kwargs

    def test_unarmed_band_never_saves(self, scanner):
        """Same SNR crossing, trigger not armed: save_capture must not
        be called."""
        with patch("core.pipeline.scanner.save_capture") as mock_save:
            self._drive_scan_loop(scanner, low_snr=10.0, high_snr=25.0)
        mock_save.assert_not_called()

    def test_other_armed_band_does_not_fire_for_this_freq(self, scanner):
        """Arming adsb must not cause a save while scanning 98 MHz
        (fm_broadcast): the armed check is per-band."""
        shared_state.set_trigger_armed("adsb", True)
        with patch("core.pipeline.scanner.save_capture") as mock_save:
            self._drive_scan_loop(scanner, low_snr=10.0, high_snr=25.0)
        mock_save.assert_not_called()

    def test_save_failure_does_not_kill_scan_loop(self, scanner):
        """A disk-full / SigMF write failure is logged and swallowed;
        the scan loop keeps cycling afterwards."""
        shared_state.set_trigger_armed("fm_broadcast", True)
        with patch(
            "core.pipeline.scanner.save_capture",
            side_effect=OSError("disk full"),
        ) as mock_save:
            self._drive_scan_loop(scanner, low_snr=10.0, high_snr=25.0)
        assert mock_save.call_count == 1
        # The loop survived the failure and kept scanning.
        assert scanner._scan_count >= 1

    def test_last_snr_recorded_each_cycle(self, scanner):
        """The per-band last-SNR state tracks the latest reading, which
        is what re-arms the edge detector after the signal drops."""
        shared_state.set_trigger_armed("fm_broadcast", True)
        with patch("core.pipeline.scanner.save_capture"):
            self._drive_scan_loop(scanner, low_snr=10.0, high_snr=25.0)
        assert shared_state.get_last_trigger_snr("fm_broadcast") == 25.0

    def test_missing_threshold_key_uses_shared_fallback_on_both_paths(
        self, scanner
    ):
        """EDGE-03: a current_band dict missing signal_threshold_db must
        resolve to features.SIGNAL_THRESHOLD_DB on BOTH the fingerprinting
        path and the trigger-check path. The scan loop computes one
        `threshold` local with the fallback and reuses it for both, so
        the two paths can never diverge on a band dict lacking the key.
        """
        with shared_state.current_band_lock:
            shared_state.current_band.clear()
            band = dict(shared_state.BAND_PROFILES["fm_broadcast"])
            band.pop("signal_threshold_db")
            shared_state.current_band.update(band)
        shared_state.set_trigger_armed("fm_broadcast", True)
        captured = {}

        def fake_fingerprint(psd, **kwargs):
            captured.setdefault(
                "fingerprint_threshold", kwargs.get("signal_threshold_db")
            )
            return self._fingerprint(10.0)

        def fake_should_fire(prev_snr, current_snr, threshold_db):
            captured.setdefault("trigger_threshold", threshold_db)
            return False

        with patch(
            "core.pipeline.scanner.features.fingerprint_spectrum",
            side_effect=fake_fingerprint,
        ), patch(
            "core.pipeline.scanner._should_fire_trigger",
            side_effect=fake_should_fire,
        ), patch("core.pipeline.scanner.save_capture"):
            scanner._running = True
            t = threading.Thread(target=scanner._scan_loop, daemon=True)
            t.start()
            time.sleep(0.4)
            scanner.stop()
            t.join(timeout=3)

        # Both paths ran (armed fm_broadcast at 98 MHz) and both saw the
        # module-level fallback, not a divergent None from a bare .get().
        assert captured["fingerprint_threshold"] == (
            features.SIGNAL_THRESHOLD_DB
        )
        assert captured["trigger_threshold"] == features.SIGNAL_THRESHOLD_DB


class TestCaptureNow:
    """Tests for the manual capture cross-thread handoff (this build).

    capture_now() is called from the Flask request handler thread; the
    scan loop services the request on its next cycle using the samples
    it has already read (no second device open). These tests drive the
    real scan loop with a mocked device and a patched save_capture /
    fingerprint_spectrum, mirroring the TestScanLoopCaptureTrigger
    pattern above.

    The trigger state and current_band are module-level in
    dashboard.shared_state, so the autouse fixture snapshots and
    restores them around every test, and explicitly disarms every band
    so the Phase 63 auto-trigger can never add a stray save_capture
    call to the assertions.
    """

    @pytest.fixture(autouse=True)
    def reset_shared_state(self):
        with shared_state.trigger_state_lock:
            saved_armed = dict(shared_state.trigger_armed)
            saved_snr = dict(shared_state._trigger_last_snr)
            shared_state.trigger_armed.clear()
            shared_state._trigger_last_snr.clear()
        with shared_state.current_band_lock:
            saved_band = dict(shared_state.current_band)
            shared_state.current_band.clear()
            shared_state.current_band.update(
                shared_state.BAND_PROFILES["fm_broadcast"]
            )
        yield
        with shared_state.trigger_state_lock:
            shared_state.trigger_armed.clear()
            shared_state.trigger_armed.update(saved_armed)
            shared_state._trigger_last_snr.clear()
            shared_state._trigger_last_snr.update(saved_snr)
        with shared_state.current_band_lock:
            shared_state.current_band.clear()
            shared_state.current_band.update(saved_band)

    @staticmethod
    def _fingerprint():
        """Fingerprint dict carrying all seven _FINGERPRINT_METADATA_KEYS
        measurement fields (plus one extra internal key, to prove the
        result dict is filtered to the allowlist). Phase 67 adds
        `is_burst` to the same dict so the manual-capture ok response
        can thread the burst detection flag through as a top-level
        sibling of the fingerprint sub-dict."""
        return {
            "center_freq_hz": 98_000_000,
            "peak_freq_hz": 98_100_000,
            "peak_power_db": -12.5,
            "noise_floor_db": -78.0,
            "snr_db": 65.5,
            "bandwidth_hz": 200_000,
            "occupied_bins": 205,
            "spectral_flatness": 0.42,
            "snr_margin_db": 44.5,
            "is_burst": False,
        }

    def test_capture_now_timeout_when_loop_not_running(self, scanner):
        """With the scan loop stopped, capture_now must return a
        structured timeout promptly (not hang), must not call
        save_capture, and must clear the request flag so a late-starting
        cycle cannot service an abandoned request."""
        with patch("core.pipeline.scanner.save_capture") as mock_save:
            start = time.monotonic()
            result = scanner.capture_now(timeout_sec=0.05)
            elapsed = time.monotonic() - start
        assert result == {"status": "timeout"}
        assert elapsed < 1.0
        mock_save.assert_not_called()
        assert not scanner._capture_request_event.is_set()

    def test_capture_now_success_returns_expected_keys(self, scanner):
        """A serviced request returns status ok, the saved file path as a
        string, and a fingerprint filtered to exactly the seven
        _FINGERPRINT_METADATA_KEYS fields with the loop's values."""
        from core.pipeline.capture import _FINGERPRINT_METADATA_KEYS
        from pathlib import Path

        fingerprint = self._fingerprint()
        sentinel = Path("/tmp/sentinel.sigmf-meta")
        with patch(
            "core.pipeline.scanner.features.fingerprint_spectrum",
            return_value=fingerprint,
        ), patch(
            "core.pipeline.scanner.save_capture", return_value=sentinel
        ) as mock_save:
            scanner._running = True
            t = threading.Thread(target=scanner._scan_loop, daemon=True)
            t.start()
            result = scanner.capture_now(timeout_sec=2.0)
            scanner.stop()
            t.join(timeout=3)

        assert mock_save.call_count == 1
        assert result["status"] == "ok"
        assert result["file"] == str(sentinel)
        assert isinstance(result["file"], str)
        assert set(result["fingerprint"].keys()) == set(
            _FINGERPRINT_METADATA_KEYS
        )
        for key in _FINGERPRINT_METADATA_KEYS:
            assert result["fingerprint"][key] == fingerprint[key]
        # Phase 67: `is_burst` is a top-level sibling of `fingerprint`,
        # NOT inside the filtered sub-dict. _FINGERPRINT_METADATA_KEYS
        # deliberately excludes it so it is never persisted to SigMF.
        assert result["is_burst"] is False
        assert "is_burst" not in result["fingerprint"]

    def test_capture_now_error_surfaces_cause(self, scanner):
        """A save_capture failure (e.g. disk full) surfaces as
        status error with the exception message as cause, and the scan
        loop survives and keeps cycling."""
        with patch(
            "core.pipeline.scanner.features.fingerprint_spectrum",
            return_value=self._fingerprint(),
        ), patch(
            "core.pipeline.scanner.save_capture",
            side_effect=OSError("disk full"),
        ) as mock_save:
            scanner._running = True
            t = threading.Thread(target=scanner._scan_loop, daemon=True)
            t.start()
            result = scanner.capture_now(timeout_sec=2.0)
            scanner.stop()
            t.join(timeout=3)

        assert mock_save.call_count == 1
        assert result == {"status": "error", "cause": "disk full"}
        # The loop survived the failure and kept scanning.
        assert scanner._scan_count >= 1

    def test_scan_loop_services_manual_request_flag(self, scanner, mock_device):
        """Integration: setting the request event from the caller thread
        is serviced inside the scan loop with the in-flight samples,
        the focus frequency, the device driver key, and this cycle's
        fingerprint; the result slot carries the ok structure."""
        from pathlib import Path

        fingerprint = self._fingerprint()
        with patch(
            "core.pipeline.scanner.features.fingerprint_spectrum",
            return_value=fingerprint,
        ), patch(
            "core.pipeline.scanner.save_capture",
            return_value=Path("/tmp/integration.sigmf-meta"),
        ) as mock_save:
            scanner._running = True
            t = threading.Thread(target=scanner._scan_loop, daemon=True)
            t.start()
            scanner._capture_request_event.set()
            serviced = scanner._capture_result_event.wait(timeout=2.0)
            scanner.stop()
            t.join(timeout=3)

        assert serviced, "scan loop did not service the manual capture request"
        mock_save.assert_called_once()
        args, kwargs = mock_save.call_args
        # Raw in-flight samples passed positionally; the rest by keyword.
        assert len(args) == 1
        assert args[0] is mock_device.read_samples.return_value
        assert kwargs["freq_hz"] == 98_000_000.0
        assert kwargs["sample_rate_hz"] == 2_000_000
        assert kwargs["device"] == "hackrf"
        assert kwargs["fingerprint"] is fingerprint
        assert "bandwidth_hz" not in kwargs
        with scanner._capture_result_lock:
            result = scanner._capture_result
        assert result is not None
        assert result["status"] == "ok"
        assert result["file"] == "/tmp/integration.sigmf-meta"
        assert result["fingerprint"]["occupied_bins"] == 205
        # Phase 67: `is_burst` rides on top-level, separate from the
        # fingerprint sub-dict.
        assert result["is_burst"] is False
        assert "is_burst" not in result["fingerprint"]

    def test_capture_now_ok_response_is_burst_is_sibling_of_fingerprint(
        self, scanner
    ):
        """Phase 67 contract: when the fingerprint carries
        `is_burst=True`, the manual-capture ok response surfaces it as a
        top-level sibling of `fingerprint` (NOT inside the fingerprint
        sub-dict). The fingerprint sub-dict shape stays exactly the
        seven _FINGERPRINT_METADATA_KEYS fields, so the saved SigMF
        metadata is unaffected by the new top-level key.

        Uses a 5-bin / `is_burst=True` fingerprint — a deliberately
        narrow reading that the dashboard verdict would label as burst
        instead of narrow — so the test confirms the full thread: the
        scan loop reads the burst flag from fingerprint_spectrum(), the
        ok response carries it on top-level, and the filtered fingerprint
        sub-dict still has the original occupied_bins value.
        """
        from pathlib import Path

        fingerprint = self._fingerprint()
        fingerprint["occupied_bins"] = 5
        fingerprint["is_burst"] = True
        with patch(
            "core.pipeline.scanner.features.fingerprint_spectrum",
            return_value=fingerprint,
        ), patch(
            "core.pipeline.scanner.save_capture",
            return_value=Path("/tmp/burst.sigmf-meta"),
        ) as mock_save:
            scanner._running = True
            t = threading.Thread(target=scanner._scan_loop, daemon=True)
            t.start()
            result = scanner.capture_now(timeout_sec=2.0)
            scanner.stop()
            t.join(timeout=3)

        assert mock_save.call_count == 1
        assert result["status"] == "ok"
        # The burst flag rides on top-level.
        assert result["is_burst"] is True
        # It is NOT inside the fingerprint sub-dict — that key list is
        # the seven _FINGERPRINT_METADATA_KEYS, which deliberately
        # excludes detection-pipeline state.
        assert "is_burst" not in result["fingerprint"]
        # And the original occupied_bins value still rides through the
        # fingerprint sub-dict unchanged.
        assert result["fingerprint"]["occupied_bins"] == 5
