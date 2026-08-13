import logging
import queue
import threading
import time
from datetime import datetime

from core.config.loader import MimirConfig
from core.device.profiles import DEVICE_PROFILES
import core.pipeline.features as features
from core.pipeline.capture import save_capture
from core.pipeline.fft import compute_psd
from core.pipeline.scan_result import ScanResult
from dashboard.server import record_hw_error
import dashboard.shared_state as shared_state
from dashboard.shared_state import (
    TRIGGER_ARMABLE_BANDS,
    band_key_for_freq,
    get_last_trigger_snr,
    is_trigger_armed,
    set_last_trigger_snr,
)
from llm.acma_reference import AcmaReference

logger = logging.getLogger(__name__)

_SAMPLE_RATE_HZ = 2_000_000


def _should_fire_trigger(
    prev_snr: float | None,
    current_snr: float | None,
    threshold: float | None,
) -> bool:
    """Edge-detect helper for the SNR auto-capture trigger (Phase 63).

    Returns True exactly when the measured SNR has crossed the band's
    signal threshold from below to at-or-above between two consecutive
    scan cycles::

        prev_snr < threshold <= current_snr

    The strict less-than on the previous side and less-than-or-equal on
    the current side means crossing the exact threshold counts as a
    fire. This asymmetry is also the re-arm contract: once a reading at
    or above the threshold has been recorded as the previous value, the
    trigger cannot fire again until SNR first drops below the threshold
    and then rises back to or above it. A continuous strong signal
    therefore produces one capture at the rising edge, not one capture
    per scan cycle.

    Returns False whenever any input is None: prev_snr is None on the
    first cycle after startup (no previous reading, so no edge can be
    detected), current_snr is None when the fingerprint produced no SNR
    reading, and threshold is None when the band profile lacks
    signal_threshold_db. Also returns False, defensively, when threshold
    is not a real number.

    Args:
        prev_snr: SNR (dB) recorded on the previous scan cycle, or None.
        current_snr: SNR (dB) measured on the current scan cycle, or None.
        threshold: The band's signal_threshold_db, or None.

    Returns:
        True iff the SNR has just crossed the threshold from below.
    """
    if prev_snr is None or current_snr is None:
        return False
    if not isinstance(threshold, (int, float)) or isinstance(threshold, bool):
        return False
    return bool(prev_snr < threshold <= current_snr)


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
    def __init__(self, device, embedder, store, classifier, config: MimirConfig,
                 device_driver: str = "hackrf") -> None:
        """Initialise the two-thread scanner.

        The scan loop captures IQ and queues fingerprints; the AI loop classifies
        the freshest sample via LLM. Queue behaviour is "latest wins" — the scan
        loop drains the queue before every insert so the AI loop always sees the
        most recent scan. At steady state the queue holds 0–1 items.

        Stats counters:
        _scan_count_since_llm — increments once per scan cycle; snapshot
        into _last_backlog when the AI loop picks up an item, then reset.

        _last_offline_emit — timestamp of the last llm_offline emit; used to
        rate-limit offline results to one every 5 seconds to avoid SocketIO
        flooding.

        device_driver — the DEVICE_PROFILES driver key ("hackrf" / "plutosdr")
        of the attached device. Used by the scan loop's unsupported-band guard:
        non-HackRF devices with a narrower tuning range (e.g. Pluto, 325 MHz
        floor) skip focus frequencies they cannot physically receive instead
        of tuning into noise. Defaults to "hackrf", which supports every band
        and bypasses the guard entirely.

        Raises:
            ValueError: If device_driver is not a DEVICE_PROFILES key. The
                scan loop's guard calls band_supported_by_device(), which
                raises KeyError for unknown drivers; failing fast here at
                construction avoids a tight log-and-retry error loop in the
                scan thread.
        """
        if device_driver not in DEVICE_PROFILES:
            raise ValueError(
                f"Unknown device driver {device_driver!r}. "
                f"Valid drivers: {sorted(DEVICE_PROFILES.keys())}"
            )
        self._device = device
        self._device_driver = device_driver
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
        self._last_offline_emit: float = 0.0
        # Per-frequency emit throttle state: freq_hz -> (signal_type, monotonic
        # timestamp of last emit). Consulted at the top of _emit_result().
        self._last_emit_by_freq: dict[float, tuple[str, float]] = {}
        self._focus_freq_hz: float = config.frequencies_hz[0]
        self._focus_lock: threading.Lock = threading.Lock()
        self._iq_subscribers: list = []
        # Unsupported-band log gate: remembers the last frequency a skip
        # warning was logged for, so a device dwelling on an unsupported
        # band logs once per focus change rather than once per iteration.
        self._last_unsupported_log_hz: float | None = None

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
          1. Tunes the SDR to the current focus frequency (skipped if unchanged —
             see frequency cache note below).
          2. Reads raw IQ samples from the device.
          3. Passes samples to any registered IQ subscribers (e.g. ACARS, AIS, ADS-B decoders).
          4. Runs FFT to produce a PSD.
          5. Broadcasts the PSD to the dashboard for the waterfall display — this happens
             immediately after FFT, independent of the AI classification loop, so the
             waterfall updates at the full scan rate regardless of LLM latency.
          6. Reads the per-band ``signal_threshold_db`` and ``crop_half_width_hz``
             from ``shared_state.current_band`` and passes them to
             ``fingerprint_spectrum()`` so each band uses its own detection
             threshold (Phase 11) and spectral crop window (Phase 30). Computes
             a fingerprint vector and queues it for the AI loop.
          7. Checks the SNR-edge auto-capture trigger (Phase 63): if the
             current band is in TRIGGER_ARMABLE_BANDS and armed, and the
             fingerprint SNR has crossed the band's signal_threshold_db from
             below since the previous cycle, saves the raw IQ samples via
             save_capture(). A save failure is logged and swallowed so it can
             never kill the scan loop.

        Frequency cache:
        A method-local ``_last_tuned_hz`` tracks the most recently tuned frequency.
        When the focus frequency has not changed since the last iteration,
        ``device.set_center_frequency()`` is skipped entirely. This avoids redundant
        libhackrf / SoapySDR retune calls that cost ~500 ms each — significant at
        1090 MHz (ADS-B) where the same frequency is scanned repeatedly. The cache
        is reset automatically when ``set_focus_frequency()`` is called (the queue
        flush there is unrelated to this cache).

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
        _last_tuned_hz: float | None = None

        while self._running:
            if not self._running:
                return
            try:
                with self._focus_lock:
                    freq_hz = self._focus_freq_hz
                if self._device_driver != "hackrf":
                    # The raw frequency range is the authoritative gate:
                    # band_key_for_freq() resolves any unmatched freq to the
                    # NEAREST band, so a freq above the device's ceiling
                    # (e.g. 4 GHz on Pluto, whose adsb band is "supported")
                    # would pass a band-only check and tune into noise.
                    device_profile = DEVICE_PROFILES[self._device_driver]
                    in_range = (
                        device_profile["min_freq_hz"]
                        <= freq_hz
                        <= device_profile["max_freq_hz"]
                    )
                    band_key = shared_state.band_key_for_freq(freq_hz) if in_range else None
                    if not in_range or band_key is None or not shared_state.band_supported_by_device(
                        band_key, self._device_driver
                    ):
                        if freq_hz != self._last_unsupported_log_hz:
                            logger.warning(
                                "Skipping %.3f MHz — band %r is unsupported on device %r",
                                freq_hz / 1e6, band_key, self._device_driver,
                            )
                            self._last_unsupported_log_hz = freq_hz
                        time.sleep(config.dwell_time_sec)
                        continue
                    # Reset the log gate on any supported-band visit so that
                    # returning to an unsupported frequency logs again.
                    self._last_unsupported_log_hz = None
                if freq_hz != _last_tuned_hz:
                    device.set_center_frequency(freq_hz)
                    _last_tuned_hz = freq_hz
                    # Belt-and-braces discard. The settle in set_center_frequency
                    # keeps the PLL transient out of the ring buffer, but the driver
                    # may still queue a small amount at the moment the stream
                    # reactivates. Throw the first read away so the pipeline only
                    # ever fingerprints settled samples.
                    try:
                        device.read_samples(config.num_samples)
                    except Exception:
                        logger.warning(
                            "Discard read after retune to %.3f MHz failed; continuing",
                            freq_hz / 1e6,
                        )
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
                with shared_state.current_band_lock:
                    band = dict(shared_state.current_band)
                threshold = band.get(
                    "signal_threshold_db",
                    features.SIGNAL_THRESHOLD_DB,
                )
                crop_half_width_hz = band.get("crop_half_width_hz")
                burst_use_wide_window = band.get("burst_use_wide_window", False)
                fingerprint = features.fingerprint_spectrum(
                    psd,
                    signal_threshold_db=threshold,
                    crop_half_width_hz=crop_half_width_hz,
                    burst_use_wide_window=burst_use_wide_window,
                )
                # SNR-edge auto-capture trigger (Phase 63). If the current
                # band is armable and armed, compare this cycle's SNR against
                # last cycle's: a rising edge across the band's calibrated
                # signal_threshold_db saves the raw IQ samples just captured
                # (the `samples` local from the read above) as a SigMF
                # recording. save_capture() writes files only - no hardware
                # access, no DSP - so it is safe in the hot loop. The
                # try/except ensures a disk-full or SigMF write failure
                # never kills the scan loop. bandwidth_hz is deliberately
                # omitted: HackRF has no settable RF filter, and on Pluto a
                # live-loop capture inherits whatever the stream already has,
                # so there is no operator-declared width to record.
                trigger_band_key = band_key_for_freq(freq_hz)
                if (
                    trigger_band_key is not None
                    and trigger_band_key in TRIGGER_ARMABLE_BANDS
                    and is_trigger_armed(trigger_band_key)
                ):
                    current_snr = fingerprint.get("snr_db")
                    trigger_threshold_db = band.get("signal_threshold_db")
                    prev_snr = get_last_trigger_snr(trigger_band_key)
                    if _should_fire_trigger(
                        prev_snr, current_snr, trigger_threshold_db
                    ):
                        logger.info(
                            "Auto-capture trigger fired: band=%s "
                            "snr_db=%.1f threshold_db=%.1f",
                            trigger_band_key,
                            current_snr if current_snr is not None else float("nan"),
                            (
                                trigger_threshold_db
                                if trigger_threshold_db is not None
                                else float("nan")
                            ),
                        )
                        try:
                            save_capture(
                                samples,
                                freq_hz=freq_hz,
                                sample_rate_hz=_SAMPLE_RATE_HZ,
                                device=self._device_driver,
                                fingerprint=fingerprint,
                            )
                        except Exception:
                            logger.exception(
                                "Auto-capture save failed for band=%s at %.3f MHz",
                                trigger_band_key,
                                freq_hz / 1e6,
                            )
                    if current_snr is not None:
                        set_last_trigger_snr(trigger_band_key, current_snr)
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
        """AI classification loop.

        Runs continuously while ``_running`` is True. Each iteration:
        1. Waits for the next fingerprint from the scan loop queue (timeout 1s).
        2. Queries ChromaDB for nearest neighbours (5 results).
        3. Calls the LLM classifier with the fingerprint, neighbour context, and
           ACMA band reference.
        4. Rate-limits llm_offline results to one emit every 5 seconds to avoid
           SocketIO flooding. Normal classification results are unaffected.
        5. Emits a ScanResult via ``_emit_result()`` for all non-offline results.

        The queue is drained before each scan-loop insertion, so the AI loop
        always sees the freshest scan. At steady state the queue holds 0–1 items.
        """
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

            # Pre-LLM deterministic noise gate. If the fingerprint unambiguously
            # describes noise (single bin, near-white), emit a deterministic
            # "noise" result and skip both the ChromaDB query and the LLM call.
            # Without this, every noise scan round-trips to the LLM and gets
            # confidently mis-labelled as a real band (e.g. "adsb 40%"),
            # flooding SIGNAL HISTORY with false classifications and wasting
            # one LLM call per noise scan. A real modulated signal has low
            # spectral flatness OR many occupied bins, so it can never trip
            # this gate. See SignalClassifier.is_noise_shaped() for the rules.
            if self._classifier.is_noise_shaped(item["fingerprint"]):
                result = self._classifier.classify_noise_deterministic(item["fingerprint"])
                # No LLM call was made — leave _llm_call_count and _last_llm_ms
                # untouched. chroma_distance is None (not 0.0) because no query
                # ran — an honest null, not a fake perfect match.
                item["fingerprint"]["chroma_distance"] = None
                scan_result = ScanResult(
                    timestamp=datetime.now().isoformat(),
                    center_freq_hz=item["freq_hz"],
                    fingerprint=item["fingerprint"],
                    classification=result,
                    psd_db=item.get("psd_db"),
                )
                self._emit_result(scan_result)
                continue

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

                # Rate-limit llm_offline emits — fast-fail returns in microseconds, which
                # floods SocketIO and causes the frontend to report a false disconnect.
                # One emit every 5 seconds is sufficient to keep the UI updated without
                # saturating the socket. Normal classification results are unaffected.
                if result.signal_type == "llm_offline":
                    now = time.time()
                    if now - self._last_offline_emit < 5.0:
                        continue
                    self._last_offline_emit = now

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

        Phase 43: a per-frequency throttle was added at the top of ``_emit_result()`` in
        ``core/pipeline/scanner.py``. The first verdict for a frequency always emits; any
        ``signal_type`` change at that frequency always emits immediately; an unchanged verdict
        (same frequency, same ``signal_type``) is suppressed until
        ``unchanged_emit_interval_sec`` (default 5.0 seconds) has elapsed since the last emit for
        that frequency. Time uses ``time.monotonic()`` (NTP-immune). The pre-existing
        ``llm_offline`` throttle in ``_ai_loop`` is unchanged.
        """
        # Per-frequency unchanged-verdict throttle. Three emit rules:
        #   a) First emit for a frequency always passes.
        #   b) A CHANGED signal_type at a frequency always emits immediately,
        #      regardless of how recently the previous verdict was emitted.
        #   c) An UNCHANGED verdict (same freq, same signal_type) is
        #      suppressed until unchanged_emit_interval_sec has elapsed since
        #      the last emit for that frequency.
        # Rule b is checked first: change-detection emits immediately.
        freq_hz = scan_result.center_freq_hz
        signal_type = scan_result.classification.signal_type
        now = time.monotonic()
        interval = self._config.unchanged_emit_interval_sec
        last = self._last_emit_by_freq.get(freq_hz)
        if last is not None and last[0] == signal_type and (now - last[1]) < interval:
            return  # suppressed: same freq, same signal_type, within interval
        self._last_emit_by_freq[freq_hz] = (signal_type, now)
        # Thread-safety: _emit_result is called only from the AI loop thread,
        # so _last_emit_by_freq has a single writer — no lock required. Do not
        # add a redundant lock here.
        # Dict growth: bounded by the number of distinct frequencies in the
        # band plan plus focus frequencies — a small fixed set, so no eviction
        # is needed.
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
