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
``./mimir tool calibrate_thresholds`` to update distance thresholds.

Run with ``./mimir tool capture_to_vectorstore``. Band cards and summaries
stay plain when piped; ``--verbose`` adds per-capture details and Mimir logs.

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
from llm.classifier import SignalClassifier
from tools._console import (
    FAILURE, OK, WARNING, Spinner, SpinnerLogHandler, box, dim, fail,
    next_step, ok, table, warn,
)

import argparse
import logging
import sys
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from textwrap import wrap

logger = logging.getLogger(__name__)

# Pluto's stock tuning range (325 MHz - 3.8 GHz) only covers these two Mimir
# bands out of the seven in CAPTURE_TARGETS. Matches diagnose_pluto_gain.py's
# BAND_SWEEP scope exactly — same hardware limitation, same two bands.
PLUTO_SUPPORTED_LABELS = ("ISM_LoRa", "ADS_B")

# Antenna-to-band mappings. Labels must match CAPTURE_TARGETS exactly.
#
# ADS_B on "Telescopic whip": confirmed 2026-08 — retracted to ~68mm (quarter-
# wave monopole for 1090 MHz), the same physical whip used at longer
# extensions for FM/Aviation/ACARS/APRS/AIS gives noticeably better ADS-B
# reception than the spiral discone. This is ONE whip at DIFFERENT
# extensions per band, not a separate antenna. The ADS_B card instructs
# the operator to retract it before starting that band's captures.
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

# Recommendations follow the ADS_B whip notes above and the existing Pluto
# prompt's description of the discone as best for ISM_LoRa. The unused
# length_reminder text covers the same whip adjustment advice.
ANTENNA_RECOMMENDATIONS: dict[str, tuple[str, str]] = {
    "ADS_B": (
        "Telescopic whip",
        "Telescopic whip (retracted to ~68 mm) works better for this band",
    ),
    "ISM_LoRa": (
        "Spiral discone", "Spiral discone works better for this band",
    ),
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
        SystemExit: if PLUTO_BAND_PROFILES is missing, a required band is
            unsupported, or its gain_db/signal_threshold_db is missing. Show
            a failure box rather than guessing a gain value.
    """
    try:
        from dashboard.shared_state import (
            PLUTO_BAND_PROFILES,
            band_supported_by_device,
        )
    except ImportError:
        box("Setup error", [
            "\nERROR: dashboard.shared_state.PLUTO_BAND_PROFILES does not exist yet.\n"
            "Pluto capture needs calibrated gain values before it can run.\n"
            "Run tools/diagnose_pluto_gain.py, pick gain_db for ISM and ADS-B\n"
            "from the sweep output, and add a PLUTO_BAND_PROFILES dict to\n"
            "dashboard/shared_state.py (e.g. {'ism': {'gain_db': ..., "
            "'signal_threshold_db': ...}, 'adsb': {...}}).\n",
        ], style=fail)
        raise SystemExit(1)

    pluto_targets = []
    for base in CAPTURE_TARGETS:
        label = base["label"]
        if label not in PLUTO_SUPPORTED_LABELS:
            continue
        key = LABEL_TO_BAND_KEY[label]

        if not band_supported_by_device(key, "plutosdr"):
            box("Setup error", [
                f"\nERROR: band_supported_by_device says Pluto does not "
                f"support '{key}' ({label}).\n"
                f"Reason: {PLUTO_BAND_PROFILES[key].get('reason', 'unknown')}\n",
            ], style=fail)
            raise SystemExit(1)

        profile = PLUTO_BAND_PROFILES[key]
        if "gain_db" not in profile or "signal_threshold_db" not in profile:
            box("Setup error", [
                f"\nERROR: PLUTO_BAND_PROFILES['{key}'] is marked supported "
                f"but is missing 'gain_db' or 'signal_threshold_db'.\n"
                f"Run tools/diagnose_pluto_gain.py --band {key} and add the "
                f"result.\n",
            ], style=fail)
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


def _configure_console_logging(verbose: bool) -> None:
    """Replace root handlers with silent or spinner-aware console logging.

    Default mode hides propagated records, including WARNING messages.
    Uncaught exceptions still print their traceback. Verbose mode enables
    INFO for Mimir only, leaving the root at WARNING and filtering explicitly
    enabled third-party INFO. Repeated calls replace rather than add handlers.
    """
    root = logging.getLogger()
    for handler in root.handlers[:]:
        root.removeHandler(handler)
    root.setLevel(logging.WARNING)
    mimir_names = (__name__, "core", "embeddings", "llm", "tools")
    for name in mimir_names:
        logging.getLogger(name).setLevel(
            logging.INFO if verbose else logging.NOTSET
        )
    if not verbose:
        root.addHandler(logging.NullHandler())
        return

    def include_record(record: logging.LogRecord) -> bool:
        """Hide third-party INFO even when a library explicitly enables it."""
        return record.levelno >= logging.WARNING or any(
            record.name == name or record.name.startswith(name + ".")
            for name in mimir_names
        )

    handler = SpinnerLogHandler(level=logging.INFO)
    handler.setFormatter(logging.Formatter(
        "%(levelname)s %(name)s: %(message)s"
    ))
    handler.addFilter(include_record)
    root.addHandler(handler)


def _quiet_soapy_info_logs() -> None:
    """Quiet driver INFO without opening a device; tolerate missing bindings.

    SoapySDR has RX/TX capability. Only its logging setter is used here;
    capture paths remain receive-only. Support both binding setter names.
    """
    try:
        import SoapySDR
    except ImportError:
        logger.debug("SoapySDR unavailable; leaving driver logging unchanged")
        return
    setter = (
        getattr(SoapySDR, "SoapySDR_setLogLevel", None)
        or getattr(SoapySDR, "setLogLevel", None)
    )
    level = getattr(SoapySDR, "SOAPY_SDR_WARNING", None)
    if setter is None or level is None:
        logger.debug("SoapySDR log controls unavailable; leaving logging unchanged")
        return
    setter(level)


def _band_signal_lines(label: str) -> list[str]:
    """Return traffic requirements and live-traffic links for a band card."""
    warnings = {
        "ADS_B": [
            "Aircraft overhead, otherwise only noise",
            "Live traffic: flightradar24.com",
        ],
        "ACARS": [
            "Active aircraft traffic, otherwise only noise",
            "Live traffic: flightradar24.com",
        ],
        "AIS": [
            "Vessels within range, otherwise only noise",
            "Live traffic: marinetraffic.com",
        ],
    }
    return warnings.get(label, [])


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
    """Parse capture overrides, device choice and optional verbose output."""
    parser = argparse.ArgumentParser(
        description=(
            "Capture live IQ samples across AU-legal RX bands and store "
            "spectrum embeddings in data/vectorstore."
        ),
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show per-capture details and Mimir log messages.",
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
    parser.add_argument(
        "--freq-mhz",
        type=float,
        default=None,
        help=(
            "Override the capture frequency in MHz for the band selected "
            "with --band (e.g. --band fm_broadcast --freq-mhz 101.5 to "
            "capture a different FM station than the hardcoded 98.9 MHz "
            "default). Requires --band — overriding one frequency across "
            "multiple bands at once would be ambiguous, so this errors if "
            "--band is not also given."
        ),
    )
    parser.add_argument(
        "--captures",
        type=int,
        default=None,
        help=(
            "Override the number of captures for the band selected with "
            "--band (default varies per band, e.g. 5 for FM_broadcast). "
            "Requires --band, same reasoning as --freq-mhz. Must be a "
            "positive integer."
        ),
    )
    return parser.parse_args()


def _select_antenna() -> tuple[str, dict]:
    """Choose the HackRF antenna used for every covered band in this run.

    Re-ask invalid choices; Ctrl+C cancels before capturing.

    Returns:
        Tuple of (choice_key, profile_dict).
    """
    print(
        "  Which antenna is on the HackRF? "
        "Every band it covers is captured with it."
    )
    for line in table([
        ("1", "Telescopic whip", "75 MHz – 700 MHz; ADS_B at ~68 mm"),
        ("2", "V-dipole 533mm", "130 MHz – 145 MHz"),
        ("3", "Spiral discone", "800 MHz – 8500 MHz"),
    ]):
        print(f"    {line}")

    antenna_choice = None
    while antenna_choice not in ANTENNA_PROFILES:
        try:
            antenna_choice = input(
                "  Choose 1, 2 or 3 (Ctrl+C to cancel): "
            ).strip()
        except KeyboardInterrupt:
            logger.info("User aborted capture at antenna selection")
            print()
            raise SystemExit(0)
        if antenna_choice not in ANTENNA_PROFILES:
            print("Please choose 1, 2 or 3.")

    return antenna_choice, ANTENNA_PROFILES[antenna_choice]


def _band_antenna_rows(label: str, antenna_name: str) -> list[tuple[str, str]]:
    """Keep the connected antenna and optional advice on aligned card rows.

    Wrap advice before colouring it. A 72-column box has 66 body columns;
    the card's longest key (Captures) and table gap leave 55 for values.
    These hints do not alter the selected antenna or prevent capture.
    """
    rows = [("Antenna", antenna_name)]
    preferred, hint = ANTENNA_RECOMMENDATIONS.get(label, ("", ""))
    if label == "ADS_B" and antenna_name == preferred:
        rows.append(("", "Retract it to ~68 mm before you start"))
    elif preferred and antenna_name != preferred:
        rows.extend(("", warn(line)) for line in wrap(f"{WARNING} {hint}", 55))
    return rows


def run_capture_loop(
    store: SignalStore,
    embedder: SpectrumEmbedder,
    selected_targets: list[dict],
    antenna_name: str,
    device: str = "hackrf",
    input_func: Callable[[str], str] = input,
    sleep_func: Callable[[float], None] = time.sleep,
    *,
    verbose: bool = False,
    results: list[dict] | None = None,
) -> int:
    """Prompt once per band, capture with progress and report stored records.

    One offline classifier applies the unchanged noise gate before embedding.
    Noise skips retain the normal five-second wait; RuntimeError stops only
    the current band without a wait. Progress clears on every exit path.
    Cards name the run's connected antenna and give aligned adjustment or
    preference hints without changing what Enter captures or Ctrl+C skips.

    Args:
        store: Initialised SignalStore, updated once per accepted capture.
        embedder: Initialised SpectrumEmbedder.
        selected_targets: Target dicts in capture order.
        antenna_name: Antenna name for cards and stored metadata.
        device: "hackrf" (split lna/vga) or "pluto" (combined gain_db).
        input_func: Input callable for the single prompt before each band.
        sleep_func: Sleep callable for the existing five-second wait rule.
        verbose: Show per-capture details and noise measurements on a TTY too.
        results: Optional list to append per-band stored/noise/failure/skip
            counts and flags for the caller's final summary.

    Returns:
        Number of records successfully stored this run.
    """
    captured_count = 0
    classifier = SignalClassifier()
    total_targets = len(selected_targets)

    for idx, target in enumerate(selected_targets):
        label = target["label"]
        freq_hz = target["freq_hz"]
        num_samples = target["num_samples"]
        sample_rate_hz = target["sample_rate_hz"]
        signal_threshold_db = target["signal_threshold_db"]
        captures = target["captures"]
        result = {
            "label": label, "stored": 0, "noise": 0,
            "failed": False, "skipped": False,
        }
        if results is not None:
            results.append(result)
        snrs: list[float] = []
        rows = _band_antenna_rows(label, antenna_name)
        for index, line in enumerate(_band_signal_lines(label)):
            rows.append(("Signal" if index == 0 else "", line))
        gain = (
            f"gain {target['gain_db']} dB" if device == "pluto" else
            f"LNA {target['lna_gain_db']} dB, VGA {target['vga_gain_db']} dB"
        )
        rows.append((
            "Captures",
            f"{captures} · {gain} · threshold {signal_threshold_db:.1f} dB",
        ))
        box(
            f"[{idx + 1}/{total_targets}] {label} · {freq_hz / 1e6:.3f} MHz",
            table(rows),
        )
        try:
            input_func("  Enter to start · Ctrl+C to skip this band: ")
        except KeyboardInterrupt:
            logger.info("User skipped %s band", label)
            result["skipped"] = True
            print(warn(f"  {WARNING} {label} skipped"))
            continue

        # Prompts finish before progress starts; the context clears all exits.
        with Spinner(f"capturing 1/{captures}", total=captures) as progress:
            for cap_idx in range(captures):
                progress.update(
                    f"capturing {cap_idx + 1}/{captures}", cap_idx, captures,
                )
                timestamp_ms = int(time.time() * 1000)
                record_id = f"{label}_{cap_idx}_{timestamp_ms}"
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

                    if classifier.is_noise_shaped(fingerprint):
                        logger.info(
                            "Skipped noise-shaped capture for %s: "
                            "bins=%s, flatness=%s",
                            label,
                            fingerprint["occupied_bins"],
                            fingerprint["spectral_flatness"],
                        )
                        result["noise"] += 1
                        progress.write_above(warn(
                            f"  {WARNING} capture {cap_idx + 1}/{captures} "
                            "skipped: looks like noise"
                        ))
                        if verbose:
                            progress.write_above(dim(
                                "    occupied_bins="
                                f"{fingerprint['occupied_bins']}, "
                                "spectral_flatness="
                                f"{fingerprint['spectral_flatness']:.6f}"
                            ))
                        if idx != total_targets - 1 or cap_idx != captures - 1:
                            logger.info(
                                "Waiting 5 seconds before next capture"
                            )
                            progress.update(
                                "waiting 5s", cap_idx + 1, captures,
                            )
                            sleep_func(5)
                        continue

                    vector = embedder.embed(fingerprint)
                    metadata = build_metadata(
                        label, antenna_name, target, fingerprint, cap_idx,
                        device=device,
                    )
                    record = {
                        "id": record_id,
                        "embedding": vector,
                        "metadata": metadata,
                    }
                    store.add(record)
                    captured_count += 1

                    result["stored"] += 1
                    snrs.append(fingerprint["snr_db"])
                    snr_margin_db = fingerprint["snr_margin_db"]
                    margin_style = (
                        ok if snr_margin_db > 0 else
                        warn if snr_margin_db == 0 else fail
                    )
                    if verbose or not progress.active:
                        progress.write_above(
                            ok(
                                f"  {OK} capture {cap_idx + 1}/{captures} "
                                "stored"
                            )
                            + f" · peak {fingerprint['peak_power_db']:.2f} dB"
                            + f" · SNR {fingerprint['snr_db']:.2f} dB"
                            + " · margin "
                            + margin_style(f"{snr_margin_db:.2f} dB")
                        )

                except RuntimeError as err:
                    result["failed"] = True
                    progress.pause()
                    logger.error(
                        "Capture failed for %s (capture %d): %s",
                        label, cap_idx, err,
                    )
                    progress.write_above(fail(
                        f"  {FAILURE} capture {cap_idx + 1}/{captures} failed"
                    ))
                    progress.write_above(dim(f"    {err}"))
                    # Retain stored records; stop at the band's first error.
                    break

                is_last = (
                    idx == total_targets - 1
                    and cap_idx == captures - 1
                )
                if not is_last:
                    logger.info("Waiting 5 seconds before next capture")
                    progress.update("waiting 5s", cap_idx + 1, captures)
                    sleep_func(5)

        parts = [f"{result['stored']}/{captures} stored"]
        if result["noise"]:
            parts.append(f"{result['noise']} skipped as noise")
        if snrs:
            parts.append(f"SNR {min(snrs):.1f} to {max(snrs):.1f} dB")
        if result["failed"]:
            parts.append("band failed")
        summary_style = ok if result["stored"] else warn
        symbol = OK if result["stored"] else WARNING
        print(summary_style(f"  {symbol} " + " · ".join(parts)))

    return captured_count


def main() -> None:
    """Validate options, show final bands and run receive-only captures.

    Configure quiet or verbose console logs, select the antenna, apply target
    overrides and initialise the store (optionally wiping it). The antenna
    choice applies to every selected band; Pluto's two displayed choices map
    to the real whip/discone profiles. Show a header with aligned skip reasons
    and the post-wipe count, then cards naming the antenna with optional
    hints and one readiness prompt per band. Report each
    band's outcome and the store count change. Exit 1 only when capture
    failures occurred and nothing was stored; noise-only and skipped runs
    complete normally. Remind successful runs to recalibrate thresholds.
    """
    args = _parse_args()
    _configure_console_logging(args.verbose)
    _quiet_soapy_info_logs()
    logger.info("Starting Mimir capture-to-vectorstore workflow (device=%s)", args.device)
    option_lines: list[str] = []

    if args.device == "pluto":
        selected_targets = _build_pluto_targets()
        skipped_labels = [
            t["label"] for t in CAPTURE_TARGETS
            if t["label"] not in PLUTO_SUPPORTED_LABELS
        ]
        skip_reason = "outside Pluto's range"
        # Pluto's two reachable bands want different antennas: ISM_LoRa
        # (915 MHz) suits the broadband spiral discone, but ADS_B (1090 MHz)
        # gets noticeably better reception on the telescopic whip retracted
        # to ~68mm (quarter-wave) than on the discone. Ask which antenna
        # is on the Pluto for both bands; cards advise but never change
        # this choice or the real antenna name stored in metadata.
        print(
            "  Which antenna is on the Pluto? "
            "Both bands are captured with it."
        )
        for line in table([
            ("1", "Telescopic whip", "best for ADS_B"),
            ("2", "Spiral discone", "best for ISM_LoRa"),
        ]):
            print(f"    {line}")
        pluto_antenna_profiles = {"1": "1", "2": "3"}
        pluto_antenna_choice = None
        while pluto_antenna_choice not in pluto_antenna_profiles:
            try:
                pluto_antenna_choice = input(
                    "  Choose 1 or 2 (Ctrl+C to cancel): "
                ).strip()
            except KeyboardInterrupt:
                logger.info("User aborted Pluto capture at antenna selection")
                print()
                raise SystemExit(0)
            if pluto_antenna_choice not in pluto_antenna_profiles:
                print("Please choose 1 or 2.")
        profile_key = pluto_antenna_profiles[pluto_antenna_choice]
        antenna_name = ANTENNA_PROFILES[profile_key]["name"]
    else:
        antenna_choice, profile = _select_antenna()
        selected_bands = set(profile["bands"])
        selected_targets = [t for t in CAPTURE_TARGETS if t["label"] in selected_bands]
        antenna_name = profile["name"]

        skipped_labels = sorted(
            t["label"] for t in CAPTURE_TARGETS if t["label"] not in selected_bands
        )

        skip_reason = "outside this antenna's range"

    # --band restricts to a single band, on top of whatever the antenna/
    # device already narrowed selected_targets to. Checked after both
    # branches so the same filter logic applies regardless of device.
    if args.band is not None:
        before_count = len(selected_targets)
        selected_targets = [
            t for t in selected_targets if LABEL_TO_BAND_KEY[t["label"]] == args.band
        ]
        if not selected_targets:
            box("Setup error", [
                f"\nERROR: --band {args.band} is not reachable with the "
                f"selected device/antenna combination (it narrowed "
                f"{before_count} band(s) down to none). Check the band is "
                f"actually covered by what you picked above.\n",
            ], style=fail)
            raise SystemExit(1)
        option_lines.append(
            f"--band filter applied: only {selected_targets[0]['label']} "
            "will be captured."
        )

    # --freq-mhz and --captures both require --band, since overriding either
    # one across multiple bands at once would be ambiguous (which band's
    # frequency? applied to how many of the selected bands?).
    if (args.freq_mhz is not None or args.captures is not None) and args.band is None:
        box("Setup error", [
            "\nERROR: --freq-mhz and --captures require --band (they "
            "override a single target's values — pick which band with "
            "--band first).\n",
        ], style=fail)
        raise SystemExit(1)

    if args.freq_mhz is not None:
        original_freq_hz = selected_targets[0]["freq_hz"]
        override_freq_hz = int(args.freq_mhz * 1e6)
        # Copy the target dict rather than mutating CAPTURE_TARGETS/the
        # Pluto-built list in place — those are shared module-level state
        # (CAPTURE_TARGETS) or freshly built per-run, but mutating either
        # unconditionally risks surprising a second call in the same
        # process (e.g. future test code that imports this module).
        selected_targets[0] = dict(selected_targets[0])
        selected_targets[0]["freq_hz"] = override_freq_hz
        option_lines.append(
            f"--freq-mhz override: {selected_targets[0]['label']} will "
            f"capture at {args.freq_mhz:.3f} MHz instead of the default "
            f"{original_freq_hz / 1e6:.3f} MHz."
        )
        option_lines.append(
            "  NOTE: signal_threshold_db and gain are still the values "
            "calibrated for the default frequency — a different station "
            "may need different threshold/gain to detect cleanly. Re-run "
            "diagnose_threshold.py at the new frequency if results look off."
        )

    if args.captures is not None:
        if args.captures < 1:
            box("Setup error", [
                f"\nERROR: --captures must be a positive integer, got "
                f"{args.captures}.\n",
            ], style=fail)
            raise SystemExit(1)
        original_captures = selected_targets[0]["captures"]
        selected_targets[0] = dict(selected_targets[0])
        selected_targets[0]["captures"] = args.captures
        option_lines.append(
            f"--captures override: {selected_targets[0]['label']} will run "
            f"{args.captures} capture(s) instead of the default "
            f"{original_captures}."
        )

    store_path = Path("data/vectorstore")
    store_path.mkdir(parents=True, exist_ok=True)

    store = SignalStore(path=str(store_path))

    # --wipe is destructive: it deletes the entire ChromaDB collection before
    # capture starts. No interactive confirmation is shown (accepted per security
    # review). If scan.py is running concurrently, SQLite lock errors may occur
    # because both processes write to the same data/vectorstore/ directory.
    if args.wipe:
        box("Wipe vector store", [
            "WARNING: --wipe will delete every stored record "
            "in data/vectorstore.",
            "All previous embeddings will be lost.",
        ], style=warn)
        store.delete_collection()
        store = SignalStore(path=str(store_path))
        print("Vector store wiped and reinitialised.")

    before_count = store.count()
    rows = [("Bands", ", ".join(t["label"] for t in selected_targets))]
    if skipped_labels:
        rows.extend([
            ("Skipped", ", ".join(skipped_labels)),
            ("", f"({skip_reason})"),
        ])
    rows.append(("Store", f"{before_count} records in data/vectorstore"))
    box(
        f"Mimir · capture to vectorstore · {args.device}",
        table(rows) + [dim(line) for line in option_lines],
    )
    embedder = SpectrumEmbedder()
    results: list[dict] = []

    captured_count = run_capture_loop(
        store=store,
        embedder=embedder,
        selected_targets=selected_targets,
        antenna_name=antenna_name,
        device=args.device,
        input_func=input,
        verbose=args.verbose,
        results=results,
    )

    any_failed = any(result["failed"] for result in results)
    if any_failed and not captured_count:
        failure_lines = ["No band stored any capture."]
        if args.wipe:
            failure_lines.append(
                "The store was wiped at the start of this run, so its earlier "
                "records are gone."
            )
        else:
            failure_lines.append("data/vectorstore was left unchanged.")
        box("No new captures", failure_lines, style=fail)
        next_step(
            "check the Pluto is plugged in (iio_info should list it), "
            "then run again"
            if args.device == "pluto" else
            "check the HackRF is plugged in (hackrf_info should list it), "
            "then run again"
        )
        raise SystemExit(1)

    summary_rows = []
    for result in results:
        parts = []
        if result["stored"] or not (result["failed"] or result["skipped"]):
            parts.append(f"{result['stored']} stored")
        if result["noise"]:
            parts.append(f"{result['noise']} noise")
        if result["failed"]:
            parts.append("failed")
        if result["skipped"]:
            parts.append("skipped")
        summary_rows.append((result["label"], " · ".join(parts)))
    summary_rows.append(("Store", f"{before_count} → {store.count()} records"))
    box(
        "Capture complete", table(summary_rows),
        style=ok if captured_count else warn,
    )
    next_step(f"./mimir tool calibrate_thresholds --device {args.device}")
    logger.info("Capture-to-vectorstore complete. %d records stored.", captured_count)


if __name__ == "__main__":
    main()
