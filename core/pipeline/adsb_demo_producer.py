"""
core/pipeline/adsb_demo_producer.py — Demo-mode ADS-B decode producer

Legal: Receive-only. Radiocommunications Act 1992 (Cth).
       No transmission. Jurisdiction: AU/SA. Authority: ACMA.

WHAT THIS FILE DOES
-------------------
A second, independent daemon-thread producer that replays a single
pre-recorded ADS-B SigMF capture and feeds the raw IQ directly into
``AdsbSubscriber.receive()``. This gives the ADS-B decode path (RAW
DECODE, FRAME INSPECTOR and the ``/radar`` aircraft table) live data
during ``--demo`` mode, while the existing ``DemoProducer`` continues
to drive the fingerprint/classify AI pipeline unchanged.

The two producers are deliberately decoupled:

* ``DemoProducer`` reads .sigmf files, fingerprints each chunk, embeds
  it, and pushes the same queue item shape that ``ScanRunner._scan_loop``
  produces. It drives SIGNAL HISTORY and AI REASONING.
* ``AdsbDemoProducer`` reads raw IQ from a separate SigMF file and
  calls ``AdsbSubscriber.receive(iq_chunk, freq_hz, sample_rate_hz)``
  directly. It drives the real-time ADS-B bit-level decoder path.

This producer owns NO device, makes NO network calls, and does NOT write
to the vector store. It only reads an existing file and feeds the
existing decode subscriber.

LOOP BEHAVIOUR
--------------
The file is replayed from the beginning indefinitely until ``stop()`` is
called. Each chunk is preceded by ``ADSB_DEMO_CHUNK_INTERVAL_SEC`` so the
replay paces itself at the real-time rate implied by the file's sample
rate (2 MSa/s for the supported ADS-B capture). This is NOT the
fingerprint path's ``DEMO_CHUNK_INTERVAL_SEC=0.05``; that constant is
visual-snappiness tuned for the AI panel and unrelated to ADS-B timing.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

import numpy as np

from core.pipeline.replay import ReplayFileError, _load_sigmf
from modules.adsb.constants import AU_ADSB_FREQUENCY_HZ, FREQ_TOLERANCE_HZ
from modules.adsb.subscriber import AdsbSubscriber

logger = logging.getLogger(__name__)


# Chunk size for the ADS-B demo producer. Matches the
# mimir:fingerprint_sequence chunk size used by the fingerprint path for
# consistency and is well above the 240-sample ADS-B message length.
ADSB_DEMO_CHUNK_SAMPLES: int = 131_072

# Real-time pacing for a 2 MSa/s ADS-B capture. This value is derived
# directly from ADSB_DEMO_CHUNK_SAMPLES / 2_000_000 so the replay
# consumes samples at the same rate they were recorded. The constructor
# validates that the supplied SigMF file is exactly 2 MSa/s, so the
# chunk size and interval are internally consistent. This is NOT
# DEMO_CHUNK_INTERVAL_SEC=0.05 on the fingerprint path; that constant
# is tuned for visual snappiness in the AI panel and has no relation
# to ADS-B sample timing.
ADSB_DEMO_CHUNK_INTERVAL_SEC: float = ADSB_DEMO_CHUNK_SAMPLES / 2_000_000.0


class AdsbDemoProducer:
    """Daemon-thread producer that replays an ADS-B SigMF file into the
    existing ``AdsbSubscriber`` decode path."""

    def __init__(self, sigmf_path: Path, adsb_subscriber: AdsbSubscriber) -> None:
        """Initialise the ADS-B demo producer.

        Args:
            sigmf_path: Path to a .sigmf-meta file. Must exist, must be
                parseable as SigMF, must have ``core:sample_rate`` of
                exactly 2_000_000 Hz, and must have ``core:frequency``
                within ``FREQ_TOLERANCE_HZ`` of ``AU_ADSB_FREQUENCY_HZ``.
            adsb_subscriber: The ``AdsbSubscriber`` instance whose
                ``receive()`` method will be fed with each chunk.

        Raises:
            FileNotFoundError: If ``sigmf_path`` does not exist.
            ReplayFileError: If the file is malformed, has the wrong
                sample rate, or is tuned outside the ADS-B tolerance.
        """
        path = Path(sigmf_path)
        if not path.exists():
            raise FileNotFoundError(f"ADS-B demo file not found: {path}")

        meta = _load_sigmf(path)

        sample_rate_hz = float(meta.sample_rate)
        if sample_rate_hz != 2_000_000.0:
            raise ReplayFileError(
                f"{path}: sample_rate={sample_rate_hz:.0f} Hz; ADS-B "
                f"demodulator requires exactly 2_000_000 Hz (2 MSa/s). "
                f"Re-capture at 2 MSa/s or use a different file."
            )

        captures = meta.get_captures()
        core_freq = captures[0].get("core:frequency") if captures else None
        if core_freq is None:
            raise ReplayFileError(
                f"{path}: SigMF metadata has no core:frequency capture field"
            )
        core_freq_hz = float(core_freq)
        if abs(core_freq_hz - AU_ADSB_FREQUENCY_HZ) > FREQ_TOLERANCE_HZ:
            raise ReplayFileError(
                f"{path}: core:frequency={core_freq_hz / 1e6:.2f} MHz is "
                f"outside the ADS-B tolerance: expected within "
                f"{FREQ_TOLERANCE_HZ / 1e3:.0f} kHz of "
                f"{AU_ADSB_FREQUENCY_HZ / 1e6:.2f} MHz"
            )

        total_samples = int(meta.sample_count or 0)
        if total_samples <= 0:
            raise ReplayFileError(
                f"{path}: SigMF metadata reports zero samples, .sigmf-data "
                f"missing or empty"
            )

        self._meta = meta
        self._adsb_subscriber = adsb_subscriber
        self._core_freq_hz = core_freq_hz
        self._sample_rate_hz = sample_rate_hz
        self._total_samples = total_samples
        self._stop_event: threading.Event = threading.Event()
        self._thread: threading.Thread | None = None
        self._started: bool = False

    def start(self) -> None:
        """Spawn the daemon replay thread. Idempotent: second call is a no-op."""
        if self._started:
            return
        self._started = True
        self._thread = threading.Thread(
            target=self._run,
            daemon=True,
            name="adsb-demo-producer",
        )
        self._thread.start()

    def stop(self) -> None:
        """Signal the replay thread to exit at the next safe point."""
        self._stop_event.set()

    def join(self, timeout: float | None = None) -> None:
        """Wait for the daemon replay thread to finish.

        Mirrors ``threading.Thread.join`` for symmetry with the cleanup
        pattern used in ``scan.py``.
        """
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    def _run(self) -> None:
        """Thread body: loop through the file indefinitely until stopped."""
        meta = self._meta
        subscriber = self._adsb_subscriber
        chunk_samples = ADSB_DEMO_CHUNK_SAMPLES
        interval = ADSB_DEMO_CHUNK_INTERVAL_SEC
        total_samples = self._total_samples
        start_index = 0

        while not self._stop_event.is_set():
            # Wrap deterministically at EOF so ``read_samples`` is never
            # asked for samples beyond the file. ``sigmf 1.11.1`` raises
            # IOError at EOF rather than returning a short array.
            if start_index + chunk_samples > total_samples:
                logger.info("AdsbDemoProducer: wrapping to start_index=0")
                start_index = 0
                time.sleep(interval)
                continue

            try:
                samples = meta.read_samples(
                    start_index=start_index,
                    count=chunk_samples,
                )
            except Exception:
                logger.exception(
                    "AdsbDemoProducer failed to read samples at start_index=%s",
                    start_index,
                )
                # Back off and restart on a genuine I/O error (corrupt
                # data file, permissions), then try from the beginning.
                time.sleep(interval)
                start_index = 0
                continue

            # A short read after a successful call means the data file was
            # truncated after the metadata was loaded. Restart from the
            # beginning rather than spinning.
            if len(samples) < chunk_samples:
                logger.info(
                    "AdsbDemoProducer: short read at EOF, restarting from "
                    "start_index=0"
                )
                time.sleep(interval)
                start_index = 0
                continue

            # Pace at real-time regardless of how fast the disk read was.
            time.sleep(interval)

            try:
                subscriber.receive(
                    np.asarray(samples, dtype=np.complex64),
                    self._core_freq_hz,
                    self._sample_rate_hz,
                )
            except Exception:
                logger.exception("AdsbDemoProducer failed to deliver chunk")

            start_index += len(samples)

        logger.info("AdsbDemoProducer stopped.")
