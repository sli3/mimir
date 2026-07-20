#!/usr/bin/env python3
"""
Mimir — live scan entry point.
Usage: python scan.py [--device hackrf|plutosdr]
       MIMIR_LLM_URL=http://host:port/v1 python scan.py

LEGAL: Receive-only. Radiocommunications Act 1992 (Cth).
       No transmission. Jurisdiction: AU/SA. Authority: ACMA.
"""

import argparse
import logging
import os
import sys
import time

from core.config.loader import load_config
from core.device.factory import build_device
from core.device.profiles import DEVICE_PROFILES
from core.pipeline.scanner import ScanRunner
import dashboard.shared_state as shared_state
from dashboard.server import emit_acars_message, emit_ais_message, emit_adsb_aircraft, emit_adsb_scan_result, start_server
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


def _parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    --device selects which SDR hardware to open. Both supported devices
    are TX-capable and operate under Mimir's software-enforced receive-only
    constraint. HackRF remains the default: its 1 MHz–6 GHz tuning range
    covers every band in the current plan, whereas the Pluto's stock
    325 MHz floor excludes six of the eight bands.
    """
    parser = argparse.ArgumentParser(
        description="Mimir — AI-powered passive RF spectrum scanner (RX only)."
    )
    parser.add_argument(
        "--device",
        default="hackrf",
        choices=sorted(DEVICE_PROFILES.keys()),
        help="SDR device to open (default: hackrf).",
    )
    return parser.parse_args()


def _first_supported_freq(
    frequencies_hz: list[float], device_driver: str
) -> tuple[float, str] | None:
    """Return the first (freq_hz, band_key) pair the device can receive.

    Iterates the configured frequencies in order and returns the first
    whose band is supported by the named device, or None if no configured
    frequency is receivable on it. Uses the real band lookup helpers so
    the answer always matches what the scan loop's unsupported-band guard
    would decide at runtime.

    A frequency must satisfy two conditions to be receivable:
    (a) it falls within the device's physical tuning range
        (DEVICE_PROFILES[device_driver].min_freq_hz/max_freq_hz), and
    (b) the resolved band is flagged supported for the device.
    Either failing means the frequency is rejected — the band lookup alone
    is not enough, because a freq that doesn't match any band exactly
    resolves to the nearest supported band and would otherwise slip
    through.
    """
    profile = DEVICE_PROFILES[device_driver]
    min_hz = profile["min_freq_hz"]
    max_hz = profile["max_freq_hz"]
    for freq_hz in frequencies_hz:
        if freq_hz < min_hz or freq_hz > max_hz:
            continue
        band_key = shared_state.band_key_for_freq(freq_hz)
        if band_key is not None and shared_state.band_supported_by_device(
            band_key, device_driver
        ):
            return float(freq_hz), band_key
    return None


def main() -> None:
    """Start the Mimir live scanner and dashboard.

    Parses --device, loads config, opens the selected SDR (HackRF by
    default), initialises the AI pipeline (embeddings, ChromaDB store,
    LLM classifier), registers decoder subscribers (ACARS, AIS, ADS-B),
    starts the Flask-SocketIO dashboard, and enters the scan loop.
    Ctrl+C stops the scan gracefully.

    Device selection:
    With --device plutosdr, the configured frequencies are checked against
    the Pluto's supported bands BEFORE the device is opened. If no
    configured frequency is receivable, the process logs an error and
    exits with code 1 without ever opening the hardware. Otherwise the
    scanner is focused on the first supported frequency and current_band
    is set to match, so per-band thresholds are correct from the first
    scan cycle.

    If the device cannot be opened (not connected, USB error), logs an
    error and exits with code 1 instead of crashing with a traceback.

    If the scan loop encounters an unexpected error, the process exits with
    code 1 (via a ``fatal_error`` flag in the ``finally`` block) to
    distinguish intentional stops from failures. Previously all non-startup
    paths exited 0.
    """
    args = _parse_args()
    display_name = DEVICE_PROFILES[args.device]["display_name"]
    logger.info("Selected device driver: %s (%s)", args.device, display_name)

    config = load_config("config/mimir.yaml")

    # Pluto startup-focus check — runs BEFORE the device is built or
    # opened, so a doomed startup never opens the hardware.
    pluto_focus: tuple[float, str] | None = None
    if args.device == "plutosdr":
        pluto_focus = _first_supported_freq(config.frequencies_hz, args.device)
        if pluto_focus is None:
            logger.error(
                "No configured frequency is receivable on the %s "
                "(supported bands: ism 915 MHz, adsb 1090 MHz). "
                "Add one to scanner.frequencies_hz in config/mimir.yaml.",
                display_name,
            )
            sys.exit(1)

    try:
        device = build_device(
            args.device,
            lna_gain_db=config.lna_gain_db,
            vga_gain_db=config.vga_gain_db,
            amp_enable=config.amp_enable,
        )
        device.open()
    except (RuntimeError, OSError) as exc:
        logger.error("Startup failed: %s. Is the %s connected?", exc, display_name)
        sys.exit(1)

    embedder = SpectrumEmbedder()
    store = SignalStore(path="data/vectorstore")
    llm_url = os.environ.get(
        "MIMIR_LLM_URL",
        config.llm_url,
    )
    classifier = SignalClassifier(
        base_url=llm_url,
        cooldown_sec=config.llm_cooldown_sec,
        connect_timeout_sec=config.llm_connect_timeout_sec,
    )

    logger.info("Checking LLM server connectivity at startup...")
    classifier.check_connection()

    scanner = ScanRunner(device, embedder, store, classifier, config,
                         device_driver=args.device)

    # Focus Pluto on its first supported frequency and set current_band to
    # match, so the per-band threshold and crop window are correct from the
    # first scan cycle. Without this the scanner would start on
    # frequencies_hz[0], which is typically 98 MHz FM — below Pluto's floor.
    if args.device == "plutosdr" and pluto_focus is not None:
        focus_freq_hz, focus_band_key = pluto_focus
        scanner.set_focus_frequency(focus_freq_hz)
        with shared_state.current_band_lock:
            shared_state.current_band = dict(
                shared_state.BAND_PROFILES[focus_band_key]
            )
        logger.info(
            "Pluto startup focus: %.3f MHz (%s)",
            focus_freq_hz / 1e6, focus_band_key,
        )

    acars_subscriber = AcarsSubscriber(broadcast_fn=emit_acars_message)
    acars_subscriber.start()
    scanner.register_iq_subscriber(acars_subscriber)

    ais_subscriber = AisSubscriber(broadcast_fn=emit_ais_message)
    ais_subscriber.start()
    scanner.register_iq_subscriber(ais_subscriber)

    adsb_subscriber = AdsbSubscriber(
        broadcast_fn=emit_adsb_aircraft,
        scan_result_fn=emit_adsb_scan_result,
    )
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
    print(f"Device: {display_name}")
    print(f"Dashboard: http://{config.dashboard_host}:{config.dashboard_port}")
    print(f"Focus mode: cycling through {len(config.frequencies_hz)} band(s) one at a time, "
          f"{config.dwell_time_sec}s dwell, queue depth {config.queue_maxsize}")

    fatal_error = False
    try:
        scanner.run()
    except KeyboardInterrupt:
        print("\nScan stopped by user.")
    except Exception as e:
        logger.error("Fatal error in scan loop: %s", e)
        fatal_error = True
    finally:
        scanner.stop()
        acars_subscriber.stop()
        ais_subscriber.stop()
        adsb_subscriber.stop()
        device.close()
        time.sleep(1.0)   # give SoapySDR time to release USB before exit
        print(f"{display_name} closed cleanly.")
        sys.exit(1 if fatal_error else 0)


if __name__ == "__main__":
    main()
