"""Tests for AcarsSubscriber — lifecycle, queue, frequency filter, scan loop integration."""

import queue
import threading
import time

import numpy as np
import pytest

from core.config.loader import MimirConfig
from core.pipeline.scanner import ScanRunner
from modules.acars import AcarsSubscriber
from modules.acars.constants import AU_ACARS_FREQUENCIES_HZ


class MockDevice:
    """Fake SDR that returns synthetic IQ samples."""

    def __init__(self, samples=None):
        self._samples = samples
        self.is_open = True

    def set_center_frequency(self, freq_hz: float) -> None:
        pass

    def read_samples(self, num_samples: int):
        if self._samples is not None:
            return self._samples
        return np.zeros(num_samples, dtype=np.complex64)

    def close(self):
        self.is_open = False


class MockEmbedder:
    def embed(self, fingerprint):
        return [0.0] * 8


class MockStore:
    def query(self, vector, n_results=5):
        return {"metadatas": [[]], "distances": [[]]}


class MockClassifier:
    def classify(self, fingerprint, neighbours, acma_allocations=None):
        class Result:
            signal_type = "TEST"
            confidence = "high"
            confidence_score = 0.99
            novel = False
            au_legal_status = "LEGAL"
            reasoning = "test"
        return Result()


class TestAcarsSubscriber:
    def test_subscriber_ignores_non_acars_frequency(self):
        """IQ chunks at 98 MHz are silently dropped."""
        calls = []
        sub = AcarsSubscriber(broadcast_fn=lambda m: calls.append(m))
        sub.receive(np.zeros(100, dtype=np.complex64), 98_000_000.0, 2_000_000.0)
        assert sub._queue.empty()

    def test_subscriber_accepts_acars_frequency(self):
        """IQ chunks at 129.125 MHz are queued."""
        calls = []
        sub = AcarsSubscriber(broadcast_fn=lambda m: calls.append(m))
        sub.receive(np.zeros(100, dtype=np.complex64), 129_125_000.0, 2_000_000.0)
        assert not sub._queue.empty()

    def test_subscriber_drops_when_queue_full(self):
        """When queue is full, new chunks are dropped without exception."""
        sub = AcarsSubscriber(broadcast_fn=lambda m: None)
        # Fill the queue
        for _ in range(32):
            sub.receive(np.zeros(100, dtype=np.complex64), 129_125_000.0, 2_000_000.0)
        # One more should not raise
        sub.receive(np.zeros(100, dtype=np.complex64), 129_125_000.0, 2_000_000.0)
        assert sub._queue.qsize() == 32

    def test_subscriber_lifecycle_start_stop(self):
        """start() spawns a thread; stop() terminates it cleanly."""
        sub = AcarsSubscriber(broadcast_fn=lambda m: None)
        sub.start()
        assert sub._thread is not None
        assert sub._thread.is_alive()
        sub.stop()
        time.sleep(0.1)
        assert not sub._thread.is_alive()

    def test_register_iq_subscriber_adds_to_list(self):
        """ScanRunner.register_iq_subscriber appends the subscriber."""
        device = MockDevice()
        config = MimirConfig(
            frequencies_hz=[129_125_000],
            num_samples=1024,
            dwell_time_sec=0.01,
            queue_maxsize=10,
            lna_gain_db=0.0,
            vga_gain_db=0.0,
            amp_enable=False,
            llm_url="http://localhost:8080/v1",
            dashboard_host="127.0.0.1",
            dashboard_port=5000,
        )
        scanner = ScanRunner(device, MockEmbedder(), MockStore(), MockClassifier(), config)
        sub = AcarsSubscriber(broadcast_fn=lambda m: None)
        scanner.register_iq_subscriber(sub)
        assert sub in scanner._iq_subscribers

    def test_scan_loop_broadcasts_to_subscriber(self):
        """ScanRunner._scan_loop calls subscriber.receive with samples."""
        samples = np.ones(100, dtype=np.complex64)
        device = MockDevice(samples=samples)
        config = MimirConfig(
            frequencies_hz=[129_125_000],
            num_samples=100,
            dwell_time_sec=0.01,
            queue_maxsize=10,
            lna_gain_db=0.0,
            vga_gain_db=0.0,
            amp_enable=False,
            llm_url="http://localhost:8080/v1",
            dashboard_host="127.0.0.1",
            dashboard_port=5000,
        )
        scanner = ScanRunner(device, MockEmbedder(), MockStore(), MockClassifier(), config)
        received = []

        class SpySubscriber:
            def receive(self, iq_chunk, freq_hz, sample_rate_hz):
                received.append((iq_chunk, freq_hz, sample_rate_hz))

        scanner.register_iq_subscriber(SpySubscriber())
        scanner._running = True
        # Run _scan_loop in a thread so we can stop it after one iteration
        thread = threading.Thread(target=scanner._scan_loop)
        thread.start()
        time.sleep(0.15)
        scanner._running = False
        thread.join(timeout=2.0)
        assert len(received) >= 1
        assert np.array_equal(received[0][0], samples)
        assert received[0][1] == 129_125_000.0
        assert received[0][2] == 2_000_000.0
