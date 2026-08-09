"""
capture_to_vectorstore.py — Live capture → vector store ingestion tool

Captures real IQ samples across AU-legal receive bands, computes spectral
fingerprints, converts them to embeddings, and stores them in the production
ChromaDB vector store at ``data/vectorstore``.

Supports TWO devices via --device:
  hackrf (default) — all 7 CAPTURE_TARGETS bands, split lna/vga gain.
  pluto             — ISM_LoRa and ADS_B only (the only two bands Pluto's
                       stock 325 MHz-3.8 GHz tuning range covers), combined
                       gain_db.

Run this after reseeding or whenever live vectors are needed to refresh the
SignalStore used by the LLM classifier. After adding live vectors, re-run
``tools/calibrate_thresholds.py`` to update distance thresholds.

Gain and threshold values are read live from ``dashboard.shared_state`` so
they stay in sync with the live dashboard configuration:
  --device hackrf : lna_gain_db, vga_gain_db, signal_threshold_db from
                     BAND_PROFILES.
  --device pluto   : gain_db, signal_threshold_db from PLUTO_BAND_PROFILES.
                     If PLUTO_BAND_PROFILES is missing or lacks a required
                     band, the tool exits with a clear error rather than
                     falling back to a guessed gain value — run
                     tools/diagnose_pluto_gain.py first and add the result
                     to dashboard/shared_state.py.

Legal: Receive-only. Radiocommunications Act 1992 (Cth).
       No transmission. Jurisdiction: AU/SA. Authority: ACMA.
"""

from core.pipeline.capture import capture_iq, capture_iq_pluto
from core.pipeline.fft import compute_psd
from core.pipeline.features import fingerprint_spectrum
from dashboard.shared_state import BAND_PROFILES
from embeddings.embedder import SpectrumEmbedder
from embeddings.store import SignalStore

import argparse
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# Pluto's stock tuning range (325 MHz - 3.8 GHz) only covers these two Mimir
# bands out of the seven in CAPTURE_TARGETS. Matches diagnose_pluto_gain.py's
# BAND_SWEEP scope exactly — same hardware limitation, same two bands.
PLUTO_SUPPORTED_LABELS = ("ISM_LoRa", "ADS_B")

# ANSI colour helpers for terminal output
ANSI_GREEN = "\033[92m"
ANSI_YELLOW = "\033[93m"
ANSI_RED = "\033[91m"
ANSI_RESET = "\033[0m"

# Antenna-to-band mappings. Labels must match CAPTURE_TARGETS exactly.
#
# ADS_B on "Telescopic whip": confirmed 2026-08 — retracted to ~68mm (quarter-
# wave monopole for 1090 MHz), the same physical whip used at longer
# extensions for FM/Aviation/ACARS/APRS/AIS gives noticeably better ADS-B
# reception than the spiral discone. This is ONE whip at DIFFERENT
# extensions per band, not a separate antenna — the tool prompts to
# re-adjust length before the ADS_B capture since its extension differs
# sharply from the other bands on this profile.
ANTENNA_PROFILES: dict[str, dict] = {
    "1": {
        "name": "Telescopic whip",
        "range": "75 MHz – 700 MHz (FM/Aviation/ACARS/APRS/AIS); ~1090 MHz when retracted to ~68mm for ADS_B",
        "bands": [
            "FM_broadcast",
            "Aviation_VHF",
            "ACARS",
            "APRS",
            "AIS",
            "ADS_B",
        ],
        "length_reminder": {
            "ADS_B": "Retract the telescopic whip to ~68mm (quarter-wave for 1090 MHz) before this capture — this is a much shorter extension than the other bands on this antenna.",
        },
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
        "trace_key": "psd_max_hold_db",
        "captures": 5,
    },
]


def _build_pluto_targets() -> list[dict]:
    """Build Pluto capture targets from PLUTO_BAND_PROFILES.

    Reuses the freq_hz/sample_rate_hz/num_samples/captures/trace_key values
    already defined in CAPTURE_TARGETS for ISM_LoRa and ADS_B — only the gain
    model changes (combined gain_db instead of split lna/vga). Support is
    checked via the existing band_supported_by_device() helper (the real
    source of truth for Pluto band support, per shared_state.py) rather than
    re-deriving it here. Gain and threshold still come straight from
    PLUTO_BAND_PROFILES, since band_supported_by_device() only returns a
    bool, not the gain values themselves.

    Raises:
        SystemExit: if PLUTO_BAND_PROFILES is missing entirely, or a band it
            marks as supported is missing gain_db/signal_threshold_db. This
            tool never guesses a gain value on the operator's behalf.
    """
    try:
        from dashboard.shared_state import (
            PLUTO_BAND_PROFILES,
            band_supported_by_device,
        )
    except ImportError:
        print(_colour(
            "\nERROR: dashboard.shared_state.PLUTO_BAND_PROFILES does not exist yet.\n"
            "Pluto capture needs calibrated gain values before it can run.\n"
            "Run tools/diagnose_pluto_gain.py, pick gain_db for ISM and ADS-B\n"
            "from the sweep output, and add a PLUTO_BAND_PROFILES dict to\n"
            "dashboard/shared_state.py (e.g. {'ism': {'gain_db': ..., "
            "'signal_threshold_db': ...}, 'adsb': {...}}).\n",
            ANSI_RED,
        ))
        raise SystemExit(1)

    pluto_targets = []
    for base in CAPTURE_TARGETS:
        label = base["label"]
        if label not in PLUTO_SUPPORTED_LABELS:
            continue
        key = LABEL_TO_BAND_KEY[label]

        if not band_supported_by_device(key, "plutosdr"):
            print(_colour(
                f"\nERROR: band_supported_by_device says Pluto does not "
                f"support '{key}' ({label}).\n"
                f"Reason: {PLUTO_BAND_PROFILES[key].get('reason', 'unknown')}\n",
                ANSI_RED,
            ))
            raise SystemExit(1)

        profile = PLUTO_BAND_PROFILES[key]
        if "gain_db" not in profile or "signal_threshold_db" not in profile:
            print(_colour(
                f"\nERROR: PLUTO_BAND_PROFILES['{key}'] is marked supported "
                f"but is missing 'gain_db' or 'signal_threshold_db'.\n"
                f"Run tools/diagnose_pluto_gain.py --band {key} and add the "
                f"result.\n",
                ANSI_RED,
            ))
            raise SystemExit(1)

        target = dict(base)  # copy freq_hz, sample_rate_hz, num_samples,
                              # captures, trace_key (if present) from the
                              # existing HackRF entry — only gain model differs
        target["gain_db"] = profile["gain_db"]
        target["signal_threshold_db"] = profile["signal_threshold_db"]
        # Drop HackRF-only keys so nothing downstream accidentally reads a
        # stale split-gain value for a Pluto target.
        target.pop("lna_gain_db", None)
        target.pop("vga_gain_db", None)
        pluto_targets.append(target)

    return pluto_targets


# HackRF/Pluto CAPTURE_TARGETS label -> lowercase key used by --band and by
# BAND_PROFILES/PLUTO_BAND_PROFILES. Single source of truth for this mapping
# — _build_pluto_targets() also uses this instead of keeping its own copy.
LABEL_TO_BAND_KEY = {
    "FM_broadcast": "fm_broadcast",
    "Aviation_VHF": "aviation",
    "ACARS": "acars",
    "APRS": "aprs",
    "AIS": "ais",
    "ISM_LoRa": "ism",
    "ADS_B": "adsb",
}


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
    device: str = "hackrf",
) -> dict:
    """Build ChromaDB metadata for a stored capture record."""
    return {
        "label": str(label),
        "source": "live_capture",
        "device": str(device),
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
    parser.add_argument(
        "--device",
        choices=["hackrf", "pluto"],
        default="hackrf",
        help=(
            "SDR device to capture from (default: hackrf). Pluto only "
            "supports ISM_LoRa and ADS_B (its stock 325 MHz-3.8 GHz tuning "
            "range excludes the other five bands)."
        ),
    )
    parser.add_argument(
        "--band",
        choices=["fm_broadcast", "aviation", "acars", "aprs", "ais", "ism", "adsb"],
        default=None,
        help=(
            "Capture only this band instead of every band the selected "
            "antenna/device reaches. Uses the same lowercase keys as "
            "diagnose_threshold.py / diagnose_pluto_gain.py (e.g. 'adsb', "
            "not 'ADS_B'). For --device hackrf, the antenna prompt still "
            "shows all bands that antenna reaches, but only the chosen band "
            "is captured — pick an antenna that actually covers it."
        ),
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
    device: str = "hackrf",
    input_func=input,
    sleep_func=time.sleep,
) -> int:
    """Run the capture → fingerprint → embed → store loop.

    Args:
        store: Initialised SignalStore.
        embedder: Initialised SpectrumEmbedder.
        selected_targets: List of target dicts to capture.
        antenna_name: Human-readable antenna name for metadata.
        device: "hackrf" (split lna/vga gain) or "pluto" (combined gain_db).
            Determines which capture function and gain keys are used —
            never both, never a guess at the other device's shape.
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
        signal_threshold_db = target["signal_threshold_db"]
        captures = target["captures"]

        for cap_idx in range(captures):
            timestamp_ms = int(time.time() * 1000)
            record_id = f"{label}_{cap_idx}_{timestamp_ms}"

            print(f"\n[{idx + 1}/{total_targets}] Capturing: {label} ({device})")
            print(f"  Frequency: {freq_hz / 1e6:.3f} MHz")
            print(f"  Samples: {num_samples:,}")
            print(f"  Capture #{cap_idx + 1}/{captures}")
            if device == "pluto":
                print(f"  Gain: {target['gain_db']} dB (combined)")
            else:
                print(f"  Gain: LNA={target['lna_gain_db']} dB, VGA={target['vga_gain_db']} dB")
            print(f"  Threshold: {signal_threshold_db:.1f} dB")

            if cap_idx == 0 and label == "ADS_B":
                print("\n" + "=" * 70)
                print("ANTENNA LENGTH CHECK — ADS_B")
                print("=" * 70)
                print(
                    "\nRetract the telescopic whip to ~68mm (quarter-wave for "
                    "1090 MHz) if it is not already set that short.\nThis is a "
                    "much shorter extension than FM/Aviation/ACARS/APRS/AIS use "
                    "on the same antenna.\n"
                )
                try:
                    input_func("Press ENTER once the whip is set to ~68mm, or Ctrl+C to skip this band: ")
                except KeyboardInterrupt:
                    logger.info("User skipped %s band at antenna length check", label)
                    print(f"\n  Skipping {label} — no captures stored for this band.")
                    break

            if cap_idx == 0 and label in ("ADS_B", "ACARS", "AIS"):
                _print_band_warning(label)
                try:
                    input_func("Press ENTER to continue or Ctrl+C to skip this band: ")
                except KeyboardInterrupt:
                    logger.info("User skipped %s band", label)
                    print(f"\n  Skipping {label} — no captures stored for this band.")
                    break

            try:
                if device == "pluto":
                    samples = capture_iq_pluto(
                        freq_hz=freq_hz,
                        num_samples=num_samples,
                        sample_rate_hz=sample_rate_hz,
                        gain_db=target["gain_db"],
                    )
                else:
                    samples = capture_iq(
                        freq_hz=freq_hz,
                        num_samples=num_samples,
                        sample_rate_hz=sample_rate_hz,
                        lna_gain_db=target["lna_gain_db"],
                        vga_gain_db=target["vga_gain_db"],
                    )

                psd_result = compute_psd(
                    samples=samples,
                    sample_rate_hz=sample_rate_hz,
                    center_freq_hz=freq_hz,
                )

                fingerprint = fingerprint_spectrum(
                    psd_result,
                    signal_threshold_db=signal_threshold_db,
                    trace_key=target.get('trace_key', 'psd_db'),
                )

                vector = embedder.embed(fingerprint)
                metadata = build_metadata(
                    label, antenna_name, target, fingerprint, cap_idx, device=device
                )
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
    2a. --device hackrf (default): prompt for antenna, filter to that
        antenna's bands (7 CAPTURE_TARGETS bands across 3 antenna profiles;
        ADS_B is reachable on both the telescopic whip, retracted to ~68mm,
        and the spiral discone — the whip gives noticeably better ADS-B
        reception).
    2b. --device pluto: Pluto only reaches ISM_LoRa and ADS_B. Prompts for
        antenna choice between telescopic whip and spiral discone (not the
        full 3-option HackRF menu, since V-dipole covers neither Pluto band)
        because the two bands want different antennas — discone for
        ISM_LoRa, whip for ADS_B.
    3. Initialise production vectorstore, optionally wiping existing data.
    4. Capture IQ samples for each target, run through pipeline, store vectors.
       Per-band warnings for ADS-B, ACARS, and AIS fire before the first
       capture of each such band.
    5. Print summary and remind operator to recalibrate thresholds.

    All capture and processing is RX-only — no transmit functionality.
    """
    args = _parse_args()
    logger.info("Starting Mimir capture-to-vectorstore workflow (device=%s)", args.device)

    if args.device == "pluto":
        selected_targets = _build_pluto_targets()
        print()
        print(_colour("Device: ADALM-PLUTO", ANSI_GREEN))
        print(f"Bands to capture: {', '.join(t['label'] for t in selected_targets)}")
        print(
            "Skipping: FM_broadcast, Aviation_VHF, ACARS, APRS, AIS "
            "(outside Pluto's 325 MHz-3.8 GHz stock tuning range)"
        )
        # Pluto's two reachable bands want different antennas: ISM_LoRa
        # (915 MHz) suits the broadband spiral discone, but ADS_B (1090 MHz)
        # gets noticeably better reception on the telescopic whip retracted
        # to ~68mm (quarter-wave) than on the discone. Since ADS_B and
        # ISM_LoRa may need a physical antenna swap mid-run, ask which
        # antenna is connected right now rather than assuming — the metadata
        # record needs the true antenna, not a hardcoded guess.
        print()
        print("Which antenna is connected right now?")
        print("  1. Telescopic whip (best for ADS_B when retracted to ~68mm)")
        print("  3. Spiral discone  (best for ISM_LoRa)")
        pluto_antenna_choice = None
        while pluto_antenna_choice not in ("1", "3"):
            try:
                pluto_antenna_choice = input("Enter choice (1/3) or Ctrl+C to abort: ").strip()
            except KeyboardInterrupt:
                logger.info("User aborted Pluto capture at antenna selection")
                print()
                raise SystemExit(0)
            if pluto_antenna_choice not in ("1", "3"):
                print("Invalid choice. Please enter 1 or 3.")
        antenna_name = ANTENNA_PROFILES[pluto_antenna_choice]["name"]
        print(f"Antenna: {antenna_name}")
    else:
        antenna_choice, profile = _select_antenna()
        selected_bands = set(profile["bands"])
        selected_targets = [t for t in CAPTURE_TARGETS if t["label"] in selected_bands]
        antenna_name = profile["name"]

        skipped_labels = sorted(
            t["label"] for t in CAPTURE_TARGETS if t["label"] not in selected_bands
        )

        print()
        print(f"Device: HackRF One")
        print(f"Antenna: {antenna_name}")
        print(f"Bands to capture: {', '.join(t['label'] for t in selected_targets)}")
        if skipped_labels:
            print(f"Skipping: {', '.join(skipped_labels)} (outside this antenna's range)")

    # --band restricts to a single band, on top of whatever the antenna/
    # device already narrowed selected_targets to. Checked after both
    # branches so the same filter logic applies regardless of device.
    if args.band is not None:
        before_count = len(selected_targets)
        selected_targets = [
            t for t in selected_targets if LABEL_TO_BAND_KEY[t["label"]] == args.band
        ]
        if not selected_targets:
            print(_colour(
                f"\nERROR: --band {args.band} is not reachable with the "
                f"selected device/antenna combination (it narrowed "
                f"{before_count} band(s) down to none). Check the band is "
                f"actually covered by what you picked above.\n",
                ANSI_RED,
            ))
            raise SystemExit(1)
        print(f"--band filter applied: only {selected_targets[0]['label']} will be captured.")

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
        antenna_name=antenna_name,
        device=args.device,
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