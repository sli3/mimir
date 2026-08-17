"""
Per-band threshold diagnostic tool.

Captures live IQ samples from each AU-legal Mimir band and sweeps a range of
SIGNAL_THRESHOLD_DB values to find the one that produces an occupied bandwidth
closest to the expected bandwidth for that signal type.

Supports TWO devices via --device:
  hackrf (default) — all 6 BAND_SWEEP bands, split lna/vga gain.
  pluto             — ISM/ADS-B only (Pluto's stock 325 MHz-3.8 GHz tuning
                       range), combined gain_db from PLUTO_BAND_PROFILES.

For ADS-B specifically: the telescopic whip retracted to ~68mm (quarter-wave
for 1090 MHz) gives noticeably better reception than the spiral discone, on
either device (see tools/capture_to_vectorstore.py ANTENNA_PROFILES). This
tool prompts to check antenna length before the ADS-B sweep on both devices.

Legal: Receive-only. Radiocommunications Act 1992 (Cth).
       No transmission. Jurisdiction: AU/SA. Authority: ACMA.

Usage:
    PYTHONPATH=. python tools/diagnose_threshold.py
    PYTHONPATH=. python tools/diagnose_threshold.py --band adsb
    PYTHONPATH=. python tools/diagnose_threshold.py --device pluto
    PYTHONPATH=. python tools/diagnose_threshold.py --device pluto --band adsb
"""

import argparse
import sys

import numpy as np

from core.pipeline.capture import capture_iq, capture_iq_pluto
from core.pipeline.features import fingerprint_spectrum
from core.pipeline.fft import compute_psd
from dashboard.shared_state import BAND_PROFILES

THRESHOLD_CANDIDATES = [3, 5, 8, 10, 12, 15, 18, 21, 24, 27]

BAND_SWEEP = [
    {
        "name": "FM Broadcast",
        "band_key": "fm_broadcast",
        "freq_hz": 98_900_000,
        "lna_gain_db": BAND_PROFILES["fm_broadcast"]["lna_gain_db"],
        "vga_gain_db": BAND_PROFILES["fm_broadcast"]["vga_gain_db"],
        "target_bw_hz": 200_000,
        "sample_rate_hz": 2_000_000,
        "num_samples": 256_000,
    },
    {
        "name": "Aviation VHF",
        "band_key": "aviation",
        "freq_hz": 127_000_000,
        "lna_gain_db": BAND_PROFILES["aviation"]["lna_gain_db"],
        "vga_gain_db": BAND_PROFILES["aviation"]["vga_gain_db"],
        "target_bw_hz": 8_300,
        "sample_rate_hz": 2_000_000,
        "num_samples": 256_000,
    },
    {
        "name": "ACARS",
        "band_key": "acars",
        "freq_hz": 129_125_000,
        "lna_gain_db": BAND_PROFILES["acars"]["lna_gain_db"],
        "vga_gain_db": BAND_PROFILES["acars"]["vga_gain_db"],
        "target_bw_hz": 12_500,
        "sample_rate_hz": 2_000_000,
        "num_samples": 256_000,
    },
    {
        "name": "APRS",
        "band_key": "aprs",
        "freq_hz": 145_175_000,
        "lna_gain_db": BAND_PROFILES["aprs"]["lna_gain_db"],
        "vga_gain_db": BAND_PROFILES["aprs"]["vga_gain_db"],
        "target_bw_hz": 12_500,
        "sample_rate_hz": 2_000_000,
        "num_samples": 256_000,
    },
    {
        "name": "ISM / LoRa",
        "band_key": "ism",
        "freq_hz": 915_000_000,
        "lna_gain_db": BAND_PROFILES["ism"]["lna_gain_db"],
        "vga_gain_db": BAND_PROFILES["ism"]["vga_gain_db"],
        "target_bw_hz": 500_000,
        "sample_rate_hz": 2_000_000,
        "num_samples": 256_000,
    },
    {
        "name": "ADS-B",
        "band_key": "adsb",
        "freq_hz": 1_090_000_000,
        "lna_gain_db": BAND_PROFILES["adsb"]["lna_gain_db"],
        "vga_gain_db": BAND_PROFILES["adsb"]["vga_gain_db"],
        "target_bw_hz": 1_000_000,
        "sample_rate_hz": 2_000_000,
        "num_samples": 256_000,
        "trace_key": "psd_max_hold_db",
    },
]

# NOTE: BAND_SWEEP has no AIS entry (pre-existing). Future enhancement:
# add AIS to BAND_SWEEP if threshold-sweeping AIS is desired.

# Each BAND_SWEEP entry carries an explicit "band_key" matching the real
# BAND_PROFILES / PLUTO_BAND_PROFILES dict keys exactly. This replaces a
# prior string-derivation approach (.lower().replace(...) on "name") that
# silently diverged for "ISM / LoRa" -> "ism_lora" instead of "ism", causing
# --band ism --device pluto to always fail even though PLUTO_BAND_PROFILES
# ["ism"] was correctly configured and supported. Confirmed live 2026-08-17.
# A single source of truth (this field) avoids the whole class of bug for
# any future band name containing a space, slash, or hyphen.
BAND_KEYS = {b["band_key"]: b for b in BAND_SWEEP}

# Pluto's stock tuning range (325 MHz - 3.8 GHz) only covers these two bands
# out of BAND_SWEEP's six. Same scope as capture_to_vectorstore.py
# PLUTO_SUPPORTED_LABELS and diagnose_pluto_gain.py's BAND_SWEEP.
PLUTO_SUPPORTED_KEYS = ("ism", "adsb")


def _build_pluto_band_sweep() -> list[dict]:
    """Build a Pluto-gain version of BAND_SWEEP, restricted to ism/adsb.

    Reuses freq_hz/target_bw_hz/sample_rate_hz/num_samples/trace_key from
    the existing BAND_SWEEP entries — only the gain model changes (combined
    gain_db instead of split lna/vga). Support and gain values are checked
    via band_supported_by_device(), the same helper
    tools/capture_to_vectorstore.py uses, rather than re-deriving support
    logic here.

    Raises:
        SystemExit: if PLUTO_BAND_PROFILES is missing, or a supported band
            is missing gain_db. This tool never guesses a gain value.
    """
    try:
        from dashboard.shared_state import (
            PLUTO_BAND_PROFILES,
            band_supported_by_device,
        )
    except ImportError:
        print(
            "\nERROR: dashboard.shared_state.PLUTO_BAND_PROFILES does not exist yet.\n"
            "Pluto threshold sweep needs calibrated gain values first.\n"
            "Run tools/diagnose_pluto_gain.py, pick gain_db for ISM and ADS-B,\n"
            "and add a PLUTO_BAND_PROFILES dict to dashboard/shared_state.py.\n",
            file=sys.stderr,
        )
        raise SystemExit(1)

    pluto_sweep = []
    for base in BAND_SWEEP:
        key = base["band_key"]
        if key not in PLUTO_SUPPORTED_KEYS:
            continue

        if not band_supported_by_device(key, "plutosdr"):
            print(
                f"\nERROR: band_supported_by_device says Pluto does not "
                f"support '{key}' ({base['name']}).\n"
                f"Reason: {PLUTO_BAND_PROFILES[key].get('reason', 'unknown')}\n",
                file=sys.stderr,
            )
            raise SystemExit(1)

        profile = PLUTO_BAND_PROFILES[key]
        if "gain_db" not in profile:
            print(
                f"\nERROR: PLUTO_BAND_PROFILES['{key}'] is marked supported "
                f"but is missing 'gain_db'.\n"
                f"Run tools/diagnose_pluto_gain.py --band {key} and add the "
                f"result.\n",
                file=sys.stderr,
            )
            raise SystemExit(1)

        target = dict(base)
        target["gain_db"] = profile["gain_db"]
        target.pop("lna_gain_db", None)
        target.pop("vga_gain_db", None)
        pluto_sweep.append(target)

    return pluto_sweep


def sweep_band(band: dict, device: str = "hackrf") -> dict:
    """Capture and sweep thresholds for a single band.

    Args:
        band: Band dict from BAND_SWEEP (hackrf gain keys) or
            _build_pluto_band_sweep() (gain_db key).
        device: "hackrf" (split lna/vga gain) or "pluto" (combined gain_db).
            Determines which capture function and gain keys are used.

    Returns:
        Dict with keys: name, freq_hz, recommended_thr, recommended_bw, rows
        where rows is a list of (thr, bw, bins) tuples.
    """
    print(f"═══ {band['name']} ({band['freq_hz'] / 1e6:.3f} MHz) — {device} ═══")

    # ADS-B specifically benefits from the telescopic whip retracted to
    # ~68mm (quarter-wave for 1090 MHz) over the spiral discone, on either
    # device — same finding as tools/capture_to_vectorstore.py. Remind the
    # operator before this band's capture since the extension differs
    # sharply from other bands on the same physical whip.
    if band["name"] == "ADS-B":
        print(
            "\nIf using the telescopic whip, retract to ~68mm (quarter-wave "
            "for 1090 MHz) for best reception.\nIf using the spiral discone, "
            "no adjustment needed.\n"
        )
        try:
            input("Press ENTER once antenna is ready, or Ctrl+C to skip this band: ")
        except KeyboardInterrupt:
            print(f"\n  Skipping {band['name']} — no sweep run for this band.")
            return {
                "name": band["name"],
                "freq_hz": band["freq_hz"],
                "recommended_thr": None,
                "recommended_bw": None,
                "rows": [],
            }

    if device == "pluto":
        samples = capture_iq_pluto(
            freq_hz=band["freq_hz"],
            num_samples=band["num_samples"],
            sample_rate_hz=band["sample_rate_hz"],
            gain_db=band["gain_db"],
        )
    else:
        samples = capture_iq(
            freq_hz=band["freq_hz"],
            num_samples=band["num_samples"],
            sample_rate_hz=band["sample_rate_hz"],
            lna_gain_db=band["lna_gain_db"],
            vga_gain_db=band["vga_gain_db"],
        )
    print(f"Captured {len(samples)} IQ samples")

    psd_result = compute_psd(
        samples=samples,
        sample_rate_hz=band["sample_rate_hz"],
        center_freq_hz=band["freq_hz"],
    )

    if len(psd_result["psd_db"]) == 0:
        print("ERROR: Empty PSD — skipping band.", file=sys.stderr)
        return {
            "name": band["name"],
            "freq_hz": band["freq_hz"],
            "recommended_thr": None,
            "recommended_bw": None,
            "rows": [],
        }

    rows = []
    for thr in THRESHOLD_CANDIDATES:
        fp = fingerprint_spectrum(
            psd_result,
            signal_threshold_db=float(thr),
            trace_key=band.get('trace_key', 'psd_db'),
        )
        bw = fp["bandwidth_hz"]
        bins = fp["occupied_bins"]
        rows.append((thr, bw, bins))
        print(
            f"  threshold={thr:>2} dB  →  "
            f"bandwidth={bw:>8.0f} Hz  bins={bins:>5}  "
            f"[target: {band['target_bw_hz']} Hz]"
        )

    # Guard against a no-signal capture. If NO threshold produced any occupied
    # bandwidth, there was nothing in the band and the "closest to target" search
    # below would otherwise emit a confident but meaningless recommendation
    # (typically the lowest threshold). This is the total-dead case only; a few
    # noise spikes at low thresholds can still slip past, so for burst bands the
    # real check remains confirming live traffic overhead before trusting output.
    if all(bw == 0 for _, bw, _ in rows):
        print(
            f"\n⚠ NO OCCUPIED BANDWIDTH at any threshold for {band['name']} — "
            f"no signal was present in this capture."
        )
        print(
            "  Recommendation suppressed. For burst bands (ADS-B, ACARS, AIS) "
            "confirm live traffic (flightradar24 / marinetraffic) and re-run."
        )
        print()
        return {
            "name": band["name"],
            "freq_hz": band["freq_hz"],
            "recommended_thr": None,
            "recommended_bw": None,
            "rows": rows,
        }

    diffs = [(abs(bw - band["target_bw_hz"]), thr, bw) for thr, bw, _ in rows]
    best = min(diffs, key=lambda x: x[0])
    print(f"\nRECOMMENDATION: {band['name']} → {best[1]} dB  (bandwidth={best[2]:.0f} Hz)")
    print()

    return {
        "name": band["name"],
        "freq_hz": band["freq_hz"],
        "recommended_thr": best[1],
        "recommended_bw": best[2],
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sweep per-band signal thresholds for Mimir.",
    )
    parser.add_argument(
        "--band",
        help="Sweep a single band instead of all bands the device reaches. Valid values depend on --device (see error message if invalid).",
    )
    parser.add_argument(
        "--device",
        choices=["hackrf", "pluto"],
        default="hackrf",
        help=(
            "SDR device to sweep with (default: hackrf). Pluto only "
            "supports ism and adsb (its stock 325 MHz-3.8 GHz tuning range "
            "excludes the other four bands)."
        ),
    )
    args = parser.parse_args()

    if args.device == "pluto":
        sweep_source = _build_pluto_band_sweep()
        band_keys = {b["band_key"]: b for b in sweep_source}
    else:
        sweep_source = BAND_SWEEP
        band_keys = BAND_KEYS

    if args.band is not None and args.band not in band_keys:
        print(
            f"ERROR: --band {args.band!r} is not valid for --device "
            f"{args.device}. Valid choices: {', '.join(sorted(band_keys))}",
            file=sys.stderr,
        )
        raise SystemExit(1)

    bands = [band_keys[args.band]] if args.band else sweep_source
    results = []

    for band in bands:
        result = sweep_band(band, device=args.device)
        results.append(result)

    # Summary table
    print("╔══════════════════════════╦═══════════════════╦══════════════════╗")
    print("║ Band                     ║ Recommended (dB)  ║ BW at rec (Hz)   ║")
    print("╠══════════════════════════╬═══════════════════╬══════════════════╣")
    for r in results:
        thr = r["recommended_thr"] if r["recommended_thr"] is not None else "N/A"
        bw = f"{r['recommended_bw']:.0f}" if r["recommended_bw"] is not None else "N/A"
        print(f"║ {r['name']:<24} ║ {str(thr):>17} ║ {bw:>16} ║")
    print("╚══════════════════════════╩═══════════════════╩══════════════════╝")
    print()
    if args.device == "pluto":
        print(
            "Update signal_threshold_db in PLUTO_BAND_PROFILES "
            "(dashboard/shared_state.py) with these recommended values."
        )
    else:
        print(
            "Update signal_threshold_db in BAND_PROFILES (dashboard/shared_state.py) "
            "with these recommended values."
        )


if __name__ == "__main__":
    main()