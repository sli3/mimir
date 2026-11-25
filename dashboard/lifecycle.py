"""
Dashboard server lifecycle, statistics and scan broadcast callbacks.

Legal: Receive-only. Radiocommunications Act 1992 (Cth).
       No transmission. Jurisdiction: AU/SA. Authority: ACMA.

This module is imported only from the bottom of dashboard/server.py and
must never be imported first. Callers use the re-exports in dashboard.server.
Shared application state is accessed through that module at call time.
start_server attaches its scan and spectrum callbacks to the function.
"""

import logging
import threading
import time
from collections.abc import Callable
from typing import Any

from core.pipeline.frequency import freq_matches
from core.pipeline.scan_result import ScanResult
import dashboard.server as _server
import dashboard.shared_state as shared_state

logger = logging.getLogger(__name__)

# emit_stats runs in a single thread; server re-exports this same set.
_warned_unknown_devices: set[str] = set()


def _unsupported_bands_or_empty(device: str) -> dict[str, str]:
    """Use the shared helper, logging once per unknown device key here."""
    try:
        return shared_state.unsupported_bands_for_device(device)
    except KeyError:
        if device not in _warned_unknown_devices:
            _warned_unknown_devices.add(device)
            logger.warning("Unknown device %r: unsupported bands unavailable", device)
        return {}


def _run_socketio(host: str, port: int) -> None:
    """Run the shared server, ending its thread after logging a failure.

    Werkzeug's own "Running on" line is the success signal.
    """
    logger.info("Dashboard server starting on http://%s:%d", host, port)
    try:
        _server.socketio.run(
            _server.app, host=host, port=port, debug=False, use_reloader=False,
            allow_unsafe_werkzeug=True,
        )
    except Exception:
        logger.exception("Dashboard server failed on http://%s:%d", host, port)
        return


def start_server(
    host: str, port: int, device: Any = None, scanner: Any = None,
) -> Callable[[ScanResult], None]:
    """
    Start the dashboard in background threads using dashboard.server state.

    Werkzeug is allowed to run without a TTY so background and demo launches
    serve the dashboard. The bind address comes from config, using loopback
    by default.
    The server thread logs its start attempt and any failure; Werkzeug's own
    "Running on" line confirms success.

    Args:
        host    : Bind address (e.g. "0.0.0.0" for all interfaces).
        port    : Port number (e.g. 5000).
        device  : Optional receiver stored on dashboard.server for status.
        scanner : Optional ScanRunner instance for live system_stats.
                  When provided, system_stats events report real values
                  (scan_count, queue_depth, llm_last_inference_ms) instead
                  of zeros. Demo scan_count counts replayed chunks; demo
                  band limits supplement the device's unsupported bands.

    After calling start_server(), the broadcast functions are attached
    as attributes on the function itself:
        start_server._broadcast_fn        — emit a scan_result event
        start_server._broadcast_spectrum_fn — emit spectrum_update at up to
            30 Hz with PSD values rounded to one decimal place
    """
    _server._device_ref = device
    _server._scanner_ref = scanner

    def run_flask() -> None:
        """Delegate to the lifecycle runner for start and failure logging."""
        _run_socketio(host, port)

    t = threading.Thread(target=run_flask, daemon=True)
    t.start()

    def emit_stats() -> None:
        """Emit stats and merge demo band limits, preserving device reasons."""
        while True:
            time.sleep(2.0)
            if scanner is not None:
                stats = scanner.get_stats()
                active_freq = stats["active_frequency_hz"]
                scan_count = stats["scan_count"]
                queue_depth = stats["queue_depth"]
                last_backlog = stats["last_backlog"]
                llm_call_count = stats["llm_call_count"]
                llm_ms = stats["last_llm_ms"]
            else:
                active_freq = 0.0
                scan_count = 0
                queue_depth = 0
                last_backlog = 0
                llm_call_count = 0
                llm_ms = 0.0
            # Read the active device under its shared-state lock each poll.
            # Look up helpers through the module so patches remain effective;
            # hardware status below comes from the current _server state.
            with shared_state.current_device_lock:
                active_device = shared_state.current_device
            unsupported_map = _unsupported_bands_or_empty(active_device)
            if (
                scanner is not None
                and getattr(scanner, "is_demo_device", False) is True
            ):
                unsupported_map = {
                    **shared_state.bands_outside_demo(active_freq),
                    **unsupported_map,
                }
            try:
                device_display = shared_state.display_name_for_device(active_device)
            except KeyError:
                device_display = str(active_device)
            data = {
                "hackrf_status": _server._compute_hackrf_status(),
                "active_frequency_hz": active_freq,
                "scan_count": scan_count,
                "queue_depth": queue_depth,
                "last_backlog": last_backlog,
                "llm_call_count": llm_call_count,
                "llm_last_inference_ms": llm_ms,
                # Phase 38 — device-aware unsupported-band UI.
                "device": active_device,
                # Friendly device name, falling back to the raw unknown key.
                "current_device_display": device_display,
                "unsupported_bands": unsupported_map,
            }
            _server.socketio.emit("system_stats", data)

    _stats_thread = threading.Thread(target=emit_stats, daemon=True)
    _stats_thread.start()

    def broadcast(scan_result: ScanResult) -> None:
        """Emit a scan_result event for a fingerprint/LLM-classified scan.

        Called by the LLM classification pipeline when ScanRunner finishes
        classifying a spectrum fingerprint. Only emits if the current focused
        frequency matches the scan's center frequency (or is None, meaning
        all frequencies pass through). The payload includes the classification
        result plus fingerprint-derived fields such as peak power, SNR, and
        per-band thresholds. Since Phase 32, also includes a ``source`` field
        set to ``"fingerprint"`` to distinguish LLM-classified scans from
        decoder-driven ones (see dashboard.emitters.emit_adsb_scan_result).
        Since Phase 45, includes burst-detection fields (burst_ratio_db,
        expected_noise_ratio_db, burst_excess_db, is_burst) computed by the
        per-bin max-hold ratio method.
        A missing SNR margin is sent as None. Focus and SocketIO are read
        from dashboard.server on each call.

        Args:
            scan_result: The ScanResult dataclass instance to broadcast.
        """
        with _server._focused_freq_lock:
            focused = _server._focused_freq_hz
        if focused is not None and not freq_matches(scan_result.center_freq_hz, focused):
            return
        cls = scan_result.classification
        fp = scan_result.fingerprint or {}  # fingerprint dict, may be None
        data = {
            "timestamp": scan_result.timestamp,
            "center_freq_hz": scan_result.center_freq_hz,
            "signal_type": cls.signal_type,
            "confidence": cls.confidence,
            "confidence_score": cls.confidence_score,
            "novel": cls.novel,
            "au_legal_status": cls.au_legal_status,
            "reasoning": cls.reasoning,
            # Fingerprint fields — added in Phase 10-Fix2
            "peak_power_db": fp.get("peak_power_db"),
            "peak_bin_power_db": fp.get("peak_bin_power_db"),
            # Phase 45 burst-detection fields (per-bin max-hold ratio). The
            # frontend consumes `is_burst` to drive the [PEAK] tag in
            # SignalHistoryLog as of Phase 45b; the other three are emitted
            # for forward-compatibility and dashboard tooling but not yet
            # rendered.
            "burst_ratio_db": fp.get("burst_ratio_db"),
            "expected_noise_ratio_db": fp.get("expected_noise_ratio_db"),
            "burst_excess_db": fp.get("burst_excess_db"),
            "is_burst": fp.get("is_burst"),
            "snr_db": fp.get("snr_db"),
            # Per-band threshold fields — added in Phase 11
            "signal_threshold_db": fp.get("signal_threshold_db", 0.0),
            "snr_margin_db": fp.get("snr_margin_db"),
            "bandwidth_hz": fp.get("bandwidth_hz"),
            "spectral_flatness": fp.get("spectral_flatness"),
            "chroma_distance": fp.get("chroma_distance"),
            "source": "fingerprint",
        }
        _server.socketio.emit("scan_result", data)

    last_spectrum_emit_time: float | None = None
    spectrum_emit_lock = threading.Lock()

    def broadcast_spectrum(
        psd_db: list,
        center_freq_hz: float,
        freq_min_hz: float,
        freq_max_hz: float,
    ) -> None:
        """Emit spectrum updates at up to 30 Hz with PSD rounded to 0.1 dB.

        The cap is shared across centre frequencies for this server call.
        Updates inside the interval are dropped without being queued.
        Updates at the next emit deadline are accepted. Rate, precision and
        SocketIO are read from dashboard.server on each call.
        """
        nonlocal last_spectrum_emit_time
        with spectrum_emit_lock:
            now = time.monotonic()
            if (
                last_spectrum_emit_time is not None
                and now < last_spectrum_emit_time + 1 / _server.SPECTRUM_MAX_RATE_HZ
            ):
                return
            last_spectrum_emit_time = now

        values = psd_db.tolist() if hasattr(psd_db, "tolist") else psd_db
        data = {
            "psd_db": [
                round(float(v), _server.SPECTRUM_DB_DECIMALS) for v in values
            ],
            "center_freq_hz": center_freq_hz,
            "freq_min_hz": freq_min_hz,
            "freq_max_hz": freq_max_hz,
        }
        _server.socketio.emit("spectrum_update", data)

    start_server._broadcast_fn = broadcast
    start_server._broadcast_spectrum_fn = broadcast_spectrum

    return broadcast
