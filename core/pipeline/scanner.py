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
        self._active_freq_hz: float = 0.0
        self._last_llm_ms: float = 0.0

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
        """Return current scanner runtime statistics."""
        return {
            "active_frequency_hz": self._active_freq_hz,
            "scan_count": self._scan_count,
            "queue_depth": self._queue.qsize(),
            "last_llm_ms": self._last_llm_ms,
        }

    def _scan_loop(self) -> None:
        config = self._config
        device = self._device
        embedder = self._embedder
        q = self._queue

        while self._running:
            for freq_hz in config.frequencies_hz:
                if not self._running:
                    return
                try:
                    device.set_center_frequency(freq_hz)
                    self._active_freq_hz = freq_hz
                    try:
                        samples = device.read_samples(config.num_samples)
                    except Exception:
                        record_hw_error()
                        raise
                    psd = compute_psd(samples, _SAMPLE_RATE_HZ, freq_hz)
                    fingerprint = fingerprint_spectrum(psd)
                    vector = embedder.embed(fingerprint)
                    try:
                        q.put_nowait({
                            "freq_hz": freq_hz,
                            "fingerprint": fingerprint,
                            "vector": vector,
                            "psd_db": psd["psd_db"],
                        })
                    except queue.Full:
                        logger.warning(
                            "Queue full — fingerprint dropped (AI loop busy) "
                            "at %.3f MHz",
                            freq_hz / 1e6,
                        )
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

            try:
                neighbours = self._store.query(item["vector"], n_results=5)
                neighbours_list = [
                    {"label": m["label"], "distance": d}
                    for m, d in zip(neighbours["metadatas"][0],
                                    neighbours["distances"][0])
                ]
                acma_allocations = self._acma_reference.lookup(
                    item["fingerprint"].get("center_freq_hz", 0)
                )
                t0 = time.time()
                result = self._classifier.classify(
                    item["fingerprint"],
                    neighbours_list,
                    acma_allocations=acma_allocations,
                )
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

        if self._broadcast_spectrum_fn is not None:
            self._broadcast_spectrum_fn(
                scan_result.psd_db,
                scan_result.center_freq_hz,
                scan_result.center_freq_hz - 1_000_000,
                scan_result.center_freq_hz + 1_000_000,
            )
