"""Tests for AdsbSubscriber — lifecycle, queue, frequency filter, scan loop integration, flush harvest."""

import threading
import time
from datetime import datetime, timedelta, timezone

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

    def test_scan_result_fn_called_on_successful_decode(self):
        """scan_result_fn callback is invoked on each successful decode."""
        broadcast_messages = []
        scan_result_messages = []

        def broadcast_spy(msg):
            broadcast_messages.append(msg)

        def scan_result_spy(msg):
            scan_result_messages.append(msg)

        msg = AdsbMessage(
            icao="7C4B4C", callsign="QFA456", latitude=-34.0, longitude=138.0,
            altitude_ft=35000, groundspeed=450.0, track=180.0, vertical_rate=0,
            raw_hex="8D406B902015A678D4D220AA4BDA",
        )

        sub = AdsbSubscriber(
            broadcast_fn=broadcast_spy,
            scan_result_fn=scan_result_spy,
        )

        def fake_demodulate(iq_chunk):
            return ["8D406B902015A678D4D220AA4BDA"]

        def fake_decode(raw_hex):
            return msg

        sub._demodulator.demodulate = fake_demodulate
        sub._decoder.decode = fake_decode

        iq_chunk = np.zeros(1024, dtype=np.complex64)
        sub.receive(iq_chunk, AU_ADSB_FREQUENCY_HZ, 2_000_000.0)

        sub.start()
        time.sleep(0.2)
        sub.stop()

        assert len(scan_result_messages) >= 1
        assert scan_result_messages[0].icao == "7C4B4C"

    def test_scan_result_fn_not_required(self):
        """AdsbSubscriber works without scan_result_fn (backward compatible)."""
        broadcast_messages = []

        def broadcast_spy(msg):
            broadcast_messages.append(msg)

        msg = AdsbMessage(
            icao="7C4B4C", callsign="QFA456", latitude=-34.0, longitude=138.0,
            altitude_ft=35000, groundspeed=450.0, track=180.0, vertical_rate=0,
            raw_hex="8D406B902015A678D4D220AA4BDA",
        )

        sub = AdsbSubscriber(broadcast_fn=broadcast_spy)

        def fake_demodulate(iq_chunk):
            return ["8D406B902015A678D4D220AA4BDA"]

        def fake_decode(raw_hex):
            return msg

        sub._demodulator.demodulate = fake_demodulate
        sub._decoder.decode = fake_decode

        iq_chunk = np.zeros(1024, dtype=np.complex64)
        sub.receive(iq_chunk, AU_ADSB_FREQUENCY_HZ, 2_000_000.0)

        sub.start()
        time.sleep(0.2)
        sub.stop()

        assert len(broadcast_messages) >= 1

    def test_stop_calls_scan_result_fn_for_harvested(self):
        """stop() invokes scan_result_fn for each harvested message."""
        harvested_broadcast = []
        harvested_scan = []

        def broadcast_spy(msg):
            harvested_broadcast.append(msg)

        def scan_result_spy(msg):
            harvested_scan.append(msg)

        msg = AdsbMessage(
            icao="7C4B4C", callsign="QFA456", latitude=-34.0, longitude=138.0,
            altitude_ft=35000, groundspeed=450.0, track=180.0, vertical_rate=0,
            raw_hex="8D406B902015A678D4D220AA4BDA",
        )

        sub = AdsbSubscriber(
            broadcast_fn=broadcast_spy,
            scan_result_fn=scan_result_spy,
        )
        sub._decoder.flush = lambda: [msg]
        sub.stop()

        assert len(harvested_scan) == 1
        assert harvested_scan[0].icao == "7C4B4C"

    def test_decode_loop_attaches_bearing_report(self):
        """Decode loop attaches bearing_deg (delta_r None on first sighting)."""
        broadcast_messages = []

        def broadcast_spy(msg):
            broadcast_messages.append(msg)

        msg = AdsbMessage(
            icao="7C4B4C", callsign="QFA456", latitude=-34.0, longitude=138.0,
            altitude_ft=35000, groundspeed=450.0, track=180.0, vertical_rate=0,
            raw_hex="8D406B902015A678D4D220AA4BDA",
        )

        sub = AdsbSubscriber(broadcast_fn=broadcast_spy)

        def fake_demodulate(iq_chunk):
            return ["8D406B902015A678D4D220AA4BDA"]

        def fake_decode(raw_hex):
            return msg

        sub._demodulator.demodulate = fake_demodulate
        sub._decoder.decode = fake_decode

        iq_chunk = np.zeros(1024, dtype=np.complex64)
        sub.receive(iq_chunk, AU_ADSB_FREQUENCY_HZ, 2_000_000.0)

        sub.start()
        time.sleep(0.2)
        sub.stop()

        assert len(broadcast_messages) >= 1
        assert isinstance(broadcast_messages[0].bearing_deg, float)
        assert broadcast_messages[0].delta_r_deg_per_sec is None

    def test_decode_loop_computes_delta_r_on_second_message(self):
        """Second position report for the same ICAO yields a delta_r rate."""
        broadcast_messages = []

        def broadcast_spy(msg):
            broadcast_messages.append(msg)

        ts1 = datetime.now(timezone.utc)
        ts2 = ts1 + timedelta(seconds=1.0)
        msg1 = AdsbMessage(
            icao="7C4B4C", callsign="QFA456", latitude=-34.0, longitude=138.0,
            altitude_ft=35000, groundspeed=450.0, track=180.0, vertical_rate=0,
            raw_hex="8D406B902015A678D4D220AA4BDA", timestamp=ts1,
        )
        msg2 = AdsbMessage(
            icao="7C4B4C", callsign="QFA456", latitude=-34.01, longitude=138.01,
            altitude_ft=35000, groundspeed=450.0, track=180.0, vertical_rate=0,
            raw_hex="8D4840D6202CC371C32CE0576098", timestamp=ts2,
        )

        sub = AdsbSubscriber(broadcast_fn=broadcast_spy)

        hex_strings = [
            "8D406B902015A678D4D220AA4BDA",
            "8D4840D6202CC371C32CE0576098",
        ]
        msgs = [msg1, msg2]

        def fake_demodulate(iq_chunk):
            return [hex_strings.pop(0)] if hex_strings else []

        def fake_decode(raw_hex):
            return msgs.pop(0) if msgs else None

        sub._demodulator.demodulate = fake_demodulate
        sub._decoder.decode = fake_decode

        iq_chunk = np.zeros(1024, dtype=np.complex64)
        sub.receive(iq_chunk, AU_ADSB_FREQUENCY_HZ, 2_000_000.0)
        sub.receive(iq_chunk, AU_ADSB_FREQUENCY_HZ, 2_000_000.0)

        sub.start()
        time.sleep(0.3)
        sub.stop()

        assert len(broadcast_messages) >= 2
        assert broadcast_messages[1].delta_r_deg_per_sec is not None
        assert isinstance(broadcast_messages[1].delta_r_deg_per_sec, float)

    def test_stop_flush_attaches_bearing_report(self):
        """stop() attaches bearing_deg to messages harvested by flush()."""
        harvested = []
        msg = AdsbMessage(
            icao="ABC123", callsign="TEST1", latitude=-34.0, longitude=138.0,
            altitude_ft=35000, groundspeed=450.0, track=180.0, vertical_rate=0,
            raw_hex="8D406B902015A678D4D220AA4BDA",
        )
        sub = AdsbSubscriber(broadcast_fn=lambda m: harvested.append(m))
        sub._decoder.flush = lambda: [msg]
        sub.stop()
        assert len(harvested) == 1
        assert harvested[0].bearing_deg is not None

    def test_decode_loop_attaches_range_nm(self):
        """A successful decode attaches range_nm onto the message."""
        broadcast_messages = []

        def broadcast_spy(msg):
            broadcast_messages.append(msg)

        msg = AdsbMessage(
            icao="7C4B4C", callsign="QFA456", latitude=-34.0, longitude=138.0,
            altitude_ft=35000, groundspeed=450.0, track=180.0, vertical_rate=0,
            raw_hex="8D406B902015A678D4D220AA4BDA",
        )

        sub = AdsbSubscriber(broadcast_fn=broadcast_spy)

        def fake_demodulate(iq_chunk):
            return ["8D406B902015A678D4D220AA4BDA"]

        def fake_decode(raw_hex):
            return msg

        sub._demodulator.demodulate = fake_demodulate
        sub._decoder.decode = fake_decode

        iq_chunk = np.zeros(1024, dtype=np.complex64)
        sub.receive(iq_chunk, AU_ADSB_FREQUENCY_HZ, 2_000_000.0)

        sub.start()
        time.sleep(0.2)
        sub.stop()

        assert len(broadcast_messages) >= 1
        assert isinstance(broadcast_messages[0].range_nm, float)
        assert broadcast_messages[0].range_nm > 0.0

    def test_stop_attaches_range_nm_on_harvested_messages(self):
        """stop() attaches range_nm to messages harvested by flush()."""
        harvested = []
        msg = AdsbMessage(
            icao="ABC123", callsign="TEST1", latitude=-34.0, longitude=138.0,
            altitude_ft=35000, groundspeed=450.0, track=180.0, vertical_rate=0,
            raw_hex="8D406B902015A678D4D220AA4BDA",
        )
        sub = AdsbSubscriber(broadcast_fn=lambda m: harvested.append(m))
        sub._decoder.flush = lambda: [msg]
        sub.stop()
        assert len(harvested) == 1
        assert isinstance(harvested[0].range_nm, float)

    def test_decode_loop_handles_message_with_no_position(self):
        """Messages with unresolved position carry None bearing fields."""
        broadcast_messages = []

        def broadcast_spy(msg):
            broadcast_messages.append(msg)

        msg = AdsbMessage(
            icao="7C4B4C", callsign="QFA456", latitude=None, longitude=None,
            altitude_ft=35000, groundspeed=450.0, track=180.0, vertical_rate=0,
            raw_hex="8D406B902015A678D4D220AA4BDA",
        )

        sub = AdsbSubscriber(broadcast_fn=broadcast_spy)

        def fake_demodulate(iq_chunk):
            return ["8D406B902015A678D4D220AA4BDA"]

        def fake_decode(raw_hex):
            return msg

        sub._demodulator.demodulate = fake_demodulate
        sub._decoder.decode = fake_decode

        iq_chunk = np.zeros(1024, dtype=np.complex64)
        sub.receive(iq_chunk, AU_ADSB_FREQUENCY_HZ, 2_000_000.0)

        sub.start()
        time.sleep(0.2)
        sub.stop()

        assert len(broadcast_messages) >= 1
        assert broadcast_messages[0].bearing_deg is None
        assert broadcast_messages[0].delta_r_deg_per_sec is None
        assert broadcast_messages[0].range_nm is None

    def test_periodic_harvest_broadcasts_messages(self, monkeypatch):
        """Periodic harvest in _decode_loop broadcasts flush-harvested messages.

        FLUSH_INTERVAL_SEC is patched down to 0.05 s so the test does not
        need to run the loop for the real 5 s cadence.
        """
        monkeypatch.setattr("modules.adsb.subscriber.FLUSH_INTERVAL_SEC", 0.05)

        broadcast_event = threading.Event()
        broadcast_messages = []
        scan_result_messages = []

        def broadcast_spy(msg):
            broadcast_messages.append(msg)
            broadcast_event.set()

        def scan_result_spy(msg):
            scan_result_messages.append(msg)

        msg = AdsbMessage(
            icao="ABC123", callsign="TEST1", latitude=-34.0, longitude=138.0,
            altitude_ft=35000, groundspeed=450.0, track=180.0, vertical_rate=0,
            raw_hex="8D406B902015A678D4D220AA4BDA",
        )
        pending = [msg]

        sub = AdsbSubscriber(
            broadcast_fn=broadcast_spy,
            scan_result_fn=scan_result_spy,
        )
        # Return the crafted message once, then empty, so the stop() harvest
        # at teardown cannot mask whether the periodic path fired.
        sub._decoder.flush = lambda: [pending.pop(0)] if pending else []

        sub.start()
        # Broadcast must arrive while the loop is still running, i.e. via
        # the periodic harvest, not via the stop() harvest.
        fired_before_stop = broadcast_event.wait(timeout=2.0)
        sub.stop()

        assert fired_before_stop
        assert len(broadcast_messages) == 1
        assert broadcast_messages[0].icao == "ABC123"
        assert isinstance(broadcast_messages[0].bearing_deg, float)
        assert broadcast_messages[0].delta_r_deg_per_sec is None
        assert isinstance(broadcast_messages[0].range_nm, float)
        assert len(scan_result_messages) == 1
        assert scan_result_messages[0].icao == "ABC123"

    def test_periodic_harvest_does_not_fire_every_iteration(self):
        """The timer gate is real: flush is not called on every loop iteration.

        Runs the loop for ~0.4 s (several queue-timeout iterations) with the
        real 5 s FLUSH_INTERVAL_SEC and asserts flush is never called until
        stop() performs its final harvest.
        """
        flush_calls = []
        sub = AdsbSubscriber(broadcast_fn=lambda m: None)
        sub._decoder.flush = lambda: flush_calls.append(time.monotonic()) or []

        sub.start()
        time.sleep(0.4)
        assert len(flush_calls) == 0
        sub.stop()
        assert len(flush_calls) == 1

    def test_harvest_helper_matches_stop_payload_shape(self):
        """_harvest_and_broadcast() produces the same payload shape as stop().

        Calls the helper directly and asserts the identical field set the
        stop() flush tests assert against: broadcast_fn and scan_result_fn
        both invoked, bearing_deg / delta_r_deg_per_sec / range_nm attached.
        """
        broadcast_messages = []
        scan_result_messages = []

        def broadcast_spy(msg):
            broadcast_messages.append(msg)

        def scan_result_spy(msg):
            scan_result_messages.append(msg)

        msg = AdsbMessage(
            icao="ABC123", callsign="TEST1", latitude=-34.0, longitude=138.0,
            altitude_ft=35000, groundspeed=450.0, track=180.0, vertical_rate=0,
            raw_hex="8D406B902015A678D4D220AA4BDA",
        )

        sub = AdsbSubscriber(
            broadcast_fn=broadcast_spy,
            scan_result_fn=scan_result_spy,
        )
        sub._decoder.flush = lambda: [msg]

        sub._harvest_and_broadcast()

        assert len(broadcast_messages) == 1
        assert broadcast_messages[0].icao == "ABC123"
        assert isinstance(broadcast_messages[0].bearing_deg, float)
        assert broadcast_messages[0].delta_r_deg_per_sec is None
        assert isinstance(broadcast_messages[0].range_nm, float)
        assert len(scan_result_messages) == 1
        assert scan_result_messages[0] is broadcast_messages[0]
