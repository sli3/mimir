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
from pathlib import Path

from core.config.loader import load_config
from core.device.factory import build_device
from core.device.detect import detect_device
from core.device.profiles import DEVICE_PROFILES
from core.pipeline.demo_producer import DemoProducer
from core.pipeline.scanner import ScanRunner
import dashboard.shared_state as shared_state
from dashboard.server import emit_acars_message, emit_ais_message, emit_adsb_aircraft, emit_adsb_scan_result, start_server
from embeddings.embedder import SpectrumEmbedder
from embeddings.store import SignalStore
from llm.classifier import SignalClassifier
from llm.demo_classifier import DemoSignalClassifier
from modules.acars import AcarsSubscriber
from modules.ais import AisSubscriber
from modules.adsb import AdsbSubscriber
import sigmf

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
    constraint. Omitting --device triggers auto-selection via
    core.device.detect.detect_device(): Pluto is preferred when both
    devices are present (2026-07-15 decision), otherwise the only device
    found. Pass --device explicitly to force a specific driver — this is
    the manual override path for the six sub-325 MHz bands when the Pluto
    is the connected device.
    """
    parser = argparse.ArgumentParser(
        description="Mimir — AI-powered passive RF spectrum scanner (RX only)."
    )
    parser.add_argument(
        "--device",
        default=None,
        choices=sorted(DEVICE_PROFILES.keys()),
        help="SDR device to open. Omit to auto-select: Pluto is preferred when both are present, otherwise the only device found. Pass an explicit driver to force it.",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help=(
            "Run in demo mode: loop SigMF files through the classifier "
            "pipeline with cached LLM responses, no hardware, no live LLM."
        ),
    )
    parser.add_argument(
        "--demo-files",
        nargs="+",
        default=None,
        help=(
            "One or more SigMF metadata files (.sigmf-meta) to loop in demo "
            "mode. Required when --demo is set."
        ),
    )
    parser.add_argument(
        "--demo-cache",
        default=None,
        help=(
            "Path to the demo cache JSON file. Defaults to "
            "data/demo_cache/<first-file-stem>.json. Must exist or startup "
            "fails fast."
        ),
    )

    args = parser.parse_args()

    if args.demo and args.device is not None:
        parser.error("--demo and --device are mutually exclusive")
    if args.demo and not args.demo_files:
        parser.error("--demo-files is required when --demo is set")

    return args


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

    Parses --device, loads config, auto-selects or honours an explicit
    --device (Pluto is preferred when both are present, per the
    2026-07-15 multi-device decision), initialises the AI pipeline
    (embeddings, ChromaDB store, LLM classifier), registers decoder
    subscribers (ACARS, AIS, ADS-B), starts the Flask-SocketIO dashboard,
    and enters the scan loop.
    Ctrl+C stops the scan gracefully.

    Device selection:
    With Pluto (auto-selected or explicit --device plutosdr), the
    configured frequencies are checked against the Pluto's supported
    bands BEFORE the device is opened. If no
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

    if args.demo:
        # ------------------------------------------------------------------
        # DEMO MODE (Phase 76): replay SigMF files through the real AI loop
        # with cached LLM responses. No hardware, no live LLM, no decoder
        # subscribers. ACARS/AIS/ADS-B modules are not started because they
        # need raw IQ, not pre-fingerprinted chunks.
        # ------------------------------------------------------------------
        demo_files = [Path(p) for p in args.demo_files]
        missing = [p for p in demo_files if not p.exists()]
        if missing:
            for p in missing:
                logger.error("Demo file not found: %s", p)
            sys.exit(1)

        first_path = demo_files[0]
        if args.demo_cache is not None:
            cache_path = Path(args.demo_cache)
        else:
            cache_dir = Path("data/demo_cache")
            cache_dir.mkdir(parents=True, exist_ok=True)
            cache_path = cache_dir / f"{first_path.stem}.json"

        if not cache_path.exists():
            logger.error(
                "Demo cache not found: %s. Generate it with "
                "tools/generate_demo_cache.py or pass --demo-cache.",
                cache_path,
            )
            sys.exit(1)

        config = load_config("config/mimir.yaml")

        # DemoDevice is a hardware placeholder: the dashboard only reads
        # ``is_open`` (which is False, truthfully) and ``close()`` (no-op).
        # Any other attribute access raises NotImplementedError.
        class DemoDevice:
            driver = "hackrf"
            is_open = False

            def close(self) -> None:
                pass

            def __getattr__(self, name: str):
                raise NotImplementedError(
                    f"DemoDevice.{name!r} — demo mode does not open hardware"
                )

        # Read the device profile recorded in the first demo file. This
        # must be a real DEVICE_PROFILES key ("hackrf" or "plutosdr") so
        # ScanRunner's constructor and the dashboard's unsupported-band
        # logic accept it.
        try:
            first_meta = sigmf.fromfile(str(first_path))
            device_driver = first_meta.get_global_field("mimir:device_profile")
        except Exception as exc:
            logger.error("Could not read first demo file %s: %s", first_path, exc)
            sys.exit(1)
        device_driver = device_driver or "hackrf"

        with shared_state.current_device_lock:
            shared_state.current_device = device_driver

        embedder = SpectrumEmbedder()
        store = SignalStore(path="data/vectorstore")
        # Demo mode queries the existing store but never adds to it — the
        # cache holds pre-computed LLM responses, so no live ingestion is
        # needed or wanted.
        classifier = DemoSignalClassifier(cache_path=Path(cache_path))

        scanner = ScanRunner(
            DemoDevice(), embedder, store, classifier, config,
            device_driver=device_driver,
            is_demo_device=True,
        )

        broadcast = start_server(
            config.dashboard_host, config.dashboard_port,
            device=DemoDevice(), scanner=scanner,
        )
        scanner._broadcast_fn = broadcast
        scanner._broadcast_spectrum_fn = start_server._broadcast_spectrum_fn

        producer = DemoProducer(
            sigmf_files=demo_files,
            embedder=embedder,
            scanner=scanner,
            config=config,
            broadcast_spectrum_fn=scanner._broadcast_spectrum_fn,
        )
        producer.start()

        print("Mimir — DEMO MODE")
        print(f"Replaying: {', '.join(str(p) for p in demo_files)}")
        print(f"Cache: {cache_path}")
        print("No hardware. No live LLM connection. Dashboard live and interactive.")
        print(f"Dashboard: http://{config.dashboard_host}:{config.dashboard_port}")

        fatal_error = False
        try:
            scanner.start_ai_only()
        except KeyboardInterrupt:
            print("\nDemo stopped by user.")
        except Exception as e:
            logger.error("Fatal error in demo AI loop: %s", e)
            fatal_error = True
        finally:
            scanner.stop()
            producer.stop()
            if producer._thread is not None:
                producer._thread.join(timeout=2.0)
            print("Demo stopped.")
            sys.exit(1 if fatal_error else 0)

    try:
        detected = detect_device(preferred=args.device)
    except RuntimeError as exc:
        logger.error(
            "SDR detection failed: %s. Pass --device to force one, or check the USB connection.",
            exc,
        )
        sys.exit(1)
    driver = detected.driver
    # Record the active device driver in shared state so the dashboard
    # system_stats payload (and the frontend's band greying) reflects the
    # device the user actually launched with. Runs for BOTH devices, not
    # just Pluto — the empty map HackRF produces is the zero-visual-change
    # case the frontend test depends on.
    with shared_state.current_device_lock:
        shared_state.current_device = driver
    display_name = detected.display_name
    logger.info("Selected device driver: %s (%s)", driver, display_name)

    config = load_config("config/mimir.yaml")

    # Pluto startup-focus check — runs BEFORE the device is built or
    # opened, so a doomed startup never opens the hardware.
    pluto_focus: tuple[float, str] | None = None
    if driver == "plutosdr":
        pluto_focus = _first_supported_freq(config.frequencies_hz, driver)
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
            driver,
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
                         device_driver=driver)

    # Focus Pluto on its first supported frequency and set current_band to
    # match, so the per-band threshold and crop window are correct from the
    # first scan cycle. Without this the scanner would start on
    # frequencies_hz[0], which is typically 98 MHz FM — below Pluto's floor.
    if driver == "plutosdr" and pluto_focus is not None:
        focus_freq_hz, focus_band_key = pluto_focus
        scanner.set_focus_frequency(focus_freq_hz)
        with shared_state.current_band_lock:
            # Resolve via the device-aware helper (Phase 65, Finding A) so
            # Pluto's calibrated signal_threshold_db/gain_db overlay is
            # applied from the first scan cycle, not the HackRF values.
            shared_state.current_band = shared_state.resolve_band_profile(
                focus_band_key, driver
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
