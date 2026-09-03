"""
tests/core/test_adsb_demo_producer.py
Mimir RF Scanner — TD-76-7 ADS-B decode demo producer tests

PURPOSE
-------
Tests for ``AdsbDemoProducer`` in ``core/pipeline/adsb_demo_producer.py``.
Proves it validates its input SigMF file, replays raw IQ chunks into
``AdsbSubscriber.receive()``, and end-to-end decodes a synthetic ADS-B
frame during demo mode. All tests build synthetic SigMF files in
``tmp_path`` except the constructor-success test, which uses the real
pre-recorded ADS-B capture.

Run with:
    uv run pytest tests/core/test_adsb_demo_producer.py -v
"""

from __future__ import annotations

import json
import logging
import sys
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.pipeline.adsb_demo_producer import (
    ADSB_DEMO_CHUNK_SAMPLES,
    AdsbDemoProducer,
)
from core.pipeline.capture import save_capture
from core.pipeline.replay import ReplayFileError
from modules.adsb.constants import (
    AU_ADSB_FREQUENCY_HZ,
    DATA_BITS,
    PREAMBLE_HIGH_INDICES,
    PREAMBLE_LOW_INDICES,
    PREAMBLE_SAMPLES,
)
from modules.adsb.message import AdsbMessage
from modules.adsb.subscriber import AdsbSubscriber


# Known-good DF17 ADS-B identification message from the decoder test suite.
# It decodes to ICAO 406B90 / callsign EZY85MH under pyModeS 3.3.0.
_IDENT_MSG = "8D406B902015A678D4D220AA4BDA"


def _hex_to_bits(raw_hex: str) -> list[int]:
    """Convert a 28-character ADS-B hex string to 112 bits (MSB-first)."""
    bits = []
    for byte in bytes.fromhex(raw_hex):
        for i in range(8):
            bits.append((byte >> (7 - i)) & 1)
    return bits


def _build_adsb_iq_chunk(
    raw_hex: str,
    num_samples: int = ADSB_DEMO_CHUNK_SAMPLES,
) -> np.ndarray:
    """Build a synthetic complex64 IQ chunk containing one ADS-B frame.

    The amplitude envelope carries a valid ADS-B preamble followed by
    the 112 PPM-encoded bits of ``raw_hex``. This is purely a receive-path
    test fixture; it creates in-memory samples for the demodulator and
    does not interact with radio hardware.
    """
    bits = _hex_to_bits(raw_hex)
    assert len(bits) == DATA_BITS

    # Quiet baseline so only the intended preamble fires. 0.1 is low
    # enough that the preamble's 10:1 contrast clears the threshold
    # (PREAMBLE_THRESHOLD = 8.0) while keeping data chips distinct.
    buffer = np.full(num_samples, 0.1, dtype=np.float32)

    # Place the message well inside the chunk.
    start = 1000

    # If the buffer is too small to hold the frame fixture, just return the
    # quiet buffer — this is used for EOF-edge tests where decode is not
    # the point.
    if num_samples < start + PREAMBLE_SAMPLES + DATA_BITS * 2:
        return buffer.astype(np.complex64)

    # Preamble pattern: four high pulses, twelve low slots.
    for idx in PREAMBLE_HIGH_INDICES:
        buffer[start + idx] = 1.0
    for idx in PREAMBLE_LOW_INDICES:
        buffer[start + idx] = 0.1

    # Data bits: PPM chip pairs. bit=1 means chip_a > chip_b.
    data_start = start + PREAMBLE_SAMPLES
    for k, bit in enumerate(bits):
        if bit == 1:
            buffer[data_start + k * 2] = 0.8
            buffer[data_start + k * 2 + 1] = 0.2
        else:
            buffer[data_start + k * 2] = 0.2
            buffer[data_start + k * 2 + 1] = 0.8

    # The demodulator uses amplitude only; imaginary part is irrelevant.
    return buffer.astype(np.complex64)


def _build_synthetic_adsb_sigmf(
    tmp_path: Path,
    freq_hz: float,
    *,
    num_samples: int | None = None,
) -> Path:
    """Write a SigMF file with a synthetic ADS-B frame and optional length.

    Defaults to exactly one ADS-B demo chunk. Pass ``num_samples`` to
    create a shorter or longer file (e.g. 1.5 chunks to exercise EOF wrap).
    """
    if num_samples is None:
        num_samples = ADSB_DEMO_CHUNK_SAMPLES
    samples = _build_adsb_iq_chunk(_IDENT_MSG, num_samples=num_samples)
    return save_capture(
        samples,
        freq_hz=freq_hz,
        sample_rate_hz=2_000_000,
        device="plutosdr",
        output_dir=tmp_path,
    )


def _build_malformed_sigmf(
    tmp_path: Path,
    *,
    sample_rate_hz: float,
    freq_hz: float,
) -> Path:
    """Write a SigMF file with the requested sample rate and frequency.

    The file carries no fingerprint metadata; AdsbDemoProducer does not
    require it, so the constructor reaches its own sample-rate and
    frequency checks.
    """
    samples = np.zeros(1_024, dtype=np.complex64)
    return save_capture(
        samples,
        freq_hz=freq_hz,
        sample_rate_hz=sample_rate_hz,
        device="plutosdr",
        output_dir=tmp_path,
    )


# ── Constructor validation tests ─────────────────────────────────────────────

class TestAdsbDemoProducerConstructor:
    """Tests for AdsbDemoProducer file loading and validation."""

    def test_wrong_sample_rate_raises_replay_file_error(
        self, tmp_path: Path
    ) -> None:
        path = _build_malformed_sigmf(
            tmp_path,
            sample_rate_hz=4_000_000,
            freq_hz=AU_ADSB_FREQUENCY_HZ,
        )
        subscriber = MagicMock(spec=AdsbSubscriber)

        with pytest.raises(ReplayFileError) as exc_info:
            AdsbDemoProducer(path, subscriber)

        message = str(exc_info.value)
        assert "4000000" in message
        assert "2_000_000" in message

    def test_wrong_frequency_raises_replay_file_error(
        self, tmp_path: Path
    ) -> None:
        path = _build_malformed_sigmf(
            tmp_path,
            sample_rate_hz=2_000_000,
            freq_hz=100_000_000,
        )
        subscriber = MagicMock(spec=AdsbSubscriber)

        with pytest.raises(ReplayFileError) as exc_info:
            AdsbDemoProducer(path, subscriber)

        message = str(exc_info.value)
        assert "100.00 MHz" in message
        assert f"{AU_ADSB_FREQUENCY_HZ / 1e6:.2f} MHz" in message

    def test_missing_file_raises_file_not_found(self, tmp_path: Path) -> None:
        subscriber = MagicMock(spec=AdsbSubscriber)
        missing = tmp_path / "missing.sigmf-meta"

        with pytest.raises(FileNotFoundError):
            AdsbDemoProducer(missing, subscriber)

    def test_zero_sample_file_raises_replay_file_error(
        self, tmp_path: Path
    ) -> None:
        """A .sigmf-meta whose .sigmf-data sibling is missing reports zero
        samples and raises ReplayFileError at construction.
        """
        path = _build_synthetic_adsb_sigmf(tmp_path, AU_ADSB_FREQUENCY_HZ)
        # Remove the data file so SigMF reports sample_count=0.
        path.with_suffix(".sigmf-data").unlink()
        subscriber = MagicMock(spec=AdsbSubscriber)

        with pytest.raises(ReplayFileError) as exc_info:
            AdsbDemoProducer(path, subscriber)

        message = str(exc_info.value)
        assert "zero samples" in message
        assert ".sigmf-data" in message

    @pytest.mark.skipif(
        not Path(
            "data/captures/capture_1090030000hz_20260820_153307.sigmf-meta"
        ).exists(),
        reason="real ADS-B capture fixture not present",
    )
    def test_constructor_succeeds_with_real_adsb_capture(self) -> None:
        path = Path(
            "data/captures/capture_1090030000hz_20260820_153307.sigmf-meta"
        )
        assert path.exists(), f"Pre-recorded ADS-B capture not found: {path}"
        subscriber = MagicMock(spec=AdsbSubscriber)

        producer = AdsbDemoProducer(path, subscriber)

        assert producer._core_freq_hz == 1_090_030_000.0
        assert producer._sample_rate_hz == 2_000_000.0
        assert isinstance(producer._stop_event, threading.Event)
        assert producer._started is False
        assert producer._thread is None


# ── Thread lifecycle and loop tests ────────────────────────────────────────────

class TestAdsbDemoProducerLoop:
    """Tests for AdsbDemoProducer.start() / stop() and the _run() body."""

    def test_loop_calls_receive_with_correct_shapes(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        path = _build_synthetic_adsb_sigmf(tmp_path, AU_ADSB_FREQUENCY_HZ)
        subscriber = MagicMock(spec=AdsbSubscriber)
        producer = AdsbDemoProducer(path, subscriber)

        # Avoid real-time pacing in this test.
        monkeypatch.setattr(
            "core.pipeline.adsb_demo_producer.time.sleep",
            lambda _s: None,
        )

        received_args: list[tuple] = []

        def receive_and_stop(*args, **kwargs):
            received_args.append((args, kwargs))
            producer.stop()

        subscriber.receive.side_effect = receive_and_stop

        producer._run()

        assert len(received_args) == 1
        (args, _kwargs) = received_args[0]
        iq_chunk, freq_hz, sample_rate_hz = args
        assert isinstance(iq_chunk, np.ndarray)
        assert iq_chunk.dtype == np.complex64
        assert iq_chunk.shape == (ADSB_DEMO_CHUNK_SAMPLES,)
        assert freq_hz == float(AU_ADSB_FREQUENCY_HZ)
        assert sample_rate_hz == 2_000_000.0

    def test_start_stop_cleanly_terminates(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        path = _build_synthetic_adsb_sigmf(tmp_path, AU_ADSB_FREQUENCY_HZ)
        subscriber = MagicMock(spec=AdsbSubscriber)
        producer = AdsbDemoProducer(path, subscriber)

        monkeypatch.setattr(
            "core.pipeline.adsb_demo_producer.time.sleep",
            lambda _s: None,
        )

        producer.start()
        time.sleep(0.05)
        producer.stop()
        producer.join(timeout=0.5)

        assert producer._thread is None or not producer._thread.is_alive()

    def test_wraps_to_start_index_zero_at_eof_with_no_error(
        self, tmp_path: Path, monkeypatch, caplog
    ) -> None:
        """A 1.5-chunk file wraps cleanly at EOF without ERROR logs."""
        num_samples = int(ADSB_DEMO_CHUNK_SAMPLES * 1.5)
        path = _build_synthetic_adsb_sigmf(
            tmp_path, AU_ADSB_FREQUENCY_HZ, num_samples=num_samples
        )
        subscriber = MagicMock(spec=AdsbSubscriber)
        producer = AdsbDemoProducer(path, subscriber)

        monkeypatch.setattr(
            "core.pipeline.adsb_demo_producer.time.sleep",
            lambda _s: None,
        )

        received_chunks: list[np.ndarray] = []

        def receive_and_count(iq_chunk, *_args, **_kwargs):
            received_chunks.append(iq_chunk)
            if len(received_chunks) >= 2:
                producer.stop()

        subscriber.receive.side_effect = receive_and_count

        with caplog.at_level(logging.ERROR):
            producer._run()

        assert len(received_chunks) >= 2
        assert caplog.records == []
        # Each delivered chunk must be the full chunk size.
        assert all(c.shape == (ADSB_DEMO_CHUNK_SAMPLES,) for c in received_chunks)

    def test_short_file_wraps_immediately_without_busy_spin(
        self, tmp_path: Path, monkeypatch, caplog
    ) -> None:
        """A file shorter than one chunk sleeps at EOF instead of spinning."""
        path = _build_synthetic_adsb_sigmf(
            tmp_path, AU_ADSB_FREQUENCY_HZ, num_samples=100
        )
        subscriber = MagicMock(spec=AdsbSubscriber)
        producer = AdsbDemoProducer(path, subscriber)

        sleeps: list[float] = []

        def tracked_sleep(seconds: float) -> None:
            sleeps.append(seconds)
            if len(sleeps) >= 3:
                producer.stop()

        monkeypatch.setattr(
            "core.pipeline.adsb_demo_producer.time.sleep",
            tracked_sleep,
        )

        with caplog.at_level(logging.ERROR):
            producer._run()

        assert len(sleeps) >= 3
        assert caplog.records == []
        # Subscriber.receive is never called because the file is shorter
        # than a single chunk and the loop wraps before reading.
        subscriber.receive.assert_not_called()

    def test_full_loop_replay_emits_no_error_records(
        self, tmp_path: Path, monkeypatch, caplog
    ) -> None:
        """A normal one-chunk replay emits no ERROR-level log records."""
        path = _build_synthetic_adsb_sigmf(tmp_path, AU_ADSB_FREQUENCY_HZ)
        subscriber = MagicMock(spec=AdsbSubscriber)
        producer = AdsbDemoProducer(path, subscriber)

        monkeypatch.setattr(
            "core.pipeline.adsb_demo_producer.time.sleep",
            lambda _s: None,
        )

        def receive_once(iq_chunk, *_args, **_kwargs):
            producer.stop()

        subscriber.receive.side_effect = receive_once

        with caplog.at_level(logging.ERROR):
            producer._run()

        assert caplog.records == []


# ── End-to-end integration test ──────────────────────────────────────────────

class TestAdsbDemoProducerIntegration:
    """Prove the producer feeds real decoded aircraft to the subscriber."""

    def test_synthetic_sigmf_decodes_known_icao(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        path = _build_synthetic_adsb_sigmf(tmp_path, AU_ADSB_FREQUENCY_HZ)
        broadcast_messages: list[AdsbMessage] = []

        def broadcast_fn(msg: AdsbMessage) -> None:
            broadcast_messages.append(msg)

        subscriber = AdsbSubscriber(
            broadcast_fn=broadcast_fn,
            scan_result_fn=MagicMock(),
        )
        subscriber.start()

        producer = AdsbDemoProducer(path, subscriber)
        monkeypatch.setattr(
            "core.pipeline.adsb_demo_producer.time.sleep",
            lambda _s: None,
        )

        # Run one chunk, then stop the producer immediately.
        real_receive = subscriber.receive

        def receive_once_and_stop(iq_chunk, freq_hz, sample_rate_hz):
            real_receive(iq_chunk, freq_hz, sample_rate_hz)
            producer.stop()

        monkeypatch.setattr(
            subscriber,
            "receive",
            receive_once_and_stop,
        )

        producer._run()
        # Give the subscriber's decode thread time to demodulate/decode.
        time.sleep(0.3)
        subscriber.stop()

        assert len(broadcast_messages) >= 1
        assert any(msg.icao == "406B90" for msg in broadcast_messages), (
            f"Expected ICAO 406B90 in broadcast messages, got "
            f"{[m.icao for m in broadcast_messages]}"
        )


# ── scan.py demo-mode smoke test ─────────────────────────────────────────────

class TestScanDemoModeSmoke:
    """Prove scan.py --demo wires both producers without blocking."""

    def _build_fm_demo_file(self, tmp_path: Path) -> Path:
        from core.pipeline.fft import compute_psd
        from core.pipeline.features import fingerprint_spectrum
        from dashboard.shared_state import BAND_PROFILES

        rng = np.random.default_rng(42)
        fm_samples = (
            rng.standard_normal(16_384)
            + 1j * rng.standard_normal(16_384)
        ).astype(np.complex64)
        profile = BAND_PROFILES["fm_broadcast"]
        psd_result = compute_psd(fm_samples, 2_000_000, 98_000_000)
        fingerprint = fingerprint_spectrum(
            psd_result,
            signal_threshold_db=profile.get("signal_threshold_db"),
            crop_half_width_hz=profile.get("crop_half_width_hz"),
            burst_use_wide_window=profile.get("burst_use_wide_window", False),
            trace_key=profile.get("fingerprint_trace_key", "psd_db"),
        )
        return save_capture(
            fm_samples,
            freq_hz=98_000_000,
            sample_rate_hz=2_000_000,
            device="hackrf",
            output_dir=tmp_path,
            fingerprint=fingerprint,
        )

    def _write_cache(self, cache_path: Path, fm_meta: Path) -> None:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache = {
            "version": 1,
            "device_driver": "hackrf",
            "files": {
                "abc": {
                    "path": str(fm_meta),
                    "device_profile": "hackrf",
                    "chunks": {
                        "0": {
                            "signal_type": "fm_broadcast",
                            "confidence": "high",
                            "confidence_score": 0.94,
                            "novel": False,
                            "reasoning": "Demo cache hit.",
                            "au_legal_status": "legal_rx",
                            "frequency_band": "fm_broadcast_band",
                            "raw_response": "{}",
                        }
                    },
                }
            },
        }
        cache_path.write_text(json.dumps(cache), encoding="utf-8")

    def test_scan_demo_starts_both_producers(
        self, tmp_path: Path
    ) -> None:
        from contextlib import ExitStack
        from scan import main

        fm_meta = self._build_fm_demo_file(tmp_path)
        adsb_meta = _build_synthetic_adsb_sigmf(
            tmp_path, AU_ADSB_FREQUENCY_HZ
        )
        cache_path = tmp_path / "demo_cache.json"
        self._write_cache(cache_path, fm_meta)

        with ExitStack() as stack:
            stack.enter_context(patch("scan.start_server"))
            mock_scanner_cls = stack.enter_context(patch("scan.ScanRunner"))
            mock_demo_cls = stack.enter_context(patch("scan.DemoProducer"))
            mock_adsb_demo_cls = stack.enter_context(
                patch("scan.AdsbDemoProducer")
            )
            stack.enter_context(
                patch(
                    "scan.DemoSignalClassifier.__init__",
                    lambda self, cache_path: None,
                )
            )
            stack.enter_context(patch("scan.load_config"))
            stack.enter_context(patch("scan.SignalStore"))
            stack.enter_context(patch("scan.SpectrumEmbedder"))
            stack.enter_context(patch("scan.detect_device"))
            stack.enter_context(patch("scan.build_device"))
            stack.enter_context(patch("scan.AcarsSubscriber"))
            stack.enter_context(patch("scan.AisSubscriber"))

            # Mock instances need enough shape for the finally block.
            mock_demo_cls.return_value._thread = MagicMock()
            mock_demo_cls.return_value._stop_event = MagicMock()
            mock_adsb_demo_cls.return_value._thread = MagicMock()
            mock_adsb_demo_cls.return_value._stop_event = MagicMock()

            # Make the scanner's AI loop return immediately so the
            # finally block runs and the process exits cleanly.
            mock_scanner_cls.return_value.start_ai_only.return_value = None

            with patch.object(sys, "argv", [
                "scan.py",
                "--demo",
                "--demo-files", str(fm_meta),
                "--demo-cache", str(cache_path),
                "--demo-files-adsb", str(adsb_meta),
            ]):
                try:
                    main()
                except SystemExit as exc:
                    assert exc.code == 0

        # Both producers were instantiated and started; no producer
        # blocked the other because the AI loop returned immediately.
        mock_demo_cls.assert_called_once()
        mock_demo_cls.return_value.start.assert_called_once()
        mock_adsb_demo_cls.assert_called_once()
        mock_adsb_demo_cls.return_value.start.assert_called_once()

        # Verify AdsbDemoProducer received the explicit --demo-files-adsb
        # path and the real AdsbSubscriber instance.
        call_kwargs = mock_adsb_demo_cls.call_args.kwargs
        assert "sigmf_path" in call_kwargs
        assert "adsb_subscriber" in call_kwargs
        assert str(call_kwargs["sigmf_path"]) == str(adsb_meta)


