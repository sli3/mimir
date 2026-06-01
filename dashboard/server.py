import logging
import os
import threading

from flask import Flask
from flask_socketio import SocketIO

from core.pipeline.scan_result import ScanResult

logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder="static", static_url_path="/static")
socketio = SocketIO(app, async_mode="threading", cors_allowed_origins="*")


def start_server(host: str, port: int):
    def run_flask():
        socketio.run(app, host=host, port=port, debug=False, use_reloader=False)

    t = threading.Thread(target=run_flask, daemon=True)
    t.start()
    logger.info("Dashboard server started on http://%s:%d", host, port)

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

    return broadcast


@app.route("/")
def index():
    from flask import send_from_directory
    return send_from_directory(
        os.path.join(os.path.dirname(__file__), "static"),
        "index.html"
    )
