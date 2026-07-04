"""
capture_to_vectorstore.py — Live capture → vector store ingestion tool

Captures real IQ samples from the HackRF One across AU-legal receive bands,
computes spectral fingerprints, converts them to embeddings, and stores them
in the production ChromaDB vector store at ``data/vectorstore``.

Run this after reseeding or whenever live vectors are needed to refresh the
SignalStore used by the LLM classifier. After adding live vectors, re-run
``tools/calibrate_thresholds.py`` to update distance thresholds.

Gain and threshold values (lna_gain_db, vga_gain_db, signal_threshold_db) are
read live from ``dashboard.shared_state.BAND_PROFILES`` so they stay in sync
with the live dashboard configuration.

Legal: Receive-only. Radiocommunications Act 1992 (Cth).
       No transmission. Jurisdiction: AU/SA. Authority: ACMA.
"""

from core.pipeline.capture import capture_iq
from core.pipeline.fft import compute_psd
from core.pipeline.features import fingerprint_spectrum
from dashboard.shared_state import BAND_PROFILES
from embeddings.embedder import SpectrumEmbedder
from embeddings.store import SignalStore

import argparse
import logging
import time
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# ANSI colour helpers for terminal output
ANSI_GREEN = "\033[92m"
ANSI_YELLOW = "\033[93m"
ANSI_RED = "\033[91m"
ANSI_RESET = "\033[0m"

# Antenna-to-band mappings. Labels must match CAPTURE_TARGETS exactly.
ANTENNA_PROFILES: dict[str, dict] = {
    "1": {
        "name": "Telescopic whip",
        "range": "75 MHz – 700 MHz",
        "bands": [
            "FM_broadcast",
            "Aviation_VHF",
            "ACARS",
            "APRS",
            "AIS",
        ],
    },
    "2": {
        "name": "V-dipole 533mm",
        "range": "130 MHz – 145 MHz",
        "bands": [
            "Aviation_VHF",
            "ACARS",
            "APRS",
        ],
    },
    "3": {
        "name": "Spiral discone",
        "range": "800 MHz – 8500 MHz",
        "bands": [
            "ADS_B",
            "ISM_LoRa",
        ],
    },
}

# Per-band capture configuration. Values are read live from
# dashboard/shared_state.BAND_PROFILES so they stay in sync with the live
# dashboard thresholds and gains.
CAPTURE_TARGETS: list[dict] = [
    {
        "label": "FM_broadcast",
        "freq_hz": 98_900_000,
        "sample_rate_hz": 2_000_000,
        "num_samples": 256_000,
        "lna_gain_db": BAND_PROFILES["fm_broadcast"]["lna_gain_db"],
        "vga_gain_db": BAND_PROFILES["fm_broadcast"]["vga_gain_db"],
        "signal_threshold_db": BAND_PROFILES["fm_broadcast"]["signal_threshold_db"],
        "captures": 5,
    },
    {
        "label": "Aviation_VHF",
        "freq_hz": 127_000_000,
        "sample_rate_hz": 2_000_000,
        "num_samples": 256_000,
        "lna_gain_db": BAND_PROFILES["aviation"]["lna_gain_db"],
        "vga_gain_db": BAND_PROFILES["aviation"]["vga_gain_db"],
        "signal_threshold_db": BAND_PROFILES["aviation"]["signal_threshold_db"],
        "captures": 5,
    },
    {
        "label": "ACARS",
        "freq_hz": 129_125_000,
        "sample_rate_hz": 2_000_000,
        "num_samples": 256_000,
        "lna_gain_db": BAND_PROFILES["acars"]["lna_gain_db"],
        "vga_gain_db": BAND_PROFILES["acars"]["vga_gain_db"],
        "signal_threshold_db": BAND_PROFILES["acars"]["signal_threshold_db"],
        "captures": 5,
    },
    {
        "label": "APRS",
        "freq_hz": 145_175_000,
        "sample_rate_hz": 2_000_000,
        "num_samples": 256_000,
        "lna_gain_db": BAND_PROFILES["aprs"]["lna_gain_db"],
        "vga_gain_db": BAND_PROFILES["aprs"]["vga_gain_db"],
        "signal_threshold_db": BAND_PROFILES["aprs"]["signal_threshold_db"],
        "captures": 5,
    },
    {
        "label": "AIS",
        "freq_hz": 162_000_000,
        "sample_rate_hz": 2_000_000,
        "num_samples": 256_000,
        "lna_gain_db": BAND_PROFILES["ais"]["lna_gain_db"],
        "vga_gain_db": BAND_PROFILES["ais"]["vga_gain_db"],
        "signal_threshold_db": BAND_PROFILES["ais"]["signal_threshold_db"],
        "captures": 5,
    },
    {
        "label": "ISM_LoRa",
        "freq_hz": 915_000_000,
        "sample_rate_hz": 2_000_000,
        "num_samples": 256_000,
        "lna_gain_db": BAND_PROFILES["ism"]["lna_gain_db"],
        "vga_gain_db": BAND_PROFILES["ism"]["vga_gain_db"],
        "signal_threshold_db": BAND_PROFILES["ism"]["signal_threshold_db"],
        "captures": 5,
    },
    {
        "label": "ADS_B",
        "freq_hz": 1_090_000_000,
        "sample_rate_hz": 2_000_000,
        "num_samples": 256_000,
        "lna_gain_db": BAND_PROFILES["adsb"]["lna_gain_db"],
        "vga_gain_db": BAND_PROFILES["adsb"]["vga_gain_db"],
        "signal_threshold_db": BAND_PROFILES["adsb"]["signal_threshold_db"],
        "captures": 5,
    },
]


def _colour(text: str, code: str) -> str:
    """Wrap text in an ANSI colour code."""
    return f"{code}{text}{ANSI_RESET}"


def _print_band_warning(label: str) -> None:
    """Print a one-time warning for bands that need live signals.

    ADS-B, ACARS, and AIS only produce real fingerprints when aircraft or
    vessels are within range. Without them the tool captures noise-floor
    vectors, which degrades the production vector store.
    """
    warnings = {
        "ADS_B": (
            "ADS-B CAPTURE WARNING",
            [
                "ADS-B (1090 MHz) transmits position data from aircraft in flight.",
                "Signal will only be present if an aircraft is overhead.",
                "Without an aircraft, only noise will be captured for this band.",
                "Check live aircraft positions at: https://www.flightradar24.com",
            ],
        ),
        "ACARS": (
            "ACARS CAPTURE WARNING",
            [
                "ACARS (129.125 MHz) transmits data bursts from aircraft in flight.",
                "Signal will only be present if an aircraft is actively transmitting overhead.",
                "Without an active aircraft, only noise will be captured for this band.",
                "Check live aircraft at: https://www.flightradar24.com",
            ],
        ),
        "AIS": (
            "AIS CAPTURE WARNING",
            [
                "AIS (162 MHz) transmits position data from vessels at sea or in port.",
                "Signal will only be present if a vessel is within range (~20–50 km).",
                "Without vessels in range, only noise will be captured for this band.",
                "Check live vessel positions at: https://www.marinetraffic.com",
            ],
        ),
    }

    title, body_lines = warnings[label]
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)
    print()
    for line in body_lines:
        print(line)
    print()


def build_metadata(
    label: str,
    antenna_name: str,
    target: dict,
    fingerprint: dict,
    cap_idx: int,
) -> dict:
    """Build ChromaDB metadata for a stored capture record."""
    return {
        "label": str(label),
        "source": "live_capture",
        "antenna": str(antenna_name),
        "freq_hz": int(target["freq_hz"]),
        "sample_rate_hz": int(target["sample_rate_hz"]),
        "capture_origin": "Adelaide, SA, AU",
        "signal_threshold_db": float(target["signal_threshold_db"]),
        "timestamp": datetime.now().isoformat(),
        "peak_power_db": float(fingerprint["peak_power_db"]),
        "snr_db": float(fingerprint["snr_db"]),
        "capture_index": int(cap_idx),
    }


def _parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Capture live IQ samples across AU-legal RX bands and store "
            "spectrum embeddings in data/vectorstore."
        ),
    )
    parser.add_argument(
        "--wipe",
        action="store_true",
        help="Delete the existing vector store collection before capture.",
    )
    return parser.parse_args()


def _select_antenna() -> tuple[str, dict]:
    """Prompt the user to select an antenna profile.

    Returns:
        Tuple of (choice_key, profile_dict).
    """
    print("\n" + "=" * 70)
    print("ANTENNA SELECTION")
    print("=" * 70)
    print()
    print("Select the antenna connected to the HackRF.")
    print("This determines which frequency bands will be captured.")
    print()
    print("  1. Telescopic whip    (75 MHz – 700 MHz)")
    print("  2. V-dipole 533mm     (130 MHz – 145 MHz)")
    print("  3. Spiral discone     (800 MHz – 8500 MHz)")
    print()

    antenna_choice = None
    while antenna_choice not in ANTENNA_PROFILES:
        try:
            antenna_choice = input("Enter choice (1/2/3) or Ctrl+C to abort: ").strip()
        except KeyboardInterrupt:
            logger.info("User aborted capture at antenna selection")
            print()
            raise SystemExit(0)
        if antenna_choice not in ANTENNA_PROFILES:
            print("Invalid choice. Please enter 1, 2, or 3.")

    return antenna_choice, ANTENNA_PROFILES[antenna_choice]


def run_capture_loop(
    store: SignalStore,
    embedder: SpectrumEmbedder,
    selected_targets: list[dict],
    antenna_name: str,
    input_func=input,
    sleep_func=time.sleep,
) -> int:
    """Run the capture → fingerprint → embed → store loop.

    Args:
        store: Initialised SignalStore.
        embedder: Initialised SpectrumEmbedder.
        selected_targets: List of target dicts to capture.
        antenna_name: Human-readable antenna name for metadata.
        input_func: Callable matching built-in input() signature.
        sleep_func: Callable matching time.sleep() signature.

    Returns:
        Number of records successfully stored this run.
    """
    captured_count = 0
    total_targets = len(selected_targets)

    for idx, target in enumerate(selected_targets):
        label = target["label"]
        freq_hz = target["freq_hz"]
        num_samples = target["num_samples"]
        sample_rate_hz = target["sample_rate_hz"]
        lna_gain_db = target["lna_gain_db"]
        vga_gain_db = target["vga_gain_db"]
        signal_threshold_db = target["signal_threshold_db"]
        captures = target["captures"]

        for cap_idx in range(captures):
            timestamp_ms = int(time.time() * 1000)
            record_id = f"{label}_{cap_idx}_{timestamp_ms}"

            print(f"\n[{idx + 1}/{total_targets}] Capturing: {label}")
            print(f"  Frequency: {freq_hz / 1e6:.3f} MHz")
            print(f"  Samples: {num_samples:,}")
            print(f"  Capture #{cap_idx + 1}/{captures}")
            print(f"  Gain: LNA={lna_gain_db} dB, VGA={vga_gain_db} dB")
            print(f"  Threshold: {signal_threshold_db:.1f} dB")

            if cap_idx == 0 and label in ("ADS_B", "ACARS", "AIS"):
                _print_band_warning(label)
                try:
                    input_func("Press ENTER to continue or Ctrl+C to skip this band: ")
                except KeyboardInterrupt:
                    logger.info("User skipped %s band", label)
                    print(f"\n  Skipping {label} — no captures stored for this band.")
                    break

            try:
                samples = capture_iq(
                    freq_hz=freq_hz,
                    num_samples=num_samples,
                    sample_rate_hz=sample_rate_hz,
                    lna_gain_db=lna_gain_db,
                    vga_gain_db=vga_gain_db,
                )

                psd_result = compute_psd(
                    samples=samples,
                    sample_rate_hz=sample_rate_hz,
                    center_freq_hz=freq_hz,
                )

                fingerprint = fingerprint_spectrum(
                    psd_result,
                    signal_threshold_db=signal_threshold_db,
                )

                vector = embedder.embed(fingerprint)
                metadata = build_metadata(label, antenna_name, target, fingerprint, cap_idx)
                record = {
                    "id": record_id,
                    "embedding": vector,
                    "metadata": metadata,
                }
                store.add(record)
                captured_count += 1

                snr_margin_db = fingerprint["snr_margin_db"]
                if snr_margin_db > 0:
                    margin_colour = ANSI_GREEN
                elif snr_margin_db == 0:
                    margin_colour = ANSI_YELLOW
                else:
                    margin_colour = ANSI_RED

                print(
                    f"  ✓ Stored: peak={fingerprint['peak_power_db']:.2f} dB, "
                    f"SNR={fingerprint['snr_db']:.2f} dB, "
                    f"margin={_colour(f'{snr_margin_db:.2f} dB', margin_colour)}"
                )

            except RuntimeError as err:
                logger.error("Capture failed for %s (capture %d): %s", label, cap_idx, err)
                print(f"  ✗ FAILED: {err}")
                continue

            is_last = (
                idx == total_targets - 1
                and cap_idx == captures - 1
            )
            if not is_last:
                logger.info("Waiting 5 seconds before next capture")
                sleep_func(5)

    return captured_count


def main() -> None:
    """
    Main capture-to-vectorstore workflow.

    1. Parse CLI arguments (so --help works without user interaction).
    2. Prompt user to select connected antenna; filter bands accordingly.
    3. Initialise production vectorstore, optionally wiping existing data.
    4. Capture IQ samples for each target, run through pipeline, store vectors.
       Per-band warnings for ADS-B, ACARS, and AIS fire before the first
       capture of each such band.
    5. Print summary and remind operator to recalibrate thresholds.

    All capture and processing is RX-only — no transmit functionality.
    """
    args = _parse_args()
    logger.info("Starting Mimir capture-to-vectorstore workflow")

    antenna_choice, profile = _select_antenna()
    selected_bands = set(profile["bands"])
    selected_targets = [t for t in CAPTURE_TARGETS if t["label"] in selected_bands]

    skipped_labels = sorted(
        t["label"] for t in CAPTURE_TARGETS if t["label"] not in selected_bands
    )

    print()
    print(f"Antenna: {profile['name']}")
    print(f"Bands to capture: {', '.join(t['label'] for t in selected_targets)}")
    if skipped_labels:
        print(f"Skipping: {', '.join(skipped_labels)} (outside this antenna's range)")
    print()
    print(
        "NOTE: ADS-B, ACARS, and AIS require live aircraft or vessel signals. "
        "You will be prompted before each of those bands."
    )

    store_path = Path("data/vectorstore")
    store_path.mkdir(parents=True, exist_ok=True)

    store = SignalStore(path=str(store_path))
    print(f"Current vector store record count: {store.count()}")

    # --wipe is destructive: it deletes the entire ChromaDB collection before
    # capture starts. No interactive confirmation is shown (accepted per security
    # review). If scan.py is running concurrently, SQLite lock errors may occur
    # because both processes write to the same data/vectorstore/ directory.
    if args.wipe:
        print()
        print(_colour("WARNING: --wipe flag set.", ANSI_YELLOW))
        print("The existing vector store collection will be deleted before capture.")
        print("All previous embeddings will be lost.")
        store.delete_collection()
        store = SignalStore(path=str(store_path))
        print("Vector store wiped and reinitialised.")

    embedder = SpectrumEmbedder()

    captured_count = run_capture_loop(
        store=store,
        embedder=embedder,
        selected_targets=selected_targets,
        antenna_name=profile["name"],
    )

    print("\n" + "=" * 70)
    print("CAPTURE COMPLETE")
    print("=" * 70)
    print(f"Records captured this run: {captured_count}")
    print(f"New vector store total: {store.count()}")
    print()
    print("Run tools/calibrate_thresholds.py to recompute distance thresholds after adding live vectors.")
    logger.info("Capture-to-vectorstore complete. %d records stored.", captured_count)


if __name__ == "__main__":
    main()
