"""AcarsSubscriber — IQ bus subscriber with decode thread lifecycle.

Receives raw IQ chunks from ScanRunner, demodulates and decodes them
in a background daemon thread, and broadcasts completed messages.

Legal: passive receive only.  Radiocommunications Act 1992 (Cth).
Jurisdiction: AU / SA.  Authority: ACMA.
"""

import logging
import queue
import threading

import numpy as np

from modules.acars.constants import AU_ACARS_FREQUENCIES_HZ, FREQ_TOLERANCE_HZ
from modules.acars.demodulator import AcarsDemodulator
from modules.acars.decoder import AcarsDecoder

logger = logging.getLogger(__name__)


class AcarsSubscriber:
    """Subscriber on the shared IQ bus for ACARS decoding."""

    def __init__(self, broadcast_fn: callable) -> None:
        """Initialise the subscriber with a broadcast callback.

        Args:
            broadcast_fn: Called with an ``AcarsMessage`` when a frame
                          is successfully decoded.
        """
        self._broadcast_fn = broadcast_fn
        self._queue: queue.Queue = queue.Queue(maxsize=32)
        self._thread: threading.Thread | None = None
        self._running = False
        self._demodulator = AcarsDemodulator()
        self._decoder = AcarsDecoder()

    def receive(
        self,
        iq_chunk: np.ndarray,
        freq_hz: float,
        sample_rate_hz: float,
    ) -> None:
        """Accept an IQ chunk if frequency is near an AU ACARS frequency.

        Drops the chunk silently if the internal queue is full.

        Args:
            iq_chunk: Complex64 IQ samples.
            freq_hz: Centre frequency of the chunk (Hz).
            sample_rate_hz: Sample rate of the chunk (Hz).
        """
        for acars_freq in AU_ACARS_FREQUENCIES_HZ:
            if abs(freq_hz - acars_freq) <= FREQ_TOLERANCE_HZ:
                try:
                    self._queue.put_nowait((iq_chunk, freq_hz, sample_rate_hz))
                except queue.Full:
                    logger.debug("ACARS queue full — dropping chunk")
                return

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
                envelope = self._demodulator.envelope_detect(iq_chunk)
                audio = self._demodulator.decimate_to_audio(
                    envelope, sample_rate_hz
                )
                tones = self._demodulator.detect_tones(audio)
                bits = self._demodulator.nrzi_decode(tones)
                start_idx = self._decoder.find_frame_start(bits)

                if start_idx is not None:
                    bytes_ = self._decoder.bits_to_bytes(bits[start_idx:])
                    msg = self._decoder.parse_frame(bytes_)
                    if msg is not None:
                        msg.freq_hz = freq_hz
                        logger.info(
                            "ACARS decoded: %s %s %s",
                            msg.registration,
                            msg.label,
                            msg.text,
                        )
                        if self._broadcast_fn is not None:
                            self._broadcast_fn(msg)
            except Exception:
                logger.debug("ACARS decode failed", exc_info=True)
