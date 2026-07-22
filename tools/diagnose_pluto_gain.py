"""
Pluto gain calibration diagnostic tool.

Captures live IQ samples from the ADALM-PLUTO on the two bands it can
physically tune (ISM 915 MHz and ADS-B 1090 MHz) and sweeps a range of
combined gain values. For each gain it records the noise floor, the number
of PSD bins exceeding the floor by a fixed margin (an excursion-count proxy
for the picket-fence spurs observed above ~30 dB), and the peak PSD value.
The output lets the operator pick calibrated gain_db values for
PLUTO_BAND_PROFILES by hand.

The excursion count is a deliberately simple proxy. It does not attempt to
classify an excursion as spur versus genuine signal; that distinction is
ultimately confirmed by comparing a clean HackRF trace at the same
frequency, as the original finding in core/device/pluto_rx.py did.

Note: See core/device/pluto_rx.py module docstring "MEASURED FINDINGS" for
the full context on the two Pluto behaviours this tool exists to expose:
spurs above ~30 dB gain and the non-monotonic gain-table boundary at ~32 dB.

Legal: Receive-only. Radiocommunications Act 1992 (Cth). No transmission.
       Jurisdiction: AU/SA. Authority: ACMA. 915 MHz (ISM, AU) and
       1090 MHz (ADS-B) are AU-legal to receive passively. Pluto RX-only
       enforced by PlutoReceiver.

Usage:
    PYTHONPATH=. python tools/diagnose_pluto_gain.py
    PYTHONPATH=. python tools/diagnose_pluto_gain.py --band ism
    PYTHONPATH=. python tools/diagnose_pluto_gain.py --band adsb
"""

import argparse
import logging
import sys

import numpy as np

from core.pipeline.capture import capture_iq_pluto
from core.pipeline.fft import compute_psd

logger = logging.getLogger(__name__)

# Gain candidates span the full AD9363 combined range, with extra density
# around 25-40 dB where the measured findings (gain-table boundary at ~32 dB,
# spur onset above ~30 dB) sit.
GAIN_CANDIDATES = [0, 10, 20, 25, 28, 30, 32, 35, 38, 40, 45, 50, 55, 60, 65, 70, 74.5]

# A PSD bin counts as an excursion if it exceeds the median noise floor by
# this many dB.
SPUR_MARGIN_DB = 10.0

# Pluto's stock tuning range (325-3800 MHz) covers only these two Mimir bands.
BAND_SWEEP = [
    {
        "name": "ISM",
        "freq_hz": 915_000_000,
        "sample_rate_hz": 2_000_000,
        "num_samples": 256_000,
    },
    {
        "name": "ADS-B",
        "freq_hz": 1_090_000_000,
        "sample_rate_hz": 2_000_000,
        "num_samples": 256_000,
    },
]

# Same key derivation as diagnose_threshold.py: "ISM" -> "ism",
# "ADS-B" -> "adsb" (hyphen stripped, not underscored).
BAND_KEYS = {b["name"].lower().replace(" / ", "_").replace("-", "").replace(" ", "_"): b for b in BAND_SWEEP}


def sweep_band(band: dict) -> dict:
    """Capture and sweep gain candidates for a single band.

    For each candidate gain a fresh capture is taken (gain is applied at
    open time, so each step opens and closes the device), the PSD is
    computed, and three measurements are recorded: the median noise floor,
    the number of bins exceeding floor + SPUR_MARGIN_DB, and the peak bin.

    A step that yields an empty PSD is reported to stderr and skipped; the
    remaining gains are still swept.

    Args:
        band: Dict with keys name, freq_hz, sample_rate_hz, num_samples.

    Returns:
        Dict with keys: name, freq_hz, rows, where rows is a list of
        (gain, noise_floor_db, excursions, max_db) tuples.
    """
    print(f"═══ {band['name']} ({band['freq_hz'] / 1e6:.3f} MHz) ═══")

    rows = []
    for gain in GAIN_CANDIDATES:
        try:
            samples = capture_iq_pluto(
                freq_hz=band["freq_hz"],
                num_samples=band["num_samples"],
                sample_rate_hz=band["sample_rate_hz"],
                gain_db=gain,
            )

            psd_result = compute_psd(
                samples=samples,
                sample_rate_hz=band["sample_rate_hz"],
                center_freq_hz=band["freq_hz"],
            )
        except (RuntimeError, OSError, ValueError) as exc:
            # A per-step hardware or processing failure (e.g. a USB hiccup
            # that exhausts PlutoReceiver's read retry) must skip the step,
            # not abort the whole 34-capture sweep with partial data.
            print(
                f"ERROR: capture/PSD failed at gain {gain:.1f} dB — skipping step",
                file=sys.stderr,
            )
            logger.warning(
                "Capture/PSD failure at gain %.1f dB on %s: %s; step skipped",
                gain,
                band["name"],
                exc,
            )
            continue

        psd_db = psd_result["psd_db"]
        if len(psd_db) == 0:
            print("ERROR: Empty PSD — skipping step", file=sys.stderr)
            logger.warning(
                "Empty PSD at gain %.1f dB on %s; step skipped",
                gain,
                band["name"],
            )
            continue

        noise_floor_db = float(np.median(psd_db))
        excursions = int(np.sum(psd_db > noise_floor_db + SPUR_MARGIN_DB))
        max_db = float(np.max(psd_db))

        print(
            f"  gain={gain:>5.1f} dB  →  "
            f"noise_floor={noise_floor_db:>7.2f} dB  "
            f"excursions={excursions:>4}  "
            f"max={max_db:>7.2f} dB"
        )
        rows.append((gain, noise_floor_db, excursions, max_db))

    print()
    return {
        "name": band["name"],
        "freq_hz": band["freq_hz"],
        "rows": rows,
    }


def main() -> None:
    """Run the gain sweep over the selected band(s) and print a summary."""
    parser = argparse.ArgumentParser(
        description="Sweep Pluto combined gain candidates for Mimir.",
    )
    parser.add_argument(
        "--band",
        choices=list(BAND_KEYS.keys()),
        help="Sweep a single band instead of both.",
    )
    args = parser.parse_args()

    bands = [BAND_KEYS[args.band]] if args.band else BAND_SWEEP
    results = []

    for band in bands:
        result = sweep_band(band)
        results.append(result)

    # Summary table
    print("╔══════════════════════════╦═══════════════════╦══════════════════╦══════════════════╗")
    print("║ Band                     ║ Gains swept       ║ Min floor (dB)   ║ Max excursions   ║")
    print("╠══════════════════════════╬═══════════════════╬══════════════════╬══════════════════╣")
    for r in results:
        if r["rows"]:
            min_floor = f"{min(row[1] for row in r['rows']):.2f}"
            max_exc = f"{max(row[2] for row in r['rows'])}"
        else:
            min_floor = "N/A"
            max_exc = "N/A"
        print(f"║ {r['name']:<24} ║ {len(r['rows']):>17} ║ {min_floor:>16} ║ {max_exc:>16} ║")
    print("╚══════════════════════════╩═══════════════════╩══════════════════╩══════════════════╝")
    print()

    # Interpretation aid: static guidance only, NOT a recommendation. The
    # calibrated value is an operator decision made against live conditions.
    print("Interpretation aid:")
    print(
        "  - Look at the 'excursions' column. A sharp rise as gain climbs "
        "past ~30 dB is the picket-fence spur onset recorded in pluto_rx.py — "
        "pick an operating gain below that onset."
    )
    print(
        "  - Look at the 'noise_floor' column near 30–35 dB. A DROP of a few "
        "dB around 32 dB is the known non-monotonic AD9363 gain-table boundary — "
        "it is not an improvement to chase."
    )
    print(
        "  - A strong LIVE in-band signal will also inflate the excursion "
        "count, so this sweep reads cleanest with no strong transmitter "
        "nearby. Spur vs signal is ultimately confirmed by comparing a clean "
        "HackRF trace at the same frequency (as the original finding did)."
    )
    print()
    print(
        "Update gain_db in PLUTO_BAND_PROFILES (dashboard/shared_state.py) "
        "with the values you select."
    )


if __name__ == "__main__":
    main()
