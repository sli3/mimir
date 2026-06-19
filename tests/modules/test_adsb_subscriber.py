"""Tests for AdsbSubscriber — lifecycle, queue, frequency filter, scan loop integration, flush harvest."""

import threading
import time

import numpy as np

from core.config.loader import MimirConfig
from core.pipeline.scanner import ScanRunner
from modules.adsb import AdsbSubscriber
from modules.adsb.constants import AU_ADSB_FREQUENCY_HZ
from modules.adsb.message import AdsbMessage


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


class TestAdsbSubscriber:
    def test_subscriber_ignores_non_adsb_frequency(self):
        """IQ chunks at 98 MHz are silently dropped."""
        sub = AdsbSubscriber(broadcast_fn=lambda m: None)
        sub.receive(np.zeros(100, dtype=np.complex64), 98_000_000.0, 2_000_000.0)
        assert sub._queue.empty()

    def test_subscriber_accepts_adsb_frequency(self):
        """IQ chunks at 1090 MHz are queued."""
        sub = AdsbSubscriber(broadcast_fn=lambda m: None)
        sub.receive(np.zeros(100, dtype=np.complex64), 1_090_000_000.0, 2_000_000.0)
        assert not sub._queue.empty()

    def test_subscriber_accepts_frequency_within_tolerance(self):
        """IQ chunks within 2 MHz of 1090 MHz are queued."""
        sub = AdsbSubscriber(broadcast_fn=lambda m: None)
        sub.receive(np.zeros(100, dtype=np.complex64), 1_089_000_000.0, 2_000_000.0)
        assert not sub._queue.empty()

    def test_subscriber_drops_when_queue_full(self):
        """When queue is full, new chunks are dropped without exception."""
        sub = AdsbSubscriber(broadcast_fn=lambda m: None)
        for _ in range(64):
            sub.receive(np.zeros(100, dtype=np.complex64), 1_090_000_000.0, 2_000_000.0)
        sub.receive(np.zeros(100, dtype=np.complex64), 1_090_000_000.0, 2_000_000.0)
        assert sub._queue.qsize() == 64

    def test_subscriber_lifecycle_start_stop(self):
        """start() spawns a thread; stop() terminates it cleanly."""
        sub = AdsbSubscriber(broadcast_fn=lambda m: None)
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
            frequencies_hz=[1_090_000_000],
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
        sub = AdsbSubscriber(broadcast_fn=lambda m: None)
        scanner.register_iq_subscriber(sub)
        assert sub in scanner._iq_subscribers

    def test_scan_loop_broadcasts_to_subscriber(self):
        """ScanRunner._scan_loop calls subscriber.receive with samples."""
        samples = np.ones(100, dtype=np.complex64)
        device = MockDevice(samples=samples)
        config = MimirConfig(
            frequencies_hz=[1_090_000_000],
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
        thread = threading.Thread(target=scanner._scan_loop)
        thread.start()
        time.sleep(0.15)
        scanner._running = False
        thread.join(timeout=2.0)
        assert len(received) >= 1
        assert np.array_equal(received[0][0], samples)
        assert received[0][1] == 1_090_000_000.0
        assert received[0][2] == 2_000_000.0

    def test_stop_broadcasts_harvested_messages(self):
        """When flush() returns messages, stop() broadcasts each."""
        harvested = []
        msg1 = AdsbMessage(
            icao="ABC123", callsign="TEST1", latitude=-34.0, longitude=138.0,
            altitude_ft=35000, groundspeed=450.0, track=180.0, vertical_rate=0,
            raw_hex="8D406B902015A678D4D220AA4BDA",
        )
        msg2 = AdsbMessage(
            icao="DEF456", callsign="TEST2", latitude=-35.0, longitude=139.0,
            altitude_ft=30000, groundspeed=420.0, track=270.0, vertical_rate=-500,
            raw_hex="8D485020994409940838175B284F",
        )
        sub = AdsbSubscriber(broadcast_fn=lambda m: harvested.append(m))
        sub._decoder.flush = lambda: [msg1, msg2]
        sub.stop()
        assert len(harvested) == 2
        assert harvested[0].icao == "ABC123"
        assert harvested[1].icao == "DEF456"

    def test_stop_no_broadcast_when_flush_empty(self):
        """When flush() returns empty list, no broadcast is made."""
        harvested = []
        sub = AdsbSubscriber(broadcast_fn=lambda m: harvested.append(m))
        sub._decoder.flush = lambda: []
        sub.stop()
        assert len(harvested) == 0
