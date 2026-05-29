"""
calibrate_thresholds.py — Calibration script for Mimir RF Scanner

This standalone script captures real IQ samples from the HackRF One across
multiple frequency bands, processes them through the existing pipeline, and
computes pairwise distance statistics to suggest threshold values for use in
llm/classifier.py's _build_system_prompt() function.

The script stores calibration vectors in a SEPARATE ChromaDB collection at
"data/calibration_vectorstore" — it does NOT touch data/vectorstore/ (production).

Usage:
    python tools/calibrate_thresholds.py

Legal: Receive-only. Radiocommunications Act 1992 (Cth).
       No transmission. Jurisdiction: AU/SA. Authority: ACMA.
"""

from core.pipeline.capture import capture_iq
from core.pipeline.fft import compute_psd
from core.pipeline.features import fingerprint_spectrum
from embeddings.embedder import SpectrumEmbedder
from embeddings.store import SignalStore

import itertools
import logging
import time
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# =============================================================================
# SECTION 1 — CALIBRATION_TARGETS config block
# =============================================================================
CALIBRATION_TARGETS: list[dict] = [
    {
        "label": "FM_broadcast",
        "freq_hz": 98_900_000,
        "sample_rate_hz": 2_000_000,
        "num_samples": 256_000,
        "lna_gain_db": 32,
        "vga_gain_db": 40,
        "captures": 2,
    },
    {
        "label": "ADS_B",
        "freq_hz": 1_090_000_000,
        "sample_rate_hz": 2_000_000,
        "num_samples": 256_000,
        "lna_gain_db": 32,
        "vga_gain_db": 38,
        "captures": 2,
    },
    {
        "label": "Aviation_VHF",
        "freq_hz": 127_000_000,
        "sample_rate_hz": 2_000_000,
        "num_samples": 256_000,
        "lna_gain_db": 32,
        "vga_gain_db": 40,
        "captures": 2,
    },
    {
        "label": "noise_floor",
        "freq_hz": 433_000_000,
        "sample_rate_hz": 2_000_000,
        "num_samples": 256_000,
        "lna_gain_db": 16,
        "vga_gain_db": 20,
        "captures": 2,
    },
]

# =============================================================================
# SECTION 2 — main() function
# =============================================================================


def main() -> None:
    """
    Main calibration workflow.

    1. Print ADS-B warning and wait for user confirmation.
    2. Initialise calibration vectorstore (overwrites any existing).
    3. Capture IQ samples for each target, run through pipeline, store vectors.
    4. Compute pairwise distance matrix between all stored vectors.
    5. Analyse distances to suggest threshold values for classifier.

    All capture and processing is RX-only — no transmit functionality.
    """
    logger.info("Starting Mimir calibration workflow")

    # ─────────────────────────────────────────────────────────────────────────
    # Step A — ADS-B warning at startup
    # ─────────────────────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("ADS-B CAPTURE WARNING")
    print("=" * 70)
    print()
    print("The ADS-B target (1090 MHz) will only show a real signal if an aircraft")
    print("is overhead. Without an aircraft, you will see noise floor only.")
    print()
    print("Check live aircraft positions at:")
    print("  https://www.flightradar24.com")
    print()
    print("Press ENTER to continue calibration, or Ctrl+C to abort entirely:")
    # Use input() directly as requested — no argument parsing
    try:
        input("Press ENTER to continue or Ctrl+C to abort: ")
    except KeyboardInterrupt:
        logger.info("User aborted calibration at ADS-B warning")
        raise SystemExit(0)

    # ─────────────────────────────────────────────────────────────────────────
    # Step B — Store initialisation (overwrite on every run)
    # ─────────────────────────────────────────────────────────────────────────
    store_path = Path("data/calibration_vectorstore")
    store_path.mkdir(parents=True, exist_ok=True)

    store = SignalStore(path=str(store_path))
    store.delete_collection()
    store = SignalStore(path=str(store_path))

    embedder = SpectrumEmbedder()

    # ─────────────────────────────────────────────────────────────────────────
    # Step C — Capture loop
    # ─────────────────────────────────────────────────────────────────────────
    total_expected = sum(t["captures"] for t in CALIBRATION_TARGETS)
    captured_count = 0

    entries: list[dict] = []

    for idx, target in enumerate(CALIBRATION_TARGETS):
        for cap_idx in range(target["captures"]):
            label = target["label"]
            freq_hz = target["freq_hz"]
            num_samples = target["num_samples"]
            sample_rate_hz = target["sample_rate_hz"]
            lna_gain_db = target["lna_gain_db"]
            vga_gain_db = target["vga_gain_db"]

            record_id = f"{label}_{cap_idx}"

            print(f"\n[{idx + 1}/{len(CALIBRATION_TARGETS)}] Capturing: {label}")
            print(f"  Frequency: {freq_hz / 1e6:.3f} MHz")
            print(f"  Samples: {num_samples:,}")
            print(f"  Capture #{cap_idx + 1}/{target['captures']}")

            try:
                # Capture IQ samples from HackRF (RX-only)
                samples = capture_iq(
                    freq_hz=freq_hz,
                    num_samples=num_samples,
                    sample_rate_hz=sample_rate_hz,
                    lna_gain_db=lna_gain_db,
                    vga_gain_db=vga_gain_db,
                )

                # Run through pipeline: FFT → features → embedding
                psd_result = compute_psd(
                    samples=samples,
                    sample_rate_hz=sample_rate_hz,
                    center_freq_hz=freq_hz,
                )

                fingerprint = fingerprint_spectrum(psd_result)
                vector = embedder.embed(fingerprint)

                # Build record dict with required structure
                record = {
                    "id": record_id,
                    "embedding": vector,
                    "label": label,
                    "metadata": {
                        "label": label,
                        "capture_index": cap_idx,
                        "freq_hz": freq_hz,
                        "timestamp": datetime.now().isoformat(),
                        "peak_power_db": fingerprint["peak_power_db"],
                        "snr_db": fingerprint["snr_db"],
                    },
                }

                store.add(record)
                captured_count += 1

                # Print one-line summary
                print(
                    f"  ✓ Stored: peak={fingerprint['peak_power_db']:.2f} dB, "
                    f"SNR={fingerprint['snr_db']:.2f} dB"
                )

                entries.append({"id": record_id, "label": label, "embedding": vector})

            except RuntimeError as err:
                logger.error("Capture failed for %s (capture %d): %s", label, cap_idx, err)
                print(f"  ✗ FAILED: {err}")
                continue

            is_last = (
                idx == len(CALIBRATION_TARGETS) - 1
                and cap_idx == target["captures"] - 1
            )
            if not is_last:
                logger.info("Waiting 5 seconds before next capture")
                time.sleep(5)

    # ─────────────────────────────────────────────────────────────────────────
    # Step D — Distance matrix computation
    # ─────────────────────────────────────────────────────────────────────────
    if captured_count < 2:
        logger.error(
            "Insufficient captures: %d (need at least 2 for distance analysis)",
            captured_count,
        )
        print("\nERROR: Fewer than 2 entries stored. Cannot compute distance matrix.")
        raise SystemExit(1)

    # Compute pairwise distances and store them
    distance_pairs: list[tuple[str, str, float]] = []

    for a, b in itertools.combinations(entries, 2):
        a_id, b_id = a["id"], b["id"]

        # Query store with embedding from entry a to find nearest neighbours
        query_result = store.query(a["embedding"], n_results=len(entries))

        # Get distances and metadatas (ChromaDB returns lists)
        distances = query_result.get("distances", [[]])[0]
        ids = query_result.get("ids", [[]])[0]

        # Find the distance to entry b
        try:
            idx_b = ids.index(b_id)
            distance = float(distances[idx_b])
            distance_pairs.append((a_id, b_id, distance))
        except ValueError:
            logger.warning("Could not find pair (%s, %s) in store", a_id, b_id)
            continue

    # ─────────────────────────────────────────────────────────────────────────
    # Print formatted distance matrix
    # ─────────────────────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("PAIRWISE DISTANCE MATRIX")
    print("=" * 70)

    # Sort entries for consistent ordering
    sorted_entries = sorted(entries, key=lambda x: (x["label"], x["id"]))
    # Calculate column width based on longest entry id
    col_width = max(len(e["id"]) for e in sorted_entries) + 2

    # Print header row — one column per entry, right-padded
    header_parts = [f"{'':>{col_width}}"]
    for e in sorted_entries:
        header_parts.append(f"{e['id']:>{col_width}}")
    print("  " + "".join(header_parts))
    print("  " + "-" * (col_width * (len(sorted_entries) + 1)))

    # Print each row
    for a in sorted_entries:
        row_parts = [f"{a['id']:>{col_width}}"]
        for b in sorted_entries:
            if a["id"] == b["id"]:
                cell = "*"
            else:
                dist = None
                for pa, pb, d in distance_pairs:
                    if (pa == a["id"] and pb == b["id"]) or \
                       (pb == a["id"] and pa == b["id"]):
                        dist = d
                        break
                if dist is not None:
                    marker = "*" if a["label"] == b["label"] else " "
                    cell = f"{dist:.4f}{marker}"
                else:
                    cell = "N/A  "
            row_parts.append(f"{cell:>{col_width}}")
        print("  " + "".join(row_parts))

    # ─────────────────────────────────────────────────────────────────────────
    # Step E — Threshold analyser
    # ─────────────────────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("THRESHOLD ANALYSIS")
    print("=" * 70)

    same_type_pairs = []
    cross_type_pairs = []
    noise_pairs = []

    for a_id, b_id, dist in distance_pairs:
        # Find labels for these ids
        a_label = None
        b_label = None
        for e in entries:
            if e["id"] == a_id:
                a_label = e["label"]
            if e["id"] == b_id:
                b_label = e["label"]

        is_same_type = a_label == b_label
        is_noise_a = a_label == "noise_floor"
        is_noise_b = b_label == "noise_floor"
        is_cross_type = (
            not is_same_type and not is_noise_a and not is_noise_b
        )

        if is_same_type:
            same_type_pairs.append(dist)
        if is_cross_type:
            cross_type_pairs.append(dist)
        if is_noise_a or is_noise_b:
            noise_pairs.append(dist)

    # Compute statistics
    same_type_max = max(same_type_pairs) if same_type_pairs else 0.0
    cross_type_min = min(cross_type_pairs) if cross_type_pairs else 1.0
    noise_min = min(noise_pairs) if noise_pairs else 1.0

    # Suggested thresholds for _build_system_prompt() in llm/classifier.py
    STRONG_MATCH = round(same_type_max * 2, 3)
    POSSIBLE_MATCH = round((same_type_max * 2 + cross_type_min) / 2, 3)
    DIFFERENT_TYPE = round(cross_type_min * 0.9, 3)
    NOVEL_SIGNAL = DIFFERENT_TYPE

    print("\nComputed statistics:")
    print(f"  same_type_pairs:       {len(same_type_pairs)} pairs")
    print(f"  cross_type_pairs:      {len(cross_type_pairs)} pairs")
    print(f"  noise_floor_pairs:     {len(noise_pairs)} pairs")
    print()
    print("Same-type max distance:   {:.4f}".format(same_type_max))
    print("Cross-type min distance:  {:.4f}".format(cross_type_min))
    print("Noise floor min distance: {:.4f}".format(noise_min))
    print()
    print("-" * 70)
    print("SUGGESTED THRESHOLDS (for llm/classifier.py → _build_system_prompt()):")
    print("-" * 70)
    print()
    print(f"STRONG_MATCH     = {STRONG_MATCH:.3f}")
    print(f"                 → Same-type signals within this distance are strong matches")
    print()
    print(f"POSSIBLE_MATCH   = {POSSIBLE_MATCH:.3f}")
    print(f"                 → Borderline cases between same-type and different-type")
    print()
    print(f"DIFFERENT_TYPE   = {DIFFERENT_TYPE:.3f}")
    print(f"NOVEL_SIGNAL     = {NOVEL_SIGNAL:.3f}")
    print(f"                 → Signals above this threshold are considered novel/unseen")
    print()

    print("=" * 70)
    logger.info("Calibration complete. %d vectors stored, thresholds computed.", captured_count)


if __name__ == "__main__":
    main()
