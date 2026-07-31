"""AdsbSubscriber — IQ bus subscriber with decode thread lifecycle.

Receives raw IQ chunks from ScanRunner, demodulates and decodes them
in a background daemon thread, and broadcasts decoded aircraft messages.

Legal: passive receive only.  Radiocommunications Act 1992 (Cth).
Jurisdiction: AU / SA.  Authority: ACMA.
"""

import logging
import queue
import threading
import time
from collections.abc import Callable

import numpy as np

from modules.adsb.constants import AU_ADSB_FREQUENCY_HZ, FREQ_TOLERANCE_HZ
from modules.adsb.demodulator import AdsbDemodulator
from modules.adsb.decoder import FLUSH_INTERVAL_SEC, AdsbDecoder
from modules.adsb.bearing_tracker import BearingTracker

logger = logging.getLogger(__name__)


class AdsbSubscriber:
    """Subscriber on the shared IQ bus for ADS-B decoding."""

    def __init__(self, broadcast_fn: Callable, scan_result_fn: Callable | None = None) -> None:
        """Initialise the subscriber with broadcast and scan result callbacks.

        Args:
            broadcast_fn: Called with an ``AdsbMessage`` when a frame
                          is successfully decoded.
            scan_result_fn: Optional callback for emitting scan_result events
                           with confirmed decoder output (confidence=1.0).
        """
        self._broadcast_fn = broadcast_fn
        self._scan_result_fn = scan_result_fn
        self._queue: queue.Queue = queue.Queue(maxsize=64)
        self._thread: threading.Thread | None = None
        self._running = False
        self._demodulator = AdsbDemodulator()
        self._decoder = AdsbDecoder()
        self._bearing_tracker = BearingTracker()
        self._last_harvest_ts: float = time.monotonic()

    def receive(
        self,
        iq_chunk: np.ndarray,
        freq_hz: float,
        sample_rate_hz: float,
    ) -> None:
        """Accept an IQ chunk if frequency is near the AU ADS-B frequency.

        Drops the chunk silently if the internal queue is full.

        Args:
            iq_chunk: Complex64 IQ samples.
            freq_hz: Centre frequency of the chunk (Hz).
            sample_rate_hz: Sample rate of the chunk (Hz).
        """
        if abs(freq_hz - AU_ADSB_FREQUENCY_HZ) <= FREQ_TOLERANCE_HZ:
            try:
                self._queue.put_nowait((iq_chunk, freq_hz, sample_rate_hz))
            except queue.Full:
                logger.debug("ADS-B queue full — dropping chunk")

    def start(self) -> None:
        """Start the daemon decode thread."""
        self._running = True
        self._thread = threading.Thread(target=self._decode_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Signal the decode thread to stop and wait for it to exit.

        Calls ``flush()`` on the decoder to harvest any bootstrap-held
        ADS-B CPR positions that have accumulated but not yet been
        emitted, and broadcasts each harvested message via
        ``broadcast_fn`` and ``scan_result_fn`` before stopping.
        """
        self._harvest_and_broadcast()
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    def _harvest_and_broadcast(self) -> None:
        """Flush the decoder and broadcast each harvested message.

        Shared by ``stop()`` (final harvest at shutdown) and by the
        periodic harvest inside ``_decode_loop()`` (live harvest of
        positions that pyModeS retro-fills into its bootstrap dicts).
        Both paths must produce the identical payload shape: bearing
        tracker update first, then attach bearing/range fields, then
        broadcast and scan_result callbacks.
        """
        harvested = self._decoder.flush()
        for msg in harvested:
            report = self._bearing_tracker.update(msg)
            msg.bearing_deg = report.bearing_deg if report else None
            msg.delta_r_deg_per_sec = report.delta_r_deg_per_sec if report else None
            msg.range_nm = report.range_nm if report else None
            if self._broadcast_fn is not None:
                self._broadcast_fn(msg)
            if self._scan_result_fn is not None:
                self._scan_result_fn(msg)

    def _decode_loop(self) -> None:
        """Background loop: fetch IQ chunks, demodulate, decode, broadcast.

        For each successfully decoded ADS-B frame, calls ``broadcast_fn``
        to emit the ``adsb_aircraft`` event and ``scan_result_fn`` (if
        provided) to emit a ground-truth ``scan_result`` event that
        bypasses the LLM pipeline (confidence = 1.0).
        """
        while self._running:
            now = time.monotonic()
            if now - self._last_harvest_ts >= FLUSH_INTERVAL_SEC:
                try:
                    self._harvest_and_broadcast()
                except Exception:
                    logger.debug("ADS-B periodic harvest failed", exc_info=True)
                # Reset outside the try so a continuously failing harvest
                # retries on the FLUSH_INTERVAL_SEC cadence, not every iteration.
                self._last_harvest_ts = now
            try:
                iq_chunk, freq_hz, sample_rate_hz = self._queue.get(timeout=0.1)
            except queue.Empty:
                continue

            try:
                hex_strings = self._demodulator.demodulate(iq_chunk)
                for raw_hex in hex_strings:
                    msg = self._decoder.decode(raw_hex)
                    if msg is not None:
                        logger.info(
                            "ADS-B decoded: ICAO %s callsign %s alt %s",
                            msg.icao,
                            msg.callsign,
                            msg.altitude_ft,
                        )
                        report = self._bearing_tracker.update(msg)
                        msg.bearing_deg = report.bearing_deg if report else None
                        msg.delta_r_deg_per_sec = report.delta_r_deg_per_sec if report else None
                        msg.range_nm = report.range_nm if report else None
                        if self._broadcast_fn is not None:
                            self._broadcast_fn(msg)
                        if self._scan_result_fn is not None:
                            self._scan_result_fn(msg)
            except Exception:
                logger.debug("ADS-B decode failed", exc_info=True)
