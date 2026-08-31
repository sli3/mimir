"""
tests/core/test_demo_producer.py
Mimir RF Scanner — Phase 76 Demo Producer Tests

PURPOSE
-------
Tests for ``DemoProducer`` in ``core/pipeline/demo_producer.py``. Proves
it loads SigMF files, fingerprints chunks, embeds them, annotates them
with stable demo keys, and pushes the right item shape into the scanner
queue at a paced cadence. All tests build real SigMF files in ``tmp_path``
— no hardware required.

Run with:
    uv run pytest tests/core/test_demo_producer.py -v
"""

from __future__ import annotations

import queue
import sys
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.config.loader import MimirConfig
from core.pipeline.capture import save_capture, save_recording
from core.pipeline.demo_producer import DemoProducer
from core.pipeline.fft import compute_psd
from core.pipeline.features import fingerprint_spectrum
from core.pipeline.replay import ReplayFileError
from dashboard.shared_state import BAND_PROFILES
from embeddings.embedder import SpectrumEmbedder


_FREQ_HZ = 98_000_000
_SAMPLE_RATE_HZ = 2_000_000


def _make_samples(num_samples: int = 16_384, seed: int = 42) -> np.ndarray:
    """Reproducible synthetic noise IQ."""
    rng = np.random.default_rng(seed)
    return (
        rng.standard_normal(num_samples) + 1j * rng.standard_normal(num_samples)
    ).astype(np.complex64)


def _expected_fingerprint(samples, freq_hz, sample_rate_hz, band_key):
    """Fingerprint computed with the band profile parameterisation."""
    profile = BAND_PROFILES[band_key]
    psd_result = compute_psd(samples, sample_rate_hz, freq_hz)
    return fingerprint_spectrum(
        psd_result,
        signal_threshold_db=profile.get("signal_threshold_db"),
        crop_half_width_hz=profile.get("crop_half_width_hz"),
        burst_use_wide_window=profile.get("burst_use_wide_window", False),
        trace_key=profile.get("fingerprint_trace_key", "psd_db"),
    )


def _build_one_shot(tmp_path: Path, freq_hz: float = _FREQ_HZ) -> Path:
    """Write a real one-shot SigMF capture at 98 MHz."""
    samples = _make_samples(16_384)
    fingerprint = _expected_fingerprint(
        samples, freq_hz, _SAMPLE_RATE_HZ, "fm_broadcast"
    )
    return save_capture(
        samples,
        freq_hz=freq_hz,
        sample_rate_hz=_SAMPLE_RATE_HZ,
        output_dir=tmp_path,
        fingerprint=fingerprint,
    )


def _build_recording(
    tmp_path: Path, chunks: int = 2, freq_hz: float = _FREQ_HZ
) -> Path:
    """Write a real Record-mode SigMF capture with ``chunks`` cycles."""
    samples = _make_samples(chunks * 8192)
    sequence = []
    start = 0
    for _ in range(chunks):
        chunk_samples = samples[start : start + 8192]
        fingerprint = _expected_fingerprint(
            chunk_samples, freq_hz, _SAMPLE_RATE_HZ, "fm_broadcast"
        )
        sequence.append({
            **fingerprint,
            "sample_start": start,
            "sample_count": 8192,
            "timestamp_sec": start / _SAMPLE_RATE_HZ,
        })
        start += 8192
    return save_recording(
        samples,
        freq_hz=freq_hz,
        sample_rate_hz=_SAMPLE_RATE_HZ,
        device="hackrf",
        fingerprint_sequence=sequence,
        output_dir=tmp_path,
    )


def _demo_config(dwell_time_sec: float = 0.01) -> MimirConfig:
    """Return a MimirConfig tuned for fast tests."""
    return MimirConfig(
        frequencies_hz=[_FREQ_HZ],
        dwell_time_sec=dwell_time_sec,
        num_samples=2048,
        lna_gain_db=24.0,
        vga_gain_db=26.0,
        amp_enable=False,
        queue_maxsize=20,
        dashboard_host="127.0.0.1",
        dashboard_port=5000,
    )


class _FakeScanner:
    """Minimal scanner stand-in: DemoProducer only needs ``_queue``."""

    def __init__(self):
        self._queue: queue.Queue = queue.Queue(maxsize=20)


@pytest.fixture
def embedder() -> SpectrumEmbedder:
    return SpectrumEmbedder()


# ── Constructor tests ────────────────────────────────────────────────────────

class TestDemoProducerConstructor:
    """Tests for DemoProducer file loading and validation."""

    def test_one_shot_file_succeeds(self, tmp_path: Path, embedder) -> None:
        meta_path = _build_one_shot(tmp_path)
        scanner = _FakeScanner()
        config = _demo_config()

        producer = DemoProducer(
            sigmf_files=[meta_path],
            embedder=embedder,
            scanner=scanner,
            config=config,
        )

        assert producer._device_driver == "hackrf"
        assert producer._core_freq_hz == _FREQ_HZ
        assert producer._band_key == "fm_broadcast"
        assert producer._file_infos[meta_path]["chunk_count"] == 1

    def test_record_mode_file_succeeds(self, tmp_path: Path, embedder) -> None:
        meta_path = _build_recording(tmp_path, chunks=3)
        scanner = _FakeScanner()
        config = _demo_config()

        producer = DemoProducer(
            sigmf_files=[meta_path],
            embedder=embedder,
            scanner=scanner,
            config=config,
        )

        assert producer._file_infos[meta_path]["chunk_count"] == 3

    def test_missing_file_raises_file_not_found(
        self, tmp_path: Path, embedder
    ) -> None:
        scanner = _FakeScanner()
        config = _demo_config()

        with pytest.raises(FileNotFoundError):
            DemoProducer(
                sigmf_files=[tmp_path / "missing.sigmf-meta"],
                embedder=embedder,
                scanner=scanner,
                config=config,
            )

    def test_malformed_file_raises_replay_file_error(
        self, tmp_path: Path, embedder
    ) -> None:
        bad_path = tmp_path / "bad.sigmf-meta"
        bad_path.write_text("not a sigmf file")
        scanner = _FakeScanner()
        config = _demo_config()

        with pytest.raises(ReplayFileError):
            DemoProducer(
                sigmf_files=[bad_path],
                embedder=embedder,
                scanner=scanner,
                config=config,
            )


# ── Thread lifecycle tests ─────────────────────────────────────────────────────

class TestDemoProducerThread:
    """Tests for DemoProducer.start() / stop() and the _run() thread body."""

    def test_start_stop_cleanly_terminates(
        self, tmp_path: Path, embedder
    ) -> None:
        meta_path = _build_one_shot(tmp_path)
        scanner = _FakeScanner()
        config = _demo_config(dwell_time_sec=0.01)
        producer = DemoProducer(
            sigmf_files=[meta_path],
            embedder=embedder,
            scanner=scanner,
            config=config,
        )

        producer.start()
        time.sleep(0.05)
        producer.stop()
        if producer._thread is not None:
            producer._thread.join(timeout=0.5)

        assert producer._thread is None or not producer._thread.is_alive()

    def test_thread_pushes_correct_item_shape(
        self, tmp_path: Path, embedder
    ) -> None:
        meta_path = _build_one_shot(tmp_path)
        scanner = _FakeScanner()
        config = _demo_config(dwell_time_sec=0.01)
        producer = DemoProducer(
            sigmf_files=[meta_path],
            embedder=embedder,
            scanner=scanner,
            config=config,
        )

        producer.start()
        try:
            item = scanner._queue.get(timeout=2.0)
        finally:
            producer.stop()
            if producer._thread is not None:
                producer._thread.join(timeout=0.5)

        assert set(item.keys()) == {"freq_hz", "fingerprint", "vector", "psd_db"}
        assert item["freq_hz"] == _FREQ_HZ
        assert isinstance(item["vector"], list)
        assert len(item["vector"]) == 7

    def test_demo_key_annotation_matches_file_and_chunk(
        self, tmp_path: Path, embedder
    ) -> None:
        meta_path = _build_one_shot(tmp_path)
        scanner = _FakeScanner()
        config = _demo_config(dwell_time_sec=0.01)
        producer = DemoProducer(
            sigmf_files=[meta_path],
            embedder=embedder,
            scanner=scanner,
            config=config,
        )
        expected_file_id = producer._file_infos[meta_path]["file_id"]

        producer.start()
        try:
            item = scanner._queue.get(timeout=2.0)
        finally:
            producer.stop()
            if producer._thread is not None:
                producer._thread.join(timeout=0.5)

        demo_key = item["fingerprint"]["mimir:demo_key"]
        assert demo_key == f"{expected_file_id}:0"

    def test_pacing_between_chunks(self, tmp_path: Path, embedder) -> None:
        meta_path = _build_recording(tmp_path, chunks=2)
        scanner = _FakeScanner()
        dwell = 0.05
        config = _demo_config(dwell_time_sec=dwell)
        producer = DemoProducer(
            sigmf_files=[meta_path],
            embedder=embedder,
            scanner=scanner,
            config=config,
        )

        producer.start()
        try:
            t0 = time.time()
            scanner._queue.get(timeout=2.0)
            scanner._queue.get(timeout=2.0)
            elapsed = time.time() - t0
        finally:
            producer.stop()
            if producer._thread is not None:
                producer._thread.join(timeout=0.5)

        assert elapsed >= dwell - 0.005

    def test_loops_back_to_file_zero(
        self, tmp_path: Path, embedder
    ) -> None:
        meta_path = _build_one_shot(tmp_path)
        scanner = _FakeScanner()
        config = _demo_config(dwell_time_sec=0.01)
        producer = DemoProducer(
            sigmf_files=[meta_path],
            embedder=embedder,
            scanner=scanner,
            config=config,
        )
        expected_file_id = producer._file_infos[meta_path]["file_id"]

        producer.start()
        try:
            keys = []
            for _ in range(3):
                item = scanner._queue.get(timeout=2.0)
                keys.append(item["fingerprint"]["mimir:demo_key"])
        finally:
            producer.stop()
            if producer._thread is not None:
                producer._thread.join(timeout=0.5)

        # All three keys are the same file_id:0, confirming the one-shot
        # file is replayed repeatedly.
        assert all(k == f"{expected_file_id}:0" for k in keys)

    def test_broadcast_spectrum_fn_called_with_right_shape(
        self, tmp_path: Path, embedder
    ) -> None:
        meta_path = _build_one_shot(tmp_path)
        scanner = _FakeScanner()
        config = _demo_config(dwell_time_sec=0.01)
        mock_broadcast = MagicMock()
        producer = DemoProducer(
            sigmf_files=[meta_path],
            embedder=embedder,
            scanner=scanner,
            config=config,
            broadcast_spectrum_fn=mock_broadcast,
        )

        producer.start()
        try:
            scanner._queue.get(timeout=2.0)
        finally:
            producer.stop()
            if producer._thread is not None:
                producer._thread.join(timeout=0.5)

        mock_broadcast.assert_called()
        args = mock_broadcast.call_args[0]
        assert len(args) == 4
        assert len(args[0]) == 2048
        assert args[1] == _FREQ_HZ
        assert args[2] < _FREQ_HZ
        assert args[3] > _FREQ_HZ

    def test_broadcast_failure_does_not_kill_thread(
        self, tmp_path: Path, embedder
    ) -> None:
        meta_path = _build_one_shot(tmp_path)
        scanner = _FakeScanner()
        config = _demo_config(dwell_time_sec=0.01)

        def failing_broadcast(*args, **kwargs):
            raise RuntimeError("broadcast socket closed")

        producer = DemoProducer(
            sigmf_files=[meta_path],
            embedder=embedder,
            scanner=scanner,
            config=config,
            broadcast_spectrum_fn=failing_broadcast,
        )

        producer.start()
        try:
            item = scanner._queue.get(timeout=2.0)
        finally:
            producer.stop()
            if producer._thread is not None:
                producer._thread.join(timeout=0.5)

        assert set(item.keys()) == {"freq_hz", "fingerprint", "vector", "psd_db"}

    def test_produce_chunk_calls_compute_psd_exactly_once_per_chunk(
        self, embedder, monkeypatch, tmp_path,
    ) -> None:
        """Regression test for Phase 76 fix (Part A).

        Phase 76's DemoProducer called compute_psd() directly AND
        indirectly via fingerprint_samples(), wasting one FFT per
        chunk. This pins the single-call contract.
        """
        meta_path = _build_one_shot(tmp_path)

        from core.pipeline.demo_producer import (
            compute_psd as real_compute_psd,
            fingerprint_from_psd as real_fingerprint_from_psd,
        )
        counts = {"compute_psd": 0, "fingerprint_from_psd": 0}

        def counting_compute_psd(*args, **kwargs):
            counts["compute_psd"] += 1
            return real_compute_psd(*args, **kwargs)

        def counting_fingerprint_from_psd(*args, **kwargs):
            counts["fingerprint_from_psd"] += 1
            return real_fingerprint_from_psd(*args, **kwargs)

        monkeypatch.setattr(
            "core.pipeline.demo_producer.compute_psd",
            counting_compute_psd,
        )
        monkeypatch.setattr(
            "core.pipeline.demo_producer.fingerprint_from_psd",
            counting_fingerprint_from_psd,
        )

        scanner = _FakeScanner()
        config = _demo_config(dwell_time_sec=0.0)
        producer = DemoProducer(
            sigmf_files=[meta_path],
            embedder=embedder,
            scanner=scanner,
            config=config,
        )
        producer.start()
        items: list = []
        try:
            first = scanner._queue.get(timeout=5.0)
            items.append(first)
        finally:
            producer.stop()
            if producer._thread is not None:
                producer._thread.join(timeout=2.0)
            # Drain anything the daemon thread produced between the
            # first item landing and stop() propagating through the
            # 0.5 s DEMO_CHUNK_INTERVAL_SEC pacing sleep.
            while True:
                try:
                    items.append(scanner._queue.get_nowait())
                except queue.Empty:
                    break

        assert len(items) >= 1, "Expected at least one produced chunk"
        assert counts["compute_psd"] == len(items), (
            f"Expected 1 compute_psd() call per produced chunk. "
            f"Got {counts['compute_psd']} compute_psd calls for "
            f"{len(items)} items (regressed to the old double-FFT path)."
        )
        assert counts["fingerprint_from_psd"] == len(items)
        for item in items:
            assert "freq_hz" in item
            assert "fingerprint" in item
            assert "vector" in item
            assert "psd_db" in item

    def test_produce_chunk_pacing_uses_demo_constant_not_config_dwell(
        self, embedder, monkeypatch, tmp_path,
    ) -> None:
        """Regression test for Phase 76 fix (Part B).

        Phase 76's DemoProducer used config.dwell_time_sec as the pacing
        value. With the live config setting dwell_time_sec=0.0, the demo
        flooded the queue. This pins the per-chunk pacing to the dedicated
        DEMO_CHUNK_INTERVAL_SEC constant.
        """
        meta_path = _build_one_shot(tmp_path)

        sleep_calls = []

        def counting_sleep(seconds):
            sleep_calls.append(seconds)

        monkeypatch.setattr(
            "core.pipeline.demo_producer.time.sleep",
            counting_sleep,
        )

        scanner = _FakeScanner()
        config = _demo_config(dwell_time_sec=0.0)
        producer = DemoProducer(
            sigmf_files=[meta_path],
            embedder=embedder,
            scanner=scanner,
            config=config,
        )
        producer.start()
        try:
            scanner._queue.get(timeout=5.0)
        finally:
            producer.stop()
            if producer._thread is not None:
                producer._thread.join(timeout=2.0)

        from core.pipeline.demo_producer import DEMO_CHUNK_INTERVAL_SEC

        assert len(sleep_calls) >= 1, "Expected at least one sleep call per chunk"
        for arg in sleep_calls:
            assert arg == DEMO_CHUNK_INTERVAL_SEC, (
                f"Demo chunk sleep must equal DEMO_CHUNK_INTERVAL_SEC "
                f"({DEMO_CHUNK_INTERVAL_SEC}), got {arg}"
            )
            assert arg != 0.0, (
                "Demo chunk sleep regressed to config.dwell_time_sec "
                "(likely 0.0) — demo will flood the queue"
            )
