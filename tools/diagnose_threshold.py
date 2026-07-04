"""
Per-band threshold diagnostic tool.

Captures live IQ samples from each AU-legal Mimir band and sweeps a range of
SIGNAL_THRESHOLD_DB values to find the one that produces an occupied bandwidth
closest to the expected bandwidth for that signal type.

Legal: Receive-only. Radiocommunications Act 1992 (Cth).
       No transmission. Jurisdiction: AU/SA. Authority: ACMA.

Usage:
    PYTHONPATH=. python tools/diagnose_threshold.py
    PYTHONPATH=. python tools/diagnose_threshold.py --band adsb
"""

import argparse
import sys

import numpy as np

from core.pipeline.capture import capture_iq
from core.pipeline.features import fingerprint_spectrum
from core.pipeline.fft import compute_psd
from dashboard.shared_state import BAND_PROFILES

THRESHOLD_CANDIDATES = [3, 5, 8, 10, 12, 15, 18, 21, 24, 27]

BAND_SWEEP = [
    {
        "name": "FM Broadcast",
        "freq_hz": 98_900_000,
        "lna_gain_db": BAND_PROFILES["fm_broadcast"]["lna_gain_db"],
        "vga_gain_db": BAND_PROFILES["fm_broadcast"]["vga_gain_db"],
        "target_bw_hz": 200_000,
        "sample_rate_hz": 2_000_000,
        "num_samples": 256_000,
    },
    {
        "name": "Aviation VHF",
        "freq_hz": 127_000_000,
        "lna_gain_db": BAND_PROFILES["aviation"]["lna_gain_db"],
        "vga_gain_db": BAND_PROFILES["aviation"]["vga_gain_db"],
        "target_bw_hz": 8_300,
        "sample_rate_hz": 2_000_000,
        "num_samples": 256_000,
    },
    {
        "name": "ACARS",
        "freq_hz": 129_125_000,
        "lna_gain_db": BAND_PROFILES["acars"]["lna_gain_db"],
        "vga_gain_db": BAND_PROFILES["acars"]["vga_gain_db"],
        "target_bw_hz": 12_500,
        "sample_rate_hz": 2_000_000,
        "num_samples": 256_000,
    },
    {
        "name": "APRS",
        "freq_hz": 145_175_000,
        "lna_gain_db": BAND_PROFILES["aprs"]["lna_gain_db"],
        "vga_gain_db": BAND_PROFILES["aprs"]["vga_gain_db"],
        "target_bw_hz": 12_500,
        "sample_rate_hz": 2_000_000,
        "num_samples": 256_000,
    },
    {
        "name": "ISM / LoRa",
        "freq_hz": 915_000_000,
        "lna_gain_db": BAND_PROFILES["ism"]["lna_gain_db"],
        "vga_gain_db": BAND_PROFILES["ism"]["vga_gain_db"],
        "target_bw_hz": 500_000,
        "sample_rate_hz": 2_000_000,
        "num_samples": 256_000,
    },
    {
        "name": "ADS-B",
        "freq_hz": 1_090_000_000,
        "lna_gain_db": BAND_PROFILES["adsb"]["lna_gain_db"],
        "vga_gain_db": BAND_PROFILES["adsb"]["vga_gain_db"],
        "target_bw_hz": 1_000_000,
        "sample_rate_hz": 2_000_000,
        "num_samples": 256_000,
    },
]

# NOTE: BAND_SWEEP has no AIS entry (pre-existing). Future enhancement:
# add AIS to BAND_SWEEP if threshold-sweeping AIS is desired.

BAND_KEYS = {b["name"].lower().replace(" / ", "_").replace("-", "_").replace(" ", "_"): b for b in BAND_SWEEP}


def sweep_band(band: dict) -> dict:
    """Capture and sweep thresholds for a single band.

    Returns:
        Dict with keys: name, freq_hz, recommended_thr, recommended_bw, rows
        where rows is a list of (thr, bw, bins) tuples.
    """
    print(f"═══ {band['name']} ({band['freq_hz'] / 1e6:.3f} MHz) ═══")
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
        fp = fingerprint_spectrum(psd_result, signal_threshold_db=float(thr))
        bw = fp["bandwidth_hz"]
        bins = fp["occupied_bins"]
        rows.append((thr, bw, bins))
        print(
            f"  threshold={thr:>2} dB  →  "
            f"bandwidth={bw:>8.0f} Hz  bins={bins:>5}  "
            f"[target: {band['target_bw_hz']} Hz]"
        )

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
        choices=list(BAND_KEYS.keys()),
        help="Sweep a single band instead of all six.",
    )
    args = parser.parse_args()

    bands = [BAND_KEYS[args.band]] if args.band else BAND_SWEEP
    results = []

    for band in bands:
        result = sweep_band(band)
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
    print(
        "Update signal_threshold_db in BAND_PROFILES (dashboard/shared_state.py) "
        "with these recommended values."
    )


if __name__ == "__main__":
    main()
