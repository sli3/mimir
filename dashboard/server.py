import logging
import os
import threading
import time

from flask import Flask
from flask_socketio import SocketIO

from core.pipeline.scan_result import ScanResult

logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder="static", static_url_path="")
socketio = SocketIO(app, async_mode="threading", cors_allowed_origins="*")

_device_ref = None
_last_hw_error_time = 0.0


def record_hw_error() -> None:
    global _last_hw_error_time
    _last_hw_error_time = time.time()


def _compute_hackrf_status() -> str:
    if _device_ref is None or not _device_ref.is_open:
        return "DISCONNECTED"
    if time.time() - _last_hw_error_time < 30.0:
        return "NOT_RESPONDING"
    return "CONNECTED"


def start_server(host: str, port: int, device=None):
    global _device_ref
    _device_ref = device

    def run_flask():
        socketio.run(app, host=host, port=port, debug=False, use_reloader=False)

    t = threading.Thread(target=run_flask, daemon=True)
    t.start()
    logger.info("Dashboard server started on http://%s:%d", host, port)

    def emit_stats():
        while True:
            time.sleep(2.0)
            data = {
                "hackrf_status": _compute_hackrf_status(),
                "active_frequency_hz": None,
                "scan_count": 0,
                "queue_depth": 0,
                "llm_last_inference_ms": None,
            }
            socketio.emit("system_stats", data)

    _stats_thread = threading.Thread(target=emit_stats, daemon=True)
    _stats_thread.start()

    def broadcast(scan_result: ScanResult) -> None:
        cls = scan_result.classification
        data = {
            "timestamp": scan_result.timestamp,
            "center_freq_hz": scan_result.center_freq_hz,
            "signal_type": cls.signal_type,
            "confidence": cls.confidence,
            "confidence_score": cls.confidence_score,
            "novel": cls.novel,
            "au_legal_status": cls.au_legal_status,
            "reasoning": cls.reasoning,
        }
        socketio.emit("scan_result", data)

    def broadcast_spectrum(
        psd_db: list,
        center_freq_hz: float,
        freq_min_hz: float,
        freq_max_hz: float,
    ) -> None:
        data = {
            "psd_db": psd_db.tolist() if hasattr(psd_db, 'tolist') else psd_db,
            "center_freq_hz": center_freq_hz,
            "freq_min_hz": freq_min_hz,
            "freq_max_hz": freq_max_hz,
        }
        socketio.emit("spectrum_update", data)

    start_server._broadcast_fn = broadcast
    start_server._broadcast_spectrum_fn = broadcast_spectrum

    return broadcast


@app.route("/")
def index():
    from flask import send_from_directory
    return send_from_directory(
        os.path.join(os.path.dirname(__file__), "static"),
        "index.html"
    )
