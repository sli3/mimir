import logging
import queue
import threading
import time
from datetime import datetime

import numpy as np

from core.config.loader import MimirConfig
from core.device.profiles import DEVICE_PROFILES
import core.pipeline.features as features
from core.pipeline.capture import (
    _FINGERPRINT_METADATA_KEYS,
    save_capture,
    save_recording,
)
from core.pipeline.fft import compute_psd
from core.pipeline.scan_result import ScanResult
from dashboard.server import record_hw_error
import dashboard.shared_state as shared_state
from dashboard.shared_state import (
    TRIGGER_ARMABLE_BANDS,
    band_key_for_freq,
    check_and_update_trigger_state,
    get_last_trigger_snr,
    is_trigger_armed,
    set_last_trigger_snr,
)
from llm.acma_reference import AcmaReference

logger = logging.getLogger(__name__)

_SAMPLE_RATE_HZ = 2_000_000
# Caps the in-memory RECORD buffer so an unattended recording cannot exhaust
# memory; the final concatenate briefly needs about twice this.
RECORD_MAX_BYTES = 2 * 1024**3
RECORD_MAX_SAMPLES = RECORD_MAX_BYTES // np.dtype(np.complex64).itemsize
# Pause after a failed scan cycle so a persistent device or pipeline error
# cannot spin the loop and flood the log. Deliberately not config.dwell_time_sec,
# which is 0.0 in config/mimir.yaml.
_SCAN_ERROR_BACKOFF_SEC: float = 1.0
# Minimum interval between short reminders during one SDR read outage.
_SDR_OUTAGE_REMINDER_SEC: float = 60.0


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

    Note: after Phase 64's EDGE-03 fix, the live scan loop no longer
    passes threshold=None to this function - it reuses the `threshold`
    local computed earlier with a fallback to features.SIGNAL_THRESHOLD_DB,
    so the threshold-is-None branch is unreachable from the production
    call site today. The guard remains for direct/test callers and for
    any future caller that does not provide a fallback.

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
    _scan_count counts live scan cycles or replayed chunks in demo mode.
    _scan_count_since_llm — increments once per scan cycle; snapshot
    into _last_backlog when the AI loop picks up an item, then reset.

    Manual capture:
    capture_now() requests a one-shot capture of the next scan cycle's
    live samples. Independent of the queue and the stats counters — it
    reuses samples already read by the scan loop rather than opening a
    second device connection. See capture_now()'s docstring for the
    cross-thread handoff contract.

    Operator-controlled recording (Phase 68):
    start_recording() / stop_recording() / get_recording_status() manage a
    long-lived, operator-controlled "Record" mode that accumulates scan-cycle
    samples in memory up to a cap, then writes a single SigMF
    file on stop. Fully separate mechanism from capture_now() above —
    separate state, separate code path, separate endpoint. The class
    methods only manage state and chunk accumulation; the actual SigMF
    metadata writing happens in save_recording() in core/pipeline/capture.py,
    called by stop_recording(). GET /api/record/status exposes
    get_recording_status() so the frontend can adopt an in-progress
    recording and its elapsed time on remount (page refresh).
    Accumulation stops at the memory cap; the operator stops to save it (a
    60-second soft warning is displayed client-side).
    """
    def __init__(
        self, device, embedder, store, classifier, config: MimirConfig,
        device_driver: str = "hackrf",
        *,
        is_demo_device: bool = False,
    ) -> None:
        """Initialise the two-thread scanner.

        The scan loop captures IQ and queues fingerprints; the AI loop classifies
        the freshest sample via LLM. Queue behaviour is "latest wins" — the scan
        loop drains the queue before every insert so the AI loop always sees the
        most recent scan. At steady state the queue holds 0–1 items.

        The scan thread wrapper signals ``_scan_loop_finished`` on every
        exit path. Shutdown waits for this event because an interrupted
        join can make thread liveness unreliable on CPython 3.11.

        Focus changes are allowed before startup and blocked after stop()
        until run() or start_ai_only() starts the scanner again.

        Recording state starts empty and uncapped with no start timestamp;
        accumulation is limited to RECORD_MAX_SAMPLES until the operator
        stops and saves it.

        Stats counters:
        _scan_count counts live cycles or replayed demo chunks.
        _scan_count_since_llm — increments once per scan cycle; snapshot
        into _last_backlog when the AI loop picks up an item, then reset.

        _last_offline_emit — timestamp of the last llm_offline emit; used to
        rate-limit offline results to one every 5 seconds to avoid SocketIO
        flooding.

        _sdr_unresponsive and _sdr_unresponsive_last_log track a sample-read
        outage and its last operator message in monotonic seconds. A good
        main read clears both so a later outage gets a fresh error message.
        The dashboard reads the flag through the sdr_unresponsive property.

        device_driver — the DEVICE_PROFILES driver key ("hackrf" / "plutosdr")
        of the attached device. Used by the scan loop's unsupported-band guard:
        non-HackRF devices with a narrower tuning range (e.g. Pluto, 325 MHz
        floor) skip focus frequencies they cannot physically receive instead
        of tuning into noise. Defaults to "hackrf", which supports every band
        and bypasses the guard entirely.

        is_demo_device — when True, ``set_focus_frequency()`` skips the queue
        drain. Demo mode has no real device to retune, so any chunks in the
        queue were legitimately captured from the demo file by ``DemoProducer``
        and must reach the AI loop, not be silently dropped on every socket
        reconnect. Defaults to False (live mode).

        Demo frequency reports update runtime statistics only in demo mode;
        live-mode reports are ignored with one warning per instance.

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
        self._is_demo_device = is_demo_device
        self._demo_frequency_warning_logged: bool = False
        self._embedder = embedder
        self._store = store
        self._classifier = classifier
        self._config = config
        self._queue: queue.Queue = queue.Queue(maxsize=config.queue_maxsize)
        self._running = False
        # True from stop() until the next run() or start_ai_only().
        self._stopping: bool = False
        self._scan_thread: threading.Thread | None = None
        self._scan_loop_finished = threading.Event()
        self._scan_loop_finished.set()
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
        self._sdr_unresponsive: bool = False
        self._sdr_unresponsive_last_log: float | None = None
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
        # Cross-thread capture request handoff (manual capture button, this
        # build). The Flask request handler thread sets
        # _capture_request_event, the scan loop checks it once per cycle,
        # services the request using the in-flight samples already read
        # this cycle (no second device open — see capture_now()'s
        # docstring and the [62] timing-integrity rationale), and posts
        # the result back via _capture_result_event. Single-producer
        # (scan loop) / single-consumer (capture_now caller) per request,
        # but the events are reusable across calls — _capture_result and
        # _capture_result_event are cleared at the top of capture_now()
        # so a stale set from a prior abandoned call cannot be misread as
        # a fresh response.
        self._capture_request_event: threading.Event = threading.Event()
        self._capture_result_event: threading.Event = threading.Event()
        self._capture_result_lock: threading.Lock = threading.Lock()
        self._capture_result: dict | None = None
        # Operator-controlled "Record" capture state (Phase 68). Fully
        # separate mechanism from capture_now() above: separate fields,
        # separate scan-loop code path, separate Flask routes. While
        # _recording is True and the cap has not been reached, each scan
        # cycle appends its already-read
        # samples to _record_buffer (in-memory accumulation only — no
        # disk streaming, no file handle held open across cycles) and
        # one per-cycle fingerprint entry to _record_fingerprints.
        # stop_recording() concatenates the buffer and writes ONE SigMF
        # file via save_recording(). _record_sample_offset is the
        # cumulative sample count into the final concatenated buffer —
        # the ground truth for replay slicing (each per-cycle entry's
        # sample_start). _record_freq_hz pins the start frequency so the
        # saved file's single core:frequency field is honest, and so a
        # mid-recording focus change can be detected and logged.
        # _record_started_monotonic tracks elapsed time for status reads.
        self._recording: bool = False
        # Latched at the memory cap until recording state is reset.
        self._record_capped: bool = False
        self._record_buffer: list = []              # np.ndarray chunks
        self._record_fingerprints: list = []        # per-cycle dicts
        self._record_sample_offset: int = 0
        self._record_freq_hz: float | None = None
        self._record_started_monotonic: float | None = None
        self._record_lock: threading.Lock = threading.Lock()

    @property
    def sdr_unresponsive(self) -> bool:
        """Return True from an outage's first failed main read until a good read.

        Only the scan thread writes the flag; the dashboard's stats thread
        reads it here. A single bool read needs no lock.
        """
        return self._sdr_unresponsive

    @property
    def stopping(self) -> bool:
        """Return whether shutdown has been requested since the last start."""
        return self._stopping

    @property
    def is_demo_device(self) -> bool:
        """Return whether the scanner consumes demo captures."""
        return self._is_demo_device

    def run(self) -> None:
        """Start both workers and join them, recording scan completion.

        Reset the completion event before starting the scan thread. Its
        wrapper signals the event even when the scan loop raises, so an
        interrupted join cannot falsely report a completed device call.
        Clear the stopping flag immediately before enabling the workers.
        """
        self._scan_loop_finished.clear()
        self._stopping = False
        self._running = True
        self._scan_thread = threading.Thread(
            target=self._run_scan_loop, daemon=True,
        )
        self._ai_thread = threading.Thread(target=self._ai_loop, daemon=True)
        self._scan_thread.start()
        self._ai_thread.start()
        self._scan_thread.join()
        self._ai_thread.join()

    def _run_scan_loop(self) -> None:
        """Signal scan-loop completion on normal return or any exception."""
        try:
            self._scan_loop()
        finally:
            self._scan_loop_finished.set()

    def start_ai_only(self) -> None:
        """Start only the AI loop thread (demo mode).

        Demo mode does not open hardware, so the scan loop is never started.
        The queue is fed externally by ``DemoProducer``.

        Blocks (joins the AI thread) until ``stop()`` is called. Same shape
        as ``run()`` but without the scan thread.
        Clear the stopping flag immediately before enabling the AI worker.
        """
        self._stopping = False
        self._running = True
        self._ai_thread = threading.Thread(target=self._ai_loop, daemon=True)
        self._ai_thread.start()
        self._ai_thread.join()

    def stop(self) -> None:
        """Block focus changes and request shutdown; wait via wait_stopped()."""
        self._stopping = True
        self._running = False

    def wait_stopped(self, timeout: float) -> bool:
        """Wait up to timeout seconds for scan-loop completion only.

        Call after stop() before closing the receiver. Return False if the
        loop has not finished, or immediately when called from its thread.
        A scanner with no scan thread is already stopped for this purpose.
        Use the completion event rather than thread liveness, which can
        falsely report a stopped thread after an interrupted Python 3.11 join.
        """
        scan_thread = self._scan_thread
        if scan_thread is None:
            return True
        if scan_thread is threading.current_thread():
            return False
        return self._scan_loop_finished.wait(timeout=timeout)

    def report_demo_frequency(self, freq_hz: float) -> None:
        """Report a demo chunk's centre frequency and count one replay cycle.

        Ignore live-mode reports and warn once per instance because the
        scan loop owns the live SDR centre frequency.
        """
        if self._is_demo_device:
            self._active_freq_hz = float(freq_hz)
            # Like live stats, this needs no lock: the demo producer is the
            # only writer because the scan loop never runs in demo mode.
            self._scan_count += 1
        elif not self._demo_frequency_warning_logged:
            self._demo_frequency_warning_logged = True
            logger.warning("Ignoring demo frequency report in live mode")

    def get_stats(self) -> dict:
        """Return current scanner runtime statistics.

        Keys:
            active_frequency_hz : float  — current SDR centre frequency, or
                in demo mode the centre frequency of the capture being
                replayed (0.0 until the first report)
            scan_count          : int    — live cycles or replayed demo chunks
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

    def set_focus_frequency(self, freq_hz: float | None) -> None:
        """Change the focus frequency and flush stale queue items (live mode only).

        Ignore requests after stop() until run() or start_ai_only() restarts
        the scanner, leaving the focus and queue untouched. Requests before
        the first start remain allowed for the startup focus.

        In demo mode (``is_demo_device=True``), the queue drain is SKIPPED:
        there is no real device to retune, so any chunks in the queue were
        legitimately captured from the demo file by ``DemoProducer`` and must
        reach the AI loop rather than being silently dropped on every socket
        reconnect. The focus frequency itself is still updated (it is harmless
        in demo mode — the AI loop doesn't read it, and the scan loop is not
        running).
        """
        if self._stopping:
            if freq_hz is None:
                logger.info("Ignoring focus change: scanner is stopping")
            else:
                logger.info(
                    "Ignoring focus change to %.3f MHz: scanner is stopping",
                    freq_hz / 1e6,
                )
            return
        with self._focus_lock:
            self._focus_freq_hz = freq_hz
            if not self._is_demo_device:
                q = self._queue
                while True:
                    try:
                        q.get_nowait()
                    except queue.Empty:
                        break
        if self._is_demo_device:
            logger.info(
                "Focus changed to %.3f MHz - queue flush skipped in demo mode",
                freq_hz / 1e6,
            )
        else:
            logger.info("Focus changed to %.3f MHz — queue flushed", freq_hz / 1e6)

    def capture_now(self, timeout_sec: float = 5.0) -> dict:
        """Request a manual capture using the next scan cycle's live samples.

        Signals the scan loop to save the samples it is about to read on its
        next iteration — the same samples already feeding the waterfall and
        classifier, not a fresh independent capture (a second device open is
        not supported; see also the [62] session's timing-integrity rationale
        for reusing in-flight samples rather than a separately-timed grab).

        Blocks the calling thread (the Flask request handler) until the scan
        loop has serviced the request or ``timeout_sec`` elapses. Safe to call
        repeatedly across operators — the events and result slot are cleared
        at the top of every call, so a stale state from a prior abandoned
        call cannot be misread as a fresh response. Single-flight semantics:
        if a request is already pending, the next call will overwrite the
        pending flag rather than queue a second one — appropriate for an
        operator tool.

        Returns:
            dict with key ``"status"`` and one of:
            - ``"ok"``    — save succeeded; also has ``"file"`` (str path) and
              ``"fingerprint"`` (the seven ``_FINGERPRINT_METADATA_KEYS``
              measurement fields).
            - ``"error"`` — save raised; also has ``"cause"`` (str, the
              exception message). The scan loop survives the failure and keeps
              cycling.
            - ``"timeout"`` — the scan loop did not service the request
              within ``timeout_sec`` (e.g. the loop has stopped, is wedged,
              or is dwelling on an unsupported band). No extra keys; the
              caller can present a distinct "no response from scanner"
              message rather than swallowing it as a save failure.
        """
        # Defensive clear BEFORE setting the request event (security-analyst
        # Q4(a) finding): Event.wait() does not consume the flag, so a stale
        # set result-event from a prior call that the caller never read
        # would make this call return instantly with the stale result. Clear
        # both the result-event AND the result slot itself — the scan loop's
        # service path always overwrites _capture_result before setting the
        # event, so this is belt-and-braces, but cheap and explicit.
        self._capture_result_event.clear()
        with self._capture_result_lock:
            self._capture_result = None
        self._capture_request_event.set()
        if not self._capture_result_event.wait(timeout=timeout_sec):
            # Late-arriving scan cycle must NOT service a request the caller
            # has already given up on — clear the request flag. The scan
            # loop's check is `if event.is_set()`, so a clear here means the
            # late-arriving cycle sees no pending request and skips the
            # block. At worst one save_capture() call is wasted; never a
            # stale data leak.
            self._capture_request_event.clear()
            return {"status": "timeout"}
        with self._capture_result_lock:
            result = self._capture_result
            self._capture_result = None
        return result

    def start_recording(self) -> dict:
        """Begin accumulating scan-cycle samples into an in-memory recording.

        Called from the Flask request handler thread (POST /api/record/
        start). From the next scan cycle onwards, each cycle's already-
        read samples are appended to an in-memory buffer until the memory
        cap is reached or stop_recording() is called. Starting resets the
        cap flag and records the monotonic start time before enabling
        recording. The buffer stays in RAM until the operator stops to save.

        Idempotent-safe: calling while already recording returns an
        error status rather than silently resetting an in-progress
        recording (a silent reset would throw away samples the operator
        believes are still being captured).

        Returns:
            dict with key ``"status"`` and one of:
            - ``"ok"``                — recording has begun; state reset.
            - ``"already_recording"`` — a recording is in progress and
              was left untouched.
        """
        with self._record_lock:
            if self._recording:
                return {"status": "already_recording"}
            self._record_buffer = []
            self._record_fingerprints = []
            self._record_sample_offset = 0
            self._record_capped = False
            self._record_freq_hz = self._focus_freq_hz
            self._record_started_monotonic = time.monotonic()
            self._recording = True
            return {"status": "ok"}

    def stop_recording(self) -> dict:
        """Stop accumulating and save one SigMF file if samples were recorded.

        Called from the Flask request handler thread (POST /api/record/
        stop). With samples, blocks for np.concatenate of the capped buffer
        plus a single save_recording() call. The memory cap bounds the samples,
        but a large buffer can still take time to save. This runs under
        _record_lock to keep the state transition atomic against the scan
        loop; concatenate briefly needs about twice the buffer memory.

        ``_recording`` is cleared FIRST, before any heavy work, so the
        scan loop's re-check inside its own lock acquisition cannot add
        an orphan cycle after the buffer has been detached. The shared
        accumulator state and monotonic start time are reset under the
        lock regardless of save outcome, so a failed save (e.g. disk full)
        can never leave a stale half-recording for the next start_recording().

        Returns:
            dict with key ``"status"`` and one of:
            - ``"ok"``            — save succeeded; also has ``"file"``
              (str path), ``"duration_sec"`` (float, total samples /
              sample rate) and ``"cycle_count"`` (int, number of scan
              cycles captured).
            - ``"cap_reached"``   — save succeeded after accumulation hit
              the memory cap; has the same file, duration and cycle keys
              as ``"ok"``, describing only the retained samples.
            - ``"error"``         — concatenate or save raised
              (including MemoryError), or no samples were recorded and no
              file was written. Also has ``"cause"`` (str): the exception
              message, or "No samples were recorded, so no file was saved."
              State is still fully reset.
            - ``"not_recording"`` — no recording was in progress.
        """
        with self._record_lock:
            if not self._recording:
                return {"status": "not_recording"}
            # Clear the flag FIRST so the scan loop's re-check under its
            # own lock acquisition cannot append an orphan cycle while
            # we work below.
            self._recording = False
            freq_hz = self._record_freq_hz
            fingerprints = self._record_fingerprints
            cycle_count = len(fingerprints)
            total_samples = self._record_sample_offset
            capped = self._record_capped
            buffer = self._record_buffer
            # Reset shared state under the lock, whatever happens next,
            # so the scan loop sees an empty accumulator on its next
            # cycle and a later start_recording() begins clean.
            self._record_buffer = []
            self._record_fingerprints = []
            self._record_sample_offset = 0
            self._record_capped = False
            self._record_started_monotonic = None
            if not buffer:
                logger.warning("No samples were recorded, so no file was saved.")
                return {
                    "status": "error",
                    "cause": "No samples were recorded, so no file was saved.",
                }
            try:
                samples = np.concatenate(buffer)
                saved_path = save_recording(
                    samples,
                    freq_hz=freq_hz,
                    sample_rate_hz=_SAMPLE_RATE_HZ,
                    device=self._device_driver,
                    fingerprint_sequence=fingerprints,
                )
            except Exception as exc:
                logger.exception(
                    "Recording save failed at %.3f MHz",
                    (freq_hz or 0.0) / 1e6,
                )
                return {"status": "error", "cause": str(exc)}
            return {
                "status": "cap_reached" if capped else "ok",
                "file": str(saved_path),
                "duration_sec": total_samples / _SAMPLE_RATE_HZ,
                "cycle_count": cycle_count,
            }

    def get_recording_status(self) -> dict:
        """Return a lightweight snapshot for GET /api/record/status.

        Read state without _record_lock so a slow save in stop_recording()
        cannot block status requests. Local references keep list and start
        time reads safe across a reset; fields need not form an atomic
        snapshot. Elapsed time uses the monotonic clock and is non-negative.

        Returns:
            dict with keys ``"recording"`` (bool), ``"elapsed_cycles"``
            (int, retained scan cycles), ``"elapsed_sec"`` (float, wall
            duration while recording, otherwise 0.0), and ``"capped"``
            (bool, whether accumulation reached the memory cap).
        """
        recording = self._recording
        fingerprints = self._record_fingerprints
        started = self._record_started_monotonic
        elapsed_sec = (
            max(0.0, time.monotonic() - started)
            if recording and started is not None else 0.0
        )
        return {
            "recording": recording,
            "elapsed_cycles": len(fingerprints),
            "elapsed_sec": elapsed_sec,
            "capped": self._record_capped,
        }


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
          8. Accumulates recording samples and fingerprints up to the
             memory cap, leaving the retained buffer for an operator stop.

        Frequency cache:
        A method-local ``_last_tuned_hz`` tracks the most recently tuned frequency.
        When the focus frequency has not changed since the last iteration,
        ``device.set_center_frequency()`` is skipped entirely. This avoids redundant
        libhackrf / SoapySDR retune calls that cost ~500 ms each — significant at
        1090 MHz (ADS-B) where the same frequency is scanned repeatedly. The cache
        is reset automatically when ``set_focus_frequency()`` is called (the queue
        flush there is unrelated to this cache and is skipped in demo mode).

        The spectrum broadcast (step 5) is wrapped in its own try/except so that a
        broadcast failure (e.g. no connected dashboard) does not prevent the scan
        loop from continuing or the fingerprint from reaching the AI pipeline.

        Main sample-read failures log one short error per outage, a reminder
        every ``_SDR_OUTAGE_REMINDER_SEC``, and exception details with a
        traceback at debug level on the first failure. A good main read logs
        recovery and clears the outage state. Read failures pause for the
        fixed ``_SCAN_ERROR_BACKOFF_SEC`` before the next cycle. The receiver
        proxy reconnects automatically once the SDR is plugged back in. The outer
        handler still logs a full traceback for any other exception escaping
        a scan cycle, using that cycle's frequency and the same back-off.
        This sleep is not interruptible, so ``stop()`` can lag by up to it.

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
            with self._focus_lock:
                freq_hz = self._focus_freq_hz
            try:
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
                except Exception as exc:
                    record_hw_error()
                    # Keep read-outage advice concise and rate-limit reminders.
                    now = time.monotonic()
                    if not self._sdr_unresponsive:
                        display_name = DEVICE_PROFILES.get(
                            self._device_driver, {}
                        ).get("display_name") or "SDR"
                        logger.error(
                            "SDR not responding: %s stopped returning samples "
                            "at %.3f MHz. Check the USB cable. Mimir reconnects "
                            "automatically once the SDR is plugged back in.",
                            display_name,
                            freq_hz / 1e6,
                        )
                        logger.debug(
                            "SDR read failure detail: %s", exc, exc_info=True
                        )
                        self._sdr_unresponsive = True
                        self._sdr_unresponsive_last_log = now
                    elif (
                        self._sdr_unresponsive_last_log is not None
                        and now - self._sdr_unresponsive_last_log
                        >= _SDR_OUTAGE_REMINDER_SEC
                    ):
                        logger.warning(
                            "SDR still not responding at %.3f MHz. Check the "
                            "USB cable. Mimir reconnects automatically once "
                            "the SDR is plugged back in.",
                            freq_hz / 1e6,
                        )
                        self._sdr_unresponsive_last_log = now
                    time.sleep(_SCAN_ERROR_BACKOFF_SEC)
                    continue
                if self._sdr_unresponsive:
                    logger.info("SDR responding again at %.3f MHz", freq_hz / 1e6)
                    self._sdr_unresponsive = False
                    self._sdr_unresponsive_last_log = None
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
                # Burst-type bands (currently only ADS-B) fingerprint the
                # max-hold trace so pulsed energy is not averaged away
                # (Phase 65, Finding B). Bands without the key default to
                # the averaged 'psd_db' trace — byte-identical to the
                # previous behaviour. fingerprint_trace_key lives on
                # BAND_PROFILES["adsb"]; it is inherited by the HackRF
                # path via a direct copy and by the Pluto path via
                # resolve_band_profile's base.copy(). The Pluto overlay
                # only copies gain_db and signal_threshold_db, so any
                # future BAND_PROFILES-only key (like this one) is
                # automatically inherited. Keeping this key on
                # BAND_PROFILES (not on PLUTO_BAND_PROFILES) avoids the
                # per-device duplication burden for keys whose value is
                # identical across devices.
                trace_key = band.get("fingerprint_trace_key", "psd_db")
                fingerprint = features.fingerprint_spectrum(
                    psd,
                    signal_threshold_db=threshold,
                    trace_key=trace_key,
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
                # The armed-check, previous-SNR read, and current-SNR write
                # go through the atomic check_and_update_trigger_state()
                # helper (Phase 64b) rather than separate is_trigger_armed() /
                # get_last_trigger_snr() / set_last_trigger_snr() calls: one
                # lock acquisition replaces three, closing the TOCTOU gap
                # flagged in review where a concurrent disarm could clear the
                # baseline (LIFE-01) and the scan loop then repopulate it
                # between the armed-check and the write. The helper also
                # owns the None-safety and armed-only-write gating
                # internally, so current_snr is passed through as-is.
                trigger_band_key = band_key_for_freq(freq_hz)
                if (
                    trigger_band_key is not None
                    and trigger_band_key in TRIGGER_ARMABLE_BANDS
                ):
                    current_snr = fingerprint.get("snr_db")
                    was_armed, prev_snr = check_and_update_trigger_state(
                        trigger_band_key, current_snr
                    )
                    # Phase 68: the auto-trigger is suppressed while an
                    # operator "Record" capture is in progress — the
                    # samples are already being accumulated into the
                    # recording, so a duplicate one-shot save_capture()
                    # would only waste disk. This is a single added
                    # boolean on the fire condition ONLY:
                    # check_and_update_trigger_state() above must keep
                    # running every cycle so prev_snr stays current (a
                    # stale prev_snr after recording stops would cause
                    # spurious fires per LIFE-01/EDGE-03).
                    if (
                        was_armed
                        and _should_fire_trigger(
                            prev_snr, current_snr, threshold
                        )
                        and not self._recording
                    ):
                        logger.info(
                            "Auto-capture trigger fired: band=%s "
                            "snr_db=%.1f threshold_db=%.1f",
                            trigger_band_key,
                            current_snr if current_snr is not None else float("nan"),
                            (
                                threshold
                                if threshold is not None
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
                # Manual capture request (this build). Independent of the
                # SNR-edge auto-trigger above — always available regardless
                # of trigger arm state, since a manual press is an explicit
                # operator action, not an edge-detected event. Uses the
                # same save_capture() call shape as the auto-trigger:
                # samples already read this cycle, no second device open,
                # same timing-integrity rationale as [62]. The fingerprint
                # is the one already measured by fingerprint_spectrum()
                # this cycle, so the result file's mimir:fingerprint
                # matches the PSD the operator is currently seeing on the
                # waterfall. bandwidth_hz is deliberately omitted:
                # HackRF has no settable RF filter, and on Pluto a
                # live-loop capture inherits whatever the stream already
                # has, so there is no operator-declared width to record.
                if self._capture_request_event.is_set():
                    self._capture_request_event.clear()
                    try:
                        saved_path = save_capture(
                            samples,
                            freq_hz=freq_hz,
                            sample_rate_hz=_SAMPLE_RATE_HZ,
                            device=self._device_driver,
                            fingerprint=fingerprint,
                        )
                        result = {
                            "status": "ok",
                            "file": str(saved_path),
                            "fingerprint": {
                                k: fingerprint[k]
                                for k in _FINGERPRINT_METADATA_KEYS
                            },
                            # Deliberate separation from the fingerprint
                            # sub-dict: `is_burst` describes the burst
                            # detection pipeline (Phase 45 family), not
                            # the captured spectrum, so it is NOT in
                            # _FINGERPRINT_METADATA_KEYS and therefore
                            # NOT persisted in the SigMF metadata. It is
                            # exposed here as a top-level sibling so the
                            # dashboard verdict (Phase 67
                            # CaptureResultPanel) can override the
                            # occupied_bins fallback for narrow bursts
                            # without re-including a transient detection
                            # state on every saved recording.
                            "is_burst": bool(
                                fingerprint.get("is_burst", False)
                            ),
                        }
                    except Exception as exc:
                        logger.exception(
                            "Manual capture save failed at %.3f MHz",
                            freq_hz / 1e6,
                        )
                        result = {"status": "error", "cause": str(exc)}
                    with self._capture_result_lock:
                        self._capture_result = result
                    self._capture_result_event.set()
                # Continuous "Record" capture (Phase 68). Independent of
                # both the SNR-edge auto-trigger above and the one-shot
                # manual capture_now() block. Appends this cycle's
                # already-read samples to an in-memory accumulator up to
                # the memory cap. Once capped, later cycles add neither
                # samples nor fingerprints; stop_recording() saves the
                # retained buffer from the Flask request thread. No disk
                # or concatenate work happens here. Frequency-change
                # guard: if the operator
                # changes the focus frequency mid-recording, the
                # recording continues but a log warning is emitted,
                # since a recording spanning two different frequencies
                # would have a legal/RF-meaning inconsistency (the SigMF
                # file only has one core:frequency field). Do NOT stop
                # the recording automatically on frequency change —
                # that is a silent data-loss surprise for an operator
                # who didn't ask for it.
                if self._recording:
                    with self._record_lock:
                        if self._recording:  # re-check under lock; may
                                             # have been stopped between
                                             # the outer check and
                                             # acquiring the lock
                            if freq_hz != self._record_freq_hz:
                                logger.warning(
                                    "Recording frequency mismatch: "
                                    "started at %.3f MHz, now at %.3f "
                                    "MHz — recording continues, saved "
                                    "file will use the START frequency",
                                    self._record_freq_hz / 1e6,
                                    freq_hz / 1e6,
                                )
                            if self._record_capped:
                                pass
                            elif (
                                self._record_sample_offset + len(samples)
                                > RECORD_MAX_SAMPLES
                            ):
                                self._record_capped = True
                                logger.warning(
                                    "Recording memory cap reached (%d bytes); "
                                    "%.3f seconds recorded so far. Later "
                                    "cycles are not kept until RECORD is stopped",
                                    RECORD_MAX_BYTES,
                                    self._record_sample_offset / _SAMPLE_RATE_HZ,
                                )
                            else:
                                self._record_buffer.append(samples)
                                cycle_fp = {
                                    "sample_start": self._record_sample_offset,
                                    "sample_count": len(samples),
                                    "timestamp_sec": (
                                        self._record_sample_offset
                                        / _SAMPLE_RATE_HZ
                                    ),
                                    **{
                                        k: fingerprint[k]
                                        for k in _FINGERPRINT_METADATA_KEYS
                                    },
                                }
                                self._record_fingerprints.append(cycle_fp)
                                self._record_sample_offset += len(samples)
                vector = embedder.embed(fingerprint)
                # "Latest wins" — drain stale items before inserting so the AI loop
                # always classifies the freshest scan, not a backlog seconds old.
                # Safe: _scan_loop is the only producer; after drain, queue is empty,
                # so put_nowait always succeeds without raising queue.Full.
                # Note: set_focus_frequency() also drains this queue (consumer-only),
                # which is safe because both paths only remove items; in demo mode
                # that drain is skipped so DemoProducer chunks are preserved.
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
                time.sleep(_SCAN_ERROR_BACKOFF_SEC)

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
