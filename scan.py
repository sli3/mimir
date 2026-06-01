#!/usr/bin/env python3
"""
Mimir — live scan entry point.
Usage: python scan.py
       MIMIR_LLM_URL=http://host:port/v1 python scan.py
"""

import logging
import os
import sys

from core.config.loader import load_config
from core.device.hackrf_rx import HackRFReceiver
from core.pipeline.scanner import ScanRunner
from dashboard.server import start_server
from embeddings.embedder import SpectrumEmbedder
from embeddings.store import SignalStore
from llm.classifier import SignalClassifier

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

logger = logging.getLogger("scan")


def main() -> None:
    config = load_config("config/mimir.yaml")

    device = HackRFReceiver(
        lna_gain_db=config.lna_gain_db,
        vga_gain_db=config.vga_gain_db,
        amp_enable=config.amp_enable,
    )
    device.open()

    embedder = SpectrumEmbedder()
    store = SignalStore(path="data/vectorstore")
    llm_url = os.environ.get(
        "MIMIR_LLM_URL",
        "http://192.168.0.66:8080/v1",
    )
    classifier = SignalClassifier(base_url=llm_url)

    broadcast = start_server(config.dashboard_host, config.dashboard_port)

    scanner = ScanRunner(device, embedder, store, classifier, config)
    scanner._broadcast_fn = broadcast

    print(f"Mimir — live scan started. Press Ctrl+C to stop.")
    print(f"Dashboard: http://{config.dashboard_host}:{config.dashboard_port}")
    print(f"Scanning {len(config.frequencies_hz)} frequencies, "
          f"{config.dwell_time_sec}s dwell, queue depth {config.queue_maxsize}")

    try:
        scanner.run()
    except KeyboardInterrupt:
        scanner.stop()
        device.close()
        print("\nScan stopped. HackRF closed cleanly.")
        sys.exit(0)


if __name__ == "__main__":
    main()
