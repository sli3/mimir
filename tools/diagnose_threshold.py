"""
DIAGNOSTIC TOOL — delete after use

Sweeps SIGNAL_THRESHOLD_DB values (3–27 dB) and prints which one
produces an occupied bandwidth closest to 200 kHz for a live FM
broadcast signal at 98.9 MHz (Adelaide).  The candidate values are
defined in THRESHOLD_CANDIDATES below.

Legal: Receive-only. Radiocommunications Act 1992 (Cth).
       No transmission. Jurisdiction: AU/SA. Authority: ACMA.

Usage:
    PYTHONPATH=. python tools/diagnose_threshold.py
"""

import sys

import numpy as np

from core.pipeline.capture import capture_iq
from core.pipeline.features import fingerprint_spectrum
from core.pipeline.features import SIGNAL_THRESHOLD_DB as ORIGINAL_THRESHOLD
from core.pipeline.fft import compute_psd

FREQ_HZ = 98_900_000
SAMPLE_RATE_HZ = 2_000_000
NUM_SAMPLES = 256_000

# Adelaide FM is extremely strong. Use minimum gain to avoid saturation.
LNA_GAIN_DB = 0
VGA_GAIN_DB = 0

THRESHOLD_CANDIDATES = [3, 5, 8, 10, 12, 15, 18, 21, 24, 27]

TARGET_BANDWIDTH_HZ = 200_000


def main() -> None:
    print(f"Tuning to {FREQ_HZ / 1e6:.1f} MHz (FM Adelaide) ...")
    samples = capture_iq(
        freq_hz=FREQ_HZ,
        num_samples=NUM_SAMPLES,
        sample_rate_hz=SAMPLE_RATE_HZ,
        lna_gain_db=LNA_GAIN_DB,
        vga_gain_db=VGA_GAIN_DB,
    )
    print(f"Captured {len(samples)} IQ samples")

    psd_result = compute_psd(
        samples=samples,
        sample_rate_hz=SAMPLE_RATE_HZ,
        center_freq_hz=FREQ_HZ,
    )

    if len(psd_result["psd_db"]) == 0:
        print("ERROR: Empty PSD — cannot continue.", file=sys.stderr)
        sys.exit(1)

    rows = []
    for thr in THRESHOLD_CANDIDATES:
        import core.pipeline.features as features

        features.SIGNAL_THRESHOLD_DB = float(thr)
        fp = fingerprint_spectrum(psd_result)
        bw = fp["bandwidth_hz"]
        bins = fp["occupied_bins"]
        rows.append((thr, bw, bins))
        print(f"  threshold={thr:>2} dB  →  bandwidth={bw:>8.0f} Hz  bins={bins:>5}")

    features.SIGNAL_THRESHOLD_DB = ORIGINAL_THRESHOLD

    print()
    diffs = [(abs(bw - TARGET_BANDWIDTH_HZ), thr, bw, bins) for thr, bw, bins in rows]
    best = min(diffs, key=lambda x: x[0])
    print(
        f"RECOMMENDATION: SIGNAL_THRESHOLD_DB = {best[1]} dB  "
        f"(bandwidth={best[2]:.0f} Hz — closest to {TARGET_BANDWIDTH_HZ / 1000:.0f} kHz)"
    )


if __name__ == "__main__":
    main()
