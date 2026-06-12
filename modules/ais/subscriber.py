"""AisSubscriber — IQ bus subscriber with decode thread lifecycle.

Receives raw IQ chunks from ScanRunner, demodulates and decodes them
in a background daemon thread, and broadcasts completed messages.

Legal: passive receive only.  Radiocommunications Act 1992 (Cth).
Jurisdiction: AU / SA.  Authority: ACMA.
"""

import logging
import queue
import threading

import numpy as np

from modules.ais.constants import AU_AIS_CENTRE_FREQ_HZ, FREQ_TOLERANCE_HZ
from modules.ais.demodulator import AisDemodulator
from modules.ais.decoder import AisDecoder

logger = logging.getLogger(__name__)


class AisSubscriber:
    """Subscriber on the shared IQ bus for AIS decoding."""

    def __init__(self, broadcast_fn: callable) -> None:
        """Initialise the subscriber with a broadcast callback.

        Args:
            broadcast_fn: Called with an ``AisMessage`` when a frame
                          is successfully decoded.
        """
        self._broadcast_fn = broadcast_fn
        self._queue: queue.Queue = queue.Queue(maxsize=32)
        self._thread: threading.Thread | None = None
        self._running = False
        self._demodulator = AisDemodulator()
        self._decoder = AisDecoder()

    def receive(
        self,
        iq_chunk: np.ndarray,
        freq_hz: float,
        sample_rate_hz: float,
    ) -> None:
        """Accept an IQ chunk if frequency is near the AU AIS centre frequency.

        Drops the chunk silently if the internal queue is full.

        Args:
            iq_chunk: Complex64 IQ samples.
            freq_hz: Centre frequency of the chunk (Hz).
            sample_rate_hz: Sample rate of the chunk (Hz).
        """
        if abs(freq_hz - AU_AIS_CENTRE_FREQ_HZ) <= FREQ_TOLERANCE_HZ:
            try:
                self._queue.put_nowait((iq_chunk, freq_hz, sample_rate_hz))
            except queue.Full:
                logger.debug("AIS queue full — dropping chunk")

    def start(self) -> None:
        """Start the daemon decode thread."""
        self._running = True
        self._thread = threading.Thread(target=self._decode_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Signal the decode thread to stop and wait for it to exit."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    def _decode_loop(self) -> None:
        """Background loop: fetch IQ chunks, demodulate, decode, broadcast."""
        while self._running:
            try:
                iq_chunk, freq_hz, sample_rate_hz = self._queue.get(timeout=1.0)
            except queue.Empty:
                continue

            try:
                payloads = self._demodulator.demodulate(iq_chunk, sample_rate_hz)
                for payload, channel in payloads:
                    msg = self._decoder.decode(payload, channel)
                    if msg is not None:
                        msg.freq_hz = freq_hz
                        logger.info(
                            "AIS decoded: MMSI %s type %s ch %s",
                            msg.mmsi,
                            msg.msg_type,
                            msg.channel,
                        )
                        if self._broadcast_fn is not None:
                            self._broadcast_fn(msg)
            except Exception:
                logger.debug("AIS decode failed", exc_info=True)
