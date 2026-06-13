#!/usr/bin/env python3
"""
Mimir — live scan entry point.
Usage: python scan.py
       MIMIR_LLM_URL=http://host:port/v1 python scan.py
"""

import logging
import os
import sys
import time

from core.config.loader import load_config
from core.device.hackrf_rx import HackRFReceiver
from core.pipeline.scanner import ScanRunner
from dashboard.server import emit_acars_message, emit_ais_message, emit_adsb_aircraft, start_server
from embeddings.embedder import SpectrumEmbedder
from embeddings.store import SignalStore
from llm.classifier import SignalClassifier
from modules.acars import AcarsSubscriber
from modules.ais import AisSubscriber
from modules.adsb import AdsbSubscriber

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
        config.llm_url,
    )
    classifier = SignalClassifier(base_url=llm_url)

    scanner = ScanRunner(device, embedder, store, classifier, config)

    acars_subscriber = AcarsSubscriber(broadcast_fn=emit_acars_message)
    acars_subscriber.start()
    scanner.register_iq_subscriber(acars_subscriber)

    ais_subscriber = AisSubscriber(broadcast_fn=emit_ais_message)
    ais_subscriber.start()
    scanner.register_iq_subscriber(ais_subscriber)

    adsb_subscriber = AdsbSubscriber(broadcast_fn=emit_adsb_aircraft)
    adsb_subscriber.start()
    scanner.register_iq_subscriber(adsb_subscriber)

    broadcast = start_server(
        config.dashboard_host, config.dashboard_port,
        device=device, scanner=scanner,
    )
    broadcast_spectrum = start_server._broadcast_spectrum_fn
    scanner._broadcast_fn = broadcast
    scanner._broadcast_spectrum_fn = broadcast_spectrum

    print(f"Mimir — live scan started. Press Ctrl+C to stop.")
    print(f"Dashboard: http://{config.dashboard_host}:{config.dashboard_port}")
    print(f"Scanning {len(config.frequencies_hz)} frequencies, "
          f"{config.dwell_time_sec}s dwell, queue depth {config.queue_maxsize}")

    try:
        scanner.run()
    except KeyboardInterrupt:
        print("\nScan stopped by user.")
    except Exception as e:
        logger.error("Fatal error in scan loop: %s", e)
    finally:
        scanner.stop()
        acars_subscriber.stop()
        ais_subscriber.stop()
        adsb_subscriber.stop()
        device.close()
        time.sleep(1.0)   # give SoapySDR time to release USB before exit
        print("HackRF closed cleanly.")
        sys.exit(0)


if __name__ == "__main__":
    main()
