"""AdsbSubscriber — IQ bus subscriber with decode thread lifecycle.

Receives raw IQ chunks from ScanRunner, demodulates and decodes them
in a background daemon thread, and broadcasts decoded aircraft messages.

Legal: passive receive only.  Radiocommunications Act 1992 (Cth).
Jurisdiction: AU / SA.  Authority: ACMA.
"""

import logging
import queue
import threading
from collections.abc import Callable

import numpy as np

from modules.adsb.constants import AU_ADSB_FREQUENCY_HZ, FREQ_TOLERANCE_HZ
from modules.adsb.demodulator import AdsbDemodulator
from modules.adsb.decoder import AdsbDecoder

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
        harvested = self._decoder.flush()
        for msg in harvested:
            if self._broadcast_fn is not None:
                self._broadcast_fn(msg)
            if self._scan_result_fn is not None:
                self._scan_result_fn(msg)
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    def _decode_loop(self) -> None:
        """Background loop: fetch IQ chunks, demodulate, decode, broadcast.

        For each successfully decoded ADS-B frame, calls ``broadcast_fn``
        to emit the ``adsb_aircraft`` event and ``scan_result_fn`` (if
        provided) to emit a ground-truth ``scan_result`` event that
        bypasses the LLM pipeline (confidence = 1.0).
        """
        while self._running:
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
                        if self._broadcast_fn is not None:
                            self._broadcast_fn(msg)
                        if self._scan_result_fn is not None:
                            self._scan_result_fn(msg)
            except Exception:
                logger.debug("ADS-B decode failed", exc_info=True)
