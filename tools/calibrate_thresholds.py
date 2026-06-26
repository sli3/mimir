"""
calibrate_thresholds.py — Calibration script for Mimir RF Scanner

This standalone script captures real IQ samples from the HackRF One across
multiple frequency bands, processes them through the existing pipeline, and
computes pairwise distance statistics to suggest threshold values for use in
llm/classifier.py's _DISTANCE_SCALE_REFERENCE constant and _build_user_prompt()
threshold block.

At startup the operator selects the connected antenna; only bands within that
antenna's usable range are captured. Per-band warnings are shown before the
first capture of ADS-B, ACARS, and AIS because those bands require live aircraft
or vessel signals to produce meaningful vectors.

If the total number of captured entries exceeds 8, the pairwise distance matrix
is split into two halves so each half fits a normal terminal width.

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

# ANSI colour helpers for terminal output
ANSI_GREEN = "\033[92m"
ANSI_YELLOW = "\033[93m"
ANSI_RED = "\033[91m"
ANSI_RESET = "\033[0m"

# Matrix is split into two halves when there are more than this many entries.
MATRIX_SPLIT_THRESHOLD = 8

# Antenna-to-band mappings. Labels must match CALIBRATION_TARGETS exactly.
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
            "noise_floor",
        ],
    },
    "2": {
        "name": "V-dipole 533mm",
        "range": "130 MHz – 145 MHz",
        "bands": [
            "Aviation_VHF",
            "ACARS",
            "APRS",
            "noise_floor",
        ],
    },
    "3": {
        "name": "Spiral discone",
        "range": "800 MHz – 8500 MHz",
        "bands": [
            "ADS_B",
            "ISM_LoRa",
            "noise_floor",
        ],
    },
}


def _colour(text: str, code: str) -> str:
    """Wrap text in an ANSI colour code."""
    return f"{code}{text}{ANSI_RESET}"


def _print_band_warning(label: str) -> None:
    """Print a one-time warning for bands that need live signals.

    ADS-B, ACARS, and AIS only produce real fingerprints when aircraft or
    vessels are within range. Without them the tool captures noise-floor
    vectors, which corrupts the distance matrix and threshold suggestions.
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


# =============================================================================
# SECTION 1 — CALIBRATION_TARGETS config block
# =============================================================================
# Gain values match shared_state.py BAND_PROFILES exactly.
# FM_broadcast (24/26): calibrated telescopic whip, Phase 9C-Threshold.
# ADS_B (24/24): updated Phase 17 recalibration (was 32/38 stock-stub).
# Aviation_VHF (16/20), ACARS (16/20), AIS (16/20): VHF maritime/aviation,
#   not yet validated with telescopic whip — provisional.
# APRS (24/26): calibrated, diagnose_threshold.py Phase 11.
# ISM_LoRa (24/26): calibrated, diagnose_threshold.py Phase 11.
# noise_floor (0/0): zero-gain baseline for reference measurement.
CALIBRATION_TARGETS: list[dict] = [
    {
        "label": "FM_broadcast",
        "freq_hz": 98_900_000,
        "sample_rate_hz": 2_000_000,
        "num_samples": 256_000,
        "lna_gain_db": 24,  # calibrated: telescopic whip, Phase 9C-Threshold
        "vga_gain_db": 26,
        "captures": 2,
    },
    {
        "label": "ADS_B",
        "freq_hz": 1_090_000_000,
        "sample_rate_hz": 2_000_000,
        "num_samples": 256_000,
        "lna_gain_db": 24,  # Matches shared_state.py BAND_PROFILES adsb (Phase 17 recalibration)
        "vga_gain_db": 24,
        "captures": 2,
    },
    {
        "label": "Aviation_VHF",
        "freq_hz": 127_000_000,
        "sample_rate_hz": 2_000_000,
        "num_samples": 256_000,
        "lna_gain_db": 16,  # matches shared_state.py BAND_PROFILES aviation
        "vga_gain_db": 20,
        "captures": 2,
    },
    {
        "label": "ACARS",
        "freq_hz": 129_125_000,
        "sample_rate_hz": 2_000_000,
        "num_samples": 256_000,
        "lna_gain_db": 16,  # matches shared_state.py BAND_PROFILES acars
        "vga_gain_db": 20,
        "captures": 2,
    },
    {
        "label": "APRS",
        "freq_hz": 145_175_000,
        "sample_rate_hz": 2_000_000,
        "num_samples": 256_000,
        "lna_gain_db": 24,  # matches shared_state.py BAND_PROFILES aprs (calibrated)
        "vga_gain_db": 26,
        "captures": 2,
    },
    {
        "label": "AIS",
        "freq_hz": 162_000_000,
        "sample_rate_hz": 2_000_000,
        "num_samples": 256_000,
        "lna_gain_db": 16,  # matches shared_state.py BAND_PROFILES ais
        "vga_gain_db": 20,
        "captures": 2,
    },
    {
        "label": "ISM_LoRa",
        "freq_hz": 915_000_000,
        "sample_rate_hz": 2_000_000,
        "num_samples": 256_000,
        "lna_gain_db": 24,  # matches shared_state.py BAND_PROFILES ism (calibrated)
        "vga_gain_db": 26,
        "captures": 2,
    },
    {
        "label": "noise_floor",
        "freq_hz": 433_000_000,
        "sample_rate_hz": 2_000_000,
        "num_samples": 256_000,
        "lna_gain_db": 0,   # zero-gain baseline
        "vga_gain_db": 0,
        "captures": 2,
    },
]

# =============================================================================
# SECTION 2 — helper functions
# =============================================================================


def _print_matrix(
    row_entries: list[dict],
    col_entries: list[dict],
    distance_pairs: list[tuple[str, str, float]],
    strong_match: float,
    possible_match: float,
    different_type: float,
) -> None:
    """Print a pairwise distance matrix subset.

    All rows are printed, but only the requested columns are shown. This lets
    the full matrix be split into halves when it would otherwise overflow a
    terminal width.
    """
    # Calculate column width based on longest id in the full row/col union
    all_ids = {e["id"] for e in row_entries + col_entries}
    col_width = max(len(e_id) for e_id in all_ids) + 2

    # Header row — one column per col_entry
    header_parts = [f"{'':>{col_width}}"]
    for e in col_entries:
        header_parts.append(f"{e['id']:>{col_width}}")
    print("  " + "".join(header_parts))
    print("  " + "-" * (col_width * (len(col_entries) + 1)))

    # Print each row
    for a in row_entries:
        row_parts = [f"{a['id']:>{col_width}}"]
        for b in col_entries:
            if a["id"] == b["id"]:
                cell = f"{'*':>{col_width}}"
            else:
                dist = None
                for pa, pb, d in distance_pairs:
                    if (pa == a["id"] and pb == b["id"]) or \
                       (pb == a["id"] and pa == b["id"]):
                        dist = d
                        break
                if dist is not None:
                    marker = "*" if a["label"] == b["label"] else " "
                    cell_visible = f"{dist:.4f}{marker}"

                    is_same_type = a["label"] == b["label"]
                    is_noise = a["label"] == "noise_floor" or b["label"] == "noise_floor"

                    if is_same_type:
                        if dist <= strong_match:
                            c_code = ANSI_GREEN
                        elif dist <= possible_match:
                            c_code = ANSI_YELLOW
                        else:
                            c_code = ANSI_RED
                    elif is_noise:
                        if dist <= strong_match:
                            c_code = ANSI_RED
                        elif dist >= different_type:
                            c_code = ANSI_GREEN
                        else:
                            c_code = ANSI_YELLOW
                    else:
                        if dist >= different_type:
                            c_code = ANSI_GREEN
                        elif dist >= possible_match:
                            c_code = ANSI_YELLOW
                        else:
                            c_code = ANSI_RED

                    cell = _colour(f"{cell_visible:>{col_width}}", c_code)
                else:
                    cell = f"{'N/A  ':>{col_width}}"
            row_parts.append(cell)
        print("  " + "".join(row_parts))


# =============================================================================
# SECTION 3 — main() function
# =============================================================================


def main() -> None:
    """
    Main calibration workflow.

    1. Prompt user to select connected antenna; filter bands accordingly.
    2. Initialise calibration vectorstore (overwrites any existing).
    3. Capture IQ samples for each target, run through pipeline, store vectors.
       Per-band warnings for ADS-B, ACARS, and AIS fire before the first
       capture of each such band.
    4. Compute pairwise distance matrix between all stored vectors. Split the
       matrix into two halves if there are more than 8 capture entries.
    5. Analyse distances to suggest threshold values for classifier.

    All capture and processing is RX-only — no transmit functionality.
    """
    logger.info("Starting Mimir calibration workflow")

    # ─────────────────────────────────────────────────────────────────────────
    # Step A — Antenna selection at startup
    # ─────────────────────────────────────────────────────────────────────────
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
            logger.info("User aborted calibration at antenna selection")
            print()
            raise SystemExit(0)
        if antenna_choice not in ANTENNA_PROFILES:
            print("Invalid choice. Please enter 1, 2, or 3.")

    profile = ANTENNA_PROFILES[antenna_choice]
    selected_bands = set(profile["bands"])
    selected_targets = [t for t in CALIBRATION_TARGETS if t["label"] in selected_bands]

    skipped_labels = sorted(
        t["label"] for t in CALIBRATION_TARGETS if t["label"] not in selected_bands
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
    total_expected = sum(t["captures"] for t in selected_targets)
    captured_count = 0

    entries: list[dict] = []

    for idx, target in enumerate(selected_targets):
        for cap_idx in range(target["captures"]):
            label = target["label"]
            freq_hz = target["freq_hz"]
            num_samples = target["num_samples"]
            sample_rate_hz = target["sample_rate_hz"]
            lna_gain_db = target["lna_gain_db"]
            vga_gain_db = target["vga_gain_db"]

            record_id = f"{label}_{cap_idx}"

            print(f"\n[{idx + 1}/{len(selected_targets)}] Capturing: {label}")
            print(f"  Frequency: {freq_hz / 1e6:.3f} MHz")
            print(f"  Samples: {num_samples:,}")
            print(f"  Capture #{cap_idx + 1}/{target['captures']}")

            # Per-band warning fires once, before the first capture of the band.
            if cap_idx == 0 and label in ("ADS_B", "ACARS", "AIS"):
                _print_band_warning(label)
                try:
                    input("Press ENTER to continue or Ctrl+C to skip this band: ")
                except KeyboardInterrupt:
                    logger.info("User skipped %s band", label)
                    print(f"\n  Skipping {label} — no captures stored for this band.")
                    break

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
                idx == len(selected_targets) - 1
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

    # Compute thresholds for colouring distance cells (same formulas as Step E)
    entry_labels = {e["id"]: e["label"] for e in entries}
    _same_type_dists = []
    _cross_type_dists = []
    _noise_dists = []

    for a_id, b_id, dist in distance_pairs:
        a_lbl = entry_labels[a_id]
        b_lbl = entry_labels[b_id]
        if a_lbl == b_lbl:
            _same_type_dists.append(dist)
        elif "noise_floor" in (a_lbl, b_lbl):
            _noise_dists.append(dist)
        else:
            _cross_type_dists.append(dist)

    _col_same_type_max = max(_same_type_dists) if _same_type_dists else 0.0
    _col_cross_type_min = min(_cross_type_dists) if _cross_type_dists else 1.0

    STRONG_MATCH = round(_col_same_type_max * 2, 3)
    POSSIBLE_MATCH = round((_col_same_type_max * 2 + _col_cross_type_min) / 2, 3)
    DIFFERENT_TYPE = round(_col_cross_type_min * 0.9, 3)
    NOVEL_SIGNAL = DIFFERENT_TYPE

    # ─────────────────────────────────────────────────────────────────────────
    # Print formatted distance matrix
    # ─────────────────────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("PAIRWISE DISTANCE MATRIX")
    print("=" * 70)

    # Sort entries for consistent ordering
    sorted_entries = sorted(entries, key=lambda x: (x["label"], x["id"]))

    if len(sorted_entries) <= MATRIX_SPLIT_THRESHOLD:
        _print_matrix(
            sorted_entries,
            sorted_entries,
            distance_pairs,
            STRONG_MATCH,
            POSSIBLE_MATCH,
            DIFFERENT_TYPE,
        )
    else:
        mid = len(sorted_entries) // 2
        col_half_1 = sorted_entries[:mid]
        col_half_2 = sorted_entries[mid:]

        print("\n--- Matrix Part 1 of 2 ---")
        _print_matrix(
            sorted_entries,
            col_half_1,
            distance_pairs,
            STRONG_MATCH,
            POSSIBLE_MATCH,
            DIFFERENT_TYPE,
        )

        print("\n--- Matrix Part 2 of 2 ---")
        _print_matrix(
            sorted_entries,
            col_half_2,
            distance_pairs,
            STRONG_MATCH,
            POSSIBLE_MATCH,
            DIFFERENT_TYPE,
        )

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

    # Suggested thresholds for _DISTANCE_SCALE_REFERENCE and _build_user_prompt()
    # in llm/classifier.py.
    STRONG_MATCH = round(same_type_max * 2, 3)
    POSSIBLE_MATCH = round((same_type_max * 2 + cross_type_min) / 2, 3)
    DIFFERENT_TYPE = round(cross_type_min * 0.9, 3)
    NOVEL_SIGNAL = DIFFERENT_TYPE

    print("\nComputed statistics:")
    print(f"  same_type_pairs:       {len(same_type_pairs)} pairs")
    print(f"  cross_type_pairs:      {len(cross_type_pairs)} pairs")
    print(f"  noise_floor_pairs:     {len(noise_pairs)} pairs")
    print()
    if same_type_max <= 0.010:
        _st_colour = ANSI_GREEN
    elif same_type_max <= 0.022:
        _st_colour = ANSI_YELLOW
    else:
        _st_colour = ANSI_RED
    print("Same-type max distance:   {}".format(_colour("{:.4f}".format(same_type_max), _st_colour)))
    if cross_type_min >= 0.031:
        _ct_colour = ANSI_GREEN
    elif cross_type_min >= 0.022:
        _ct_colour = ANSI_YELLOW
    else:
        _ct_colour = ANSI_RED
    print("Cross-type min distance:  {}".format(_colour("{:.4f}".format(cross_type_min), _ct_colour)))
    if noise_min >= 0.031:
        _nf_colour = ANSI_GREEN
    elif noise_min >= 0.022:
        _nf_colour = ANSI_YELLOW
    else:
        _nf_colour = ANSI_RED
    print("Noise floor min distance: {}".format(_colour("{:.4f}".format(noise_min), _nf_colour)))
    print()
    print("-" * 70)
    print("SUGGESTED THRESHOLDS — update TWO locations in llm/classifier.py:")
    print("-" * 70)
    print()
    print("1. _DISTANCE_SCALE_REFERENCE (module-level constant, ~line 155)")
    print("   Update the distance range text and reference distances.")
    print()
    print("2. _build_user_prompt() threshold block (~lines 424-431)")
    print("   Update the if/elif distance comparisons that label each neighbour.")
    print()

    _diff_type_gap = cross_type_min - same_type_max
    _diff_type_colour = ANSI_GREEN if _diff_type_gap > 0.010 else ANSI_RED

    print(f"STRONG_MATCH     = {_colour(f'{STRONG_MATCH:.3f}', ANSI_GREEN)}")
    print(f"                 → Same-type signals within this distance are strong matches")
    print()
    print(f"POSSIBLE_MATCH   = {_colour(f'{POSSIBLE_MATCH:.3f}', ANSI_YELLOW)}")
    print(f"                 → Borderline cases between same-type and different-type")
    print()
    print(f"DIFFERENT_TYPE   = {_colour(f'{DIFFERENT_TYPE:.3f}', _diff_type_colour)}")
    print(f"NOVEL_SIGNAL     = {_colour(f'{NOVEL_SIGNAL:.3f}', _diff_type_colour)}")
    print(f"                 → Signals above this threshold are considered novel/unseen")
    print()

    print("=" * 70)
    logger.info("Calibration complete. %d vectors stored, thresholds computed.", captured_count)


if __name__ == "__main__":
    main()
