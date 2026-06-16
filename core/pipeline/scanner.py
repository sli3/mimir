import logging
import queue
import threading
import time
from datetime import datetime

from core.config.loader import MimirConfig
from core.pipeline.features import fingerprint_spectrum
from core.pipeline.fft import compute_psd
from core.pipeline.scan_result import ScanResult
from dashboard.server import record_hw_error
from llm.acma_reference import AcmaReference

logger = logging.getLogger(__name__)

_SAMPLE_RATE_HZ = 2_000_000


class ScanRunner:
    """Two-thread scanner: scan loop captures IQ and queues fingerprints;
    AI loop classifies the freshest sample via LLM.

    Queue behaviour ("latest wins"):
    The scan loop drains the queue before every insert so the AI loop
    always sees the most recent scan. At steady state the queue holds
    0–1 items.

    Stats counters:
    _scan_count_since_llm — increments once per scan cycle; snapshot
    into _last_backlog when the AI loop picks up an item, then reset.
    """
    def __init__(self, device, embedder, store, classifier, config: MimirConfig) -> None:
        self._device = device
        self._embedder = embedder
        self._store = store
        self._classifier = classifier
        self._config = config
        self._queue: queue.Queue = queue.Queue(maxsize=config.queue_maxsize)
        self._running = False
        self._scan_thread: threading.Thread | None = None
        self._ai_thread: threading.Thread | None = None
        self._broadcast_fn = None
        self._broadcast_spectrum_fn = None
        self._acma_reference = AcmaReference()
        self._scan_count: int = 0
        self._scan_count_since_llm: int = 0
        self._last_backlog: int = 0
        self._llm_call_count: int = 0
        self._active_freq_hz: float = 0.0
        self._last_llm_ms: float = 0.0
        self._focus_freq_hz: float = config.frequencies_hz[0]
        self._focus_lock: threading.Lock = threading.Lock()
        self._iq_subscribers: list = []

    def run(self) -> None:
        self._running = True
        self._scan_thread = threading.Thread(target=self._scan_loop, daemon=True)
        self._ai_thread = threading.Thread(target=self._ai_loop, daemon=True)
        self._scan_thread.start()
        self._ai_thread.start()
        self._scan_thread.join()
        self._ai_thread.join()

    def stop(self) -> None:
        self._running = False

    def get_stats(self) -> dict:
        """Return current scanner runtime statistics.

        Keys:
            active_frequency_hz : float  — current SDR center frequency
            scan_count          : int    — total scan cycles completed
            queue_depth         : int    — current AI queue depth (0–1)
            last_backlog        : int    — scan cycles since last LLM pickup
            llm_call_count      : int    — total successful LLM classifications
            last_llm_ms         : float  — milliseconds of last LLM inference
        """
        return {
            "active_frequency_hz": self._active_freq_hz,
            "scan_count": self._scan_count,
            "queue_depth": self._queue.qsize(),
            "last_backlog": self._last_backlog,
            "llm_call_count": self._llm_call_count,
            "last_llm_ms": self._last_llm_ms,
        }

    def set_focus_frequency(self, freq_hz: float) -> None:
        """Change the focus frequency and flush stale queue items."""
        with self._focus_lock:
            self._focus_freq_hz = freq_hz
            q = self._queue
            while True:
                try:
                    q.get_nowait()
                except queue.Empty:
                    break
        logger.info("Focus changed to %.3f MHz — queue flushed", freq_hz / 1e6)

    def register_iq_subscriber(self, subscriber) -> None:
        """Register an IQ subscriber that receives raw samples before FFT."""
        self._iq_subscribers.append(subscriber)

    def _scan_loop(self) -> None:
        """Capture IQ samples, compute PSD, and broadcast spectrum to the dashboard.

        Runs continuously while ``_running`` is True. Each iteration:
          1. Tunes the SDR to the current focus frequency.
          2. Reads raw IQ samples from the device.
          3. Passes samples to any registered IQ subscribers (e.g. ACARS, AIS, ADS-B decoders).
          4. Runs FFT to produce a PSD.
          5. Broadcasts the PSD to the dashboard for the waterfall display — this happens
             immediately after FFT, independent of the AI classification loop, so the
             waterfall updates at the full scan rate regardless of LLM latency.
          6. Computes a fingerprint vector and queues it for the AI loop.

        The spectrum broadcast (step 5) is wrapped in its own try/except so that a
        broadcast failure (e.g. no connected dashboard) does not prevent the scan
        loop from continuing or the fingerprint from reaching the AI pipeline.

        "Latest wins" queue behaviour:
        Before inserting a fingerprint, the queue is drained completely. Because LLM
        inference (~2500 ms) is slower than the scan rate (~260 ms), a FIFO queue would
        saturate permanently and the AI loop would classify scans that are tens of
        seconds old. The drain ensures the AI loop always sees the freshest sample.
        At steady state the queue holds 0–1 items (the most recent scan).
        """
    
        config = self._config
        device = self._device
        embedder = self._embedder
        q = self._queue

        while self._running:
            if not self._running:
                return
            try:
                with self._focus_lock:
                    freq_hz = self._focus_freq_hz
                device.set_center_frequency(freq_hz)
                self._active_freq_hz = freq_hz
                try:
                    samples = device.read_samples(config.num_samples)
                except Exception:
                    record_hw_error()
                    raise
                for subscriber in self._iq_subscribers:
                    subscriber.receive(samples, freq_hz, _SAMPLE_RATE_HZ)
                psd = compute_psd(samples, _SAMPLE_RATE_HZ, freq_hz)
                if self._broadcast_spectrum_fn is not None:
                    # Isolate spectrum broadcast failures so they never block the
                    # scan loop or prevent fingerprints reaching the AI pipeline.
                    try:
                        self._broadcast_spectrum_fn(
                            psd["psd_db"],
                            freq_hz,
                            float(psd["frequencies_hz"][0]),
                            float(psd["frequencies_hz"][-1]),
                        )
                    except Exception:
                        logger.exception(
                            "Spectrum broadcast failed at %.3f MHz",
                            freq_hz / 1e6,
                        )
                fingerprint = fingerprint_spectrum(psd)
                vector = embedder.embed(fingerprint)
                # "Latest wins" — drain stale items before inserting so the AI loop
                # always classifies the freshest scan, not a backlog seconds old.
                # Safe: _scan_loop is the only producer; after drain, queue is empty,
                # so put_nowait always succeeds without raising queue.Full.
                # Note: set_focus_frequency() also drains this queue (consumer-only),
                # which is safe because both paths only remove items.
                while True:
                    try:
                        q.get_nowait()
                    except queue.Empty:
                        break
                q.put_nowait({
                    "freq_hz": freq_hz,
                    "fingerprint": fingerprint,
                    "vector": vector,
                    "psd_db": psd["psd_db"],
                })
                self._scan_count_since_llm += 1
                time.sleep(config.dwell_time_sec)
                self._scan_count += 1
            except Exception:
                logger.exception("Scan loop error at %.3f MHz", freq_hz / 1e6)

    def _ai_loop(self) -> None:
        q = self._queue
        while self._running:
            try:
                item = q.get(timeout=1.0)
            except queue.Empty:
                continue

            # Snapshot scan cycles since last LLM pickup, then reset.
            # NOTE: Not atomic — _scan_loop may increment between snapshot
            # and reset, losing at most 1 count. Acceptable for a display metric.
            self._last_backlog = self._scan_count_since_llm
            self._scan_count_since_llm = 0

            try:
                neighbours = self._store.query(item["vector"], n_results=5)
                neighbours_list = [
                    {"label": m["label"], "distance": d}
                    for m, d in zip(neighbours["metadatas"][0],
                                    neighbours["distances"][0])
                ]
                chroma_distance = neighbours_list[0]["distance"] if neighbours_list else None
                item["fingerprint"]["chroma_distance"] = chroma_distance
                acma_allocations = self._acma_reference.lookup(
                    item["fingerprint"].get("center_freq_hz", 0)
                )
                t0 = time.time()
                result = self._classifier.classify(
                    item["fingerprint"],
                    neighbours_list,
                    acma_allocations=acma_allocations,
                )
                self._llm_call_count += 1
                self._last_llm_ms = (time.time() - t0) * 1000.0
                scan_result = ScanResult(
                    timestamp=datetime.now().isoformat(),
                    center_freq_hz=item["freq_hz"],
                    fingerprint=item["fingerprint"],
                    classification=result,
                    psd_db=item.get("psd_db"),
                )
                self._emit_result(scan_result)
            except Exception:
                logger.exception("AI loop error")

    def _emit_result(self, scan_result: ScanResult) -> None:
        """Print the classification result to the terminal and broadcast ``scan_result`` to the dashboard.

        Called by the AI loop after the LLM classifier produces a result. Emits
        the ``scan_result`` SocketIO event (which carries classification data,
        fingerprint fields, and PSD) to all connected browsers. The spectrum
        waterfall broadcast is NOT done here — it is done in ``_scan_loop``
        immediately after FFT so that waterfall updates are not gated by LLM
        inference time.
        """
        ts = scan_result.timestamp[11:19]
        freq_mhz = scan_result.center_freq_hz / 1e6
        cls = scan_result.classification
        confidence = cls.confidence
        score = cls.confidence_score
        signal_type = cls.signal_type
        au_legal = cls.au_legal_status

        if confidence == "high":
            colour = "\033[92m"
        elif confidence == "medium":
            colour = "\033[93m"
        else:
            colour = "\033[91m"
        reset = "\033[0m"

        print(
            f"{colour}[{ts}] {freq_mhz:10.3f} MHz  │ "
            f"{signal_type:<15} │ {confidence:<6} {score:.2f} │ "
            f"{au_legal}{reset}"
        )

        if self._broadcast_fn is not None:
            self._broadcast_fn(scan_result)
