"""
calibrate_thresholds.py — Calibration script for Mimir RF Scanner

This standalone script captures real IQ samples across multiple frequency
bands, processes them through the existing pipeline, and computes pairwise
distance statistics to suggest threshold values for use in
llm/classifier.py's _DISTANCE_SCALE_REFERENCE constant and _build_user_prompt()
threshold block.

Supports TWO devices via --device:
  hackrf (default) — all 7 CALIBRATION_TARGETS bands, split lna/vga gain.
  pluto             — ISM_LoRa and ADS_B only (Pluto's stock 325 MHz-3.8 GHz
                       tuning range), combined gain_db from
                       PLUTO_BAND_PROFILES. noise_floor (433 MHz) is outside
                       Pluto's range too, so cross-type/noise stats will have
                       fewer entries than a HackRF run.

Calibration records are tagged with device in both the record id
(f"{label}_{device}_{cap_idx}") and metadata, so HackRF and Pluto
calibration vectors coexist in the same store without overwriting each
other and can be told apart later.

By default the script loads prior calibration vectors from a separate
ChromaDB collection at "data/calibration_vectorstore" and merges them with
newly captured vectors before deriving the ladder. A band is considered stale
if its newest stored capture is older than STALENESS_DAYS; stale bands are
excluded from the merged ladder unless recaptured. Use the --wipe flag to
fully reset the store and start from empty.

The operator is prompted to connect the appropriate antenna for each group of
bands that need calibration. Per-band warnings are shown before the first
capture of ADS-B, ACARS, and AIS because those bands require live aircraft or
vessel signals to produce meaningful vectors. ADS-B additionally prompts for
an antenna-length check on the telescopic whip (~68mm for 1090 MHz).

If the total number of captured entries exceeds 8, the pairwise distance
matrix is split into two halves so each half fits a normal terminal width.

The script stores calibration vectors in a SEPARATE ChromaDB collection at
"data/calibration_vectorstore" — it does NOT touch data/vectorstore/ (production).

Gain and threshold values are read live from dashboard.shared_state so
calibration vectors always match the live dashboard configuration:
  --device hackrf : lna_gain_db, vga_gain_db, signal_threshold_db from
                     BAND_PROFILES.
  --device pluto   : gain_db, signal_threshold_db from PLUTO_BAND_PROFILES,
                      checked via band_supported_by_device(). If a required
                      band is missing calibrated gain, the tool exits with a
                      clear error rather than guessing a gain value — run
                      tools/diagnose_pluto_gain.py first.

Usage:
    python tools/calibrate_thresholds.py
    python tools/calibrate_thresholds.py --wipe
    python tools/calibrate_thresholds.py --device pluto
    python tools/calibrate_thresholds.py --device pluto --wipe

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
import itertools
import logging
import numpy as np
import time
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# ANSI colour helpers for terminal output
ANSI_GREEN = "\033[92m"
ANSI_YELLOW = "\033[93m"
ANSI_RED = "\033[91m"
ANSI_RESET = "\033[0m"

# Maximum age of a stored calibration record before its band is considered stale
# and excluded from the merged ladder input. Fail-safe: malformed or missing
# timestamps are treated as stale.
STALENESS_DAYS = 14

# Matrix is split into two halves when there are more than this many entries.
MATRIX_SPLIT_THRESHOLD = 8

# Threshold-derivation constants. SEPARABILITY_FACTOR sets how far the
# cross-type nearest neighbour must be from the same-type furthest neighbour
# for a monotonic threshold set to exist. STRONG_MATCH_FLOOR prevents the
# strong-match ceiling from rounding to 0.000 on very clean captures.
SEPARABILITY_FACTOR = 2.5
STRONG_MATCH_FLOOR = 0.002
# CROSS_TYPE_MIN_FLOOR is an ABSOLUTE floor below which cross_type_min is treated
# as "no real separation measured", independent of the SEPARABILITY_FACTOR ratio.
# The ratio test alone passes on noise-vs-noise runs: if a burst band (ADS-B,
# ACARS, AIS) is captured with nothing overhead, same-type and cross-type
# distances both collapse into the noise floor, where the ratio can still hold by
# coincidence (e.g. cross=0.0005 > 2.5 * same=0.0001) while both magnitudes are
# meaningless jitter. Real cross-type separation observed in clean runs is ~0.012;
# a degenerate noise run measured ~0.0005. 0.005 sits an order of magnitude below
# real separation and an order above noise, so it rejects dead captures without
# risking valid ones. Global constant — revisit if ever calibrating a band with
# genuinely tight (<0.005) cross-type separation.
CROSS_TYPE_MIN_FLOOR = 0.005

# Antenna-to-band mappings. Labels must match CALIBRATION_TARGETS exactly.
#
# ADS_B on "Telescopic whip": same finding as tools/capture_to_vectorstore.py —
# retracted to ~68mm (quarter-wave for 1090 MHz), the same physical whip used
# at longer extensions for the other bands gives noticeably better ADS-B
# reception than the spiral discone. This is ONE whip at DIFFERENT
# extensions per band, not a separate antenna.
ANTENNA_PROFILES: dict[str, dict] = {
    "1": {
        "name": "Telescopic whip",
        "range": "75 MHz – 700 MHz (most bands); ~1090 MHz when retracted to ~68mm for ADS_B",
        "bands": [
            "FM_broadcast",
            "Aviation_VHF",
            "ACARS",
            "APRS",
            "AIS",
            "noise_floor",
            "ADS_B",
        ],
        "length_reminder": {
            "ADS_B": "Retract the telescopic whip to ~68mm (quarter-wave for 1090 MHz) before this capture — a much shorter extension than the other bands on this antenna.",
        },
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


def derive_thresholds(same_type_spread: float, cross_type_min: float) -> dict:
    """Derive classifier thresholds from calibration distance statistics.

    ``same_type_spread`` is the p90 of all same-type pair distances. It
    replaces the previous max reducer so that a single outlier capture window
    (common for burst signals such as ADS-B) cannot dominate the class spread.

    Returns a dict:
        {
            'ok': bool,
            'strong_match': float,
            'possible_match': float,
            'different_type': float,
            'novel_signal': float,
            'reason': str | None,
        }

    Monotonicity of the derived set requires
    ``cross_type_min > SEPARABILITY_FACTOR * same_type_spread``. When that fails the
    same-type captures overlap the cross-type captures and no usable threshold
    set exists; ``ok`` is False and the numeric fields are still returned for
    diagnostics but MUST NOT be presented as paste-ready.
    """
    # Two independent conditions must hold for a usable threshold set:
    #   (1) absolute: cross_type_min must clear CROSS_TYPE_MIN_FLOOR, else no real
    #       cross-class separation was measured (a near-noise / dead capture).
    #   (2) ratio: cross_type_min must exceed SEPARABILITY_FACTOR * same_type_spread,
    #       else same-type and cross-type captures overlap.
    # (1) is checked first because it is the more fundamental failure: when both
    # magnitudes are in the noise the ratio can pass by coincidence.
    floor_ok = cross_type_min >= CROSS_TYPE_MIN_FLOOR
    ratio_ok = cross_type_min > SEPARABILITY_FACTOR * same_type_spread
    ok = floor_ok and ratio_ok
    strong = max(round(same_type_spread * 2, 3), STRONG_MATCH_FLOOR)
    possible = round((same_type_spread * 2 + cross_type_min) / 2, 3)
    different = round(cross_type_min * 0.9, 3)
    if ok:
        reason = None
    elif not floor_ok:
        reason = (
            f'cross_type_min ({cross_type_min:.4f}) is below CROSS_TYPE_MIN_FLOOR '
            f'({CROSS_TYPE_MIN_FLOOR}): no real cross-class separation was measured. '
            f'The capture was almost certainly noise-only (no live signal in one or '
            f'more bands), so the distances are meaningless jitter.'
        )
    else:
        reason = (
            f'same_type_spread ({same_type_spread:.4f}) is not < cross_type_min '
            f'({cross_type_min:.4f}) / {SEPARABILITY_FACTOR}: the calibration '
            f'captures overlap, so no monotonic threshold set exists.'
        )
    return {
        'ok': ok, 'strong_match': strong, 'possible_match': possible,
        'different_type': different, 'novel_signal': different, 'reason': reason,
    }


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


def _compute_band_freshness(
    stored: dict, device: str | None = None, reference: datetime | None = None
) -> dict[str, tuple[bool, float, str]]:
    """Return freshness metadata for each stored band.

    For each label present in ``stored``, find the newest valid ISO-8601
    timestamp. Return a mapping from label to ``(is_fresh, age_days,
    newest_timestamp)`` where ``is_fresh`` is True when the newest capture is
    no older than ``STALENESS_DAYS``.

    Args:
        stored: store.get_all_embeddings() result.
        device: If given, only records whose metadata "device" matches are
            considered (records with no "device" key, i.e. captured before
            Pluto support existed, are treated as "hackrf" for backward
            compatibility). If None, all records are considered regardless
            of device — used only where device-blending is intentional.
        reference: Reference time for age calculation (defaults to now).

    Records with missing or malformed timestamps are ignored when searching
    for the newest timestamp; if no valid timestamp exists for a label, that
    label is omitted from the result (treated as stale/missing by callers).
    """
    if reference is None:
        reference = datetime.now()
    newest_by_label: dict[str, tuple[datetime, str]] = {}
    for meta in (stored.get("metadatas") or []):
        if not meta:
            continue
        if device is not None and meta.get("device", "hackrf") != device:
            continue
        label = meta.get("label")
        ts_str = meta.get("timestamp")
        if not label or not ts_str:
            continue
        try:
            ts = datetime.fromisoformat(ts_str)
        except (ValueError, TypeError):
            continue
        if label not in newest_by_label or ts > newest_by_label[label][0]:
            newest_by_label[label] = (ts, ts_str)
    result: dict[str, tuple[bool, float, str]] = {}
    for label, (ts, ts_str) in newest_by_label.items():
        age_days = (reference - ts).total_seconds() / 86400
        is_fresh = age_days <= STALENESS_DAYS
        result[label] = (is_fresh, age_days, ts_str)
    return result


def _print_startup_summary(freshness: dict[str, tuple[bool, float, str]]) -> None:
    """Print the current calibration-store status before capturing."""
    print("\n" + "=" * 70)
    print("CALIBRATION STORE STATUS")
    print("=" * 70)
    if not freshness:
        print("No prior calibration data — starting fresh.")
        return
    for label in sorted(freshness):
        is_fresh, age_days, ts_str = freshness[label]
        status = "FRESH" if is_fresh else "STALE, excluded unless recaptured"
        age_word = "today" if age_days < 1 else f"{int(age_days)} days ago"
        print(f"{label:12} — last calibrated {age_word:12} ({ts_str[:10]}) — {status}")
    print()


def _prompt_recapture_fresh_bands(
    fresh_labels: set[str], targets: list[dict]
) -> set[str]:
    """Ask which fresh bands the operator wants to recapture.

    Args:
        fresh_labels: Labels considered fresh (not stale).
        targets: The active target list (CALIBRATION_TARGETS for hackrf, or
            _build_pluto_calibration_targets() output for pluto) — determines
            which band names are shown as valid, so a Pluto run does not
            advertise HackRF-only bands as recapture options.

    Returns a set of labels the operator chose to recapture. Empty input or
    Ctrl+C defaults to skipping all fresh bands.
    """
    if not fresh_labels:
        return set()
    print("\n" + "=" * 70)
    print("FRESH BANDS ALREADY CALIBRATED")
    print("=" * 70)
    print(
        f"Fresh bands (within last {STALENESS_DAYS} days): "
        f"{', '.join(sorted(fresh_labels))}"
    )
    print("\nValid band names:")
    _label_width = max(len(t["label"]) for t in targets)
    for target in targets:
        print(
            f"  {target['label']:<{_label_width}}   "
            f"({target['freq_hz'] / 1e6:.3f} MHz)"
        )
    print("Enter comma-separated band names to recapture, or press ENTER to skip:")
    try:
        recapture_input = input("> ").strip()
    except KeyboardInterrupt:
        print()
        return set()
    chosen = {b.strip() for b in recapture_input.split(",") if b.strip()}
    return {b for b in chosen if b in fresh_labels}


def _build_antenna_groups(labels_to_capture: set[str]) -> dict[str, list[str]]:
    """Group bands by the first antenna profile that covers them.

    Ensures each band is assigned to exactly one antenna group even if it
    appears in multiple profiles.
    """
    label_to_antenna: dict[str, str] = {}
    for key, profile in ANTENNA_PROFILES.items():
        for band in profile["bands"]:
            if band not in label_to_antenna:
                label_to_antenna[band] = key
    groups: dict[str, list[str]] = {key: [] for key in ANTENNA_PROFILES}
    for label in sorted(labels_to_capture):
        key = label_to_antenna.get(label)
        if key is not None:
            groups[key].append(label)
    return groups


def _merge_stored_entries(
    entries: list[dict],
    store: SignalStore,
    freshness: dict[str, tuple[bool, float, str]],
    captured_bands: set[str],
    device: str | None = None,
) -> list[dict]:
    """Append stored non-stale records for bands not captured this run.

    Vectors from bands that were captured this run are excluded because their
    fresh vectors are already in ``entries``. Stale stored vectors are excluded
    to prevent outdated calibration data from corrupting the ladder.

    Args:
        device: If given, only merges records whose metadata "device"
            matches (missing "device" key treated as "hackrf", same
            backward-compatibility rule as _compute_band_freshness). Keeps a
            Pluto run's distance matrix from silently absorbing old HackRF
            vectors for the same band label, and vice versa.
    """
    all_stored = store.get_all_embeddings()
    all_stored_metas = all_stored.get("metadatas") or []
    for idx, meta in enumerate(all_stored_metas):
        if not meta:
            continue
        if device is not None and meta.get("device", "hackrf") != device:
            continue
        lbl = meta.get("label")
        if lbl is None or lbl in captured_bands:
            continue
        if lbl in freshness and freshness[lbl][0]:
            entries.append({
                "id": all_stored["ids"][idx],
                "label": lbl,
                "embedding": all_stored["embeddings"][idx],
            })
    return entries


def _classify_distance_pairs(
    distance_pairs: list[tuple[str, str, float]],
    entry_labels: dict[str, str],
) -> tuple[list[float], list[float], list[float]]:
    """Partition distance pairs into same-type, cross-type, and noise buckets.

    Each pair is classified by the labels in entry_labels:
      - same_type_pairs:    both endpoints share a label (e.g. FM vs FM)
      - cross_type_pairs:   endpoints have different non-noise labels
                            (e.g. FM vs ACARS)
      - noise_pairs:        at least one endpoint is "noise_floor"

    Returns three lists of distance floats in the order pairs were encountered.
    """
    same_type_pairs: list[float] = []
    cross_type_pairs: list[float] = []
    noise_pairs: list[float] = []
    for a_id, b_id, dist in distance_pairs:
        a_label = entry_labels[a_id]
        b_label = entry_labels[b_id]
        is_noise_a = a_label == "noise_floor"
        is_noise_b = b_label == "noise_floor"
        is_same_type = a_label == b_label
        is_cross_type = not is_same_type and not is_noise_a and not is_noise_b
        if is_same_type:
            same_type_pairs.append(dist)
        elif is_cross_type:
            cross_type_pairs.append(dist)
        elif is_noise_a or is_noise_b:
            noise_pairs.append(dist)
    return same_type_pairs, cross_type_pairs, noise_pairs


def _find_cross_type_min_pair(
    distance_pairs: list[tuple[str, str, float]],
    entry_labels: dict[str, str],
) -> tuple[float, tuple[str, str] | None]:
    """Return the minimum cross-type distance and the labels that produced it.

    Same-type pairs and pairs involving ``noise_floor`` are excluded, matching
    the ladder logic in ``derive_thresholds``.
    """
    cross_type_min = 1.0
    cross_type_min_pair: tuple[str, str] | None = None
    for a_id, b_id, dist in distance_pairs:
        a_label = entry_labels[a_id]
        b_label = entry_labels[b_id]
        is_noise = "noise_floor" in (a_label, b_label)
        is_same_type = a_label == b_label
        if is_same_type or is_noise:
            continue
        if dist < cross_type_min:
            cross_type_min = dist
            cross_type_min_pair = (a_label, b_label)
    return cross_type_min, cross_type_min_pair


# =============================================================================
# SECTION 1 — CALIBRATION_TARGETS config block
# =============================================================================
# Gain, signal_threshold_db, and lna/vga values are read live from
# dashboard.shared_state.BAND_PROFILES so calibration vectors always match
# the live dashboard configuration.
CALIBRATION_TARGETS: list[dict] = [
    {
        "label": "FM_broadcast",
        "freq_hz": 98_900_000,
        "sample_rate_hz": 2_000_000,
        "num_samples": 256_000,
        "lna_gain_db": BAND_PROFILES["fm_broadcast"]["lna_gain_db"],
        "vga_gain_db": BAND_PROFILES["fm_broadcast"]["vga_gain_db"],
        "signal_threshold_db": BAND_PROFILES["fm_broadcast"]["signal_threshold_db"],
        "captures": 2,
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
    {
        "label": "Aviation_VHF",
        "freq_hz": 127_000_000,
        "sample_rate_hz": 2_000_000,
        "num_samples": 256_000,
        "lna_gain_db": BAND_PROFILES["aviation"]["lna_gain_db"],
        "vga_gain_db": BAND_PROFILES["aviation"]["vga_gain_db"],
        "signal_threshold_db": BAND_PROFILES["aviation"]["signal_threshold_db"],
        "captures": 2,
    },
    {
        "label": "ACARS",
        "freq_hz": 129_125_000,
        "sample_rate_hz": 2_000_000,
        "num_samples": 256_000,
        "lna_gain_db": BAND_PROFILES["acars"]["lna_gain_db"],
        "vga_gain_db": BAND_PROFILES["acars"]["vga_gain_db"],
        "signal_threshold_db": BAND_PROFILES["acars"]["signal_threshold_db"],
        "captures": 2,
    },
    {
        "label": "APRS",
        "freq_hz": 145_175_000,
        "sample_rate_hz": 2_000_000,
        "num_samples": 256_000,
        "lna_gain_db": BAND_PROFILES["aprs"]["lna_gain_db"],
        "vga_gain_db": BAND_PROFILES["aprs"]["vga_gain_db"],
        "signal_threshold_db": BAND_PROFILES["aprs"]["signal_threshold_db"],
        "captures": 2,
    },
    {
        "label": "AIS",
        "freq_hz": 162_000_000,
        "sample_rate_hz": 2_000_000,
        "num_samples": 256_000,
        "lna_gain_db": BAND_PROFILES["ais"]["lna_gain_db"],
        "vga_gain_db": BAND_PROFILES["ais"]["vga_gain_db"],
        "signal_threshold_db": BAND_PROFILES["ais"]["signal_threshold_db"],
        "captures": 2,
    },
    {
        "label": "ISM_LoRa",
        "freq_hz": 915_000_000,
        "sample_rate_hz": 2_000_000,
        "num_samples": 256_000,
        "lna_gain_db": BAND_PROFILES["ism"]["lna_gain_db"],
        "vga_gain_db": BAND_PROFILES["ism"]["vga_gain_db"],
        "signal_threshold_db": BAND_PROFILES["ism"]["signal_threshold_db"],
        "captures": 2,
    },
    {
        "label": "noise_floor",
        "freq_hz": 433_000_000,
        "sample_rate_hz": 2_000_000,
        "num_samples": 256_000,
        "lna_gain_db": BAND_PROFILES["noise_floor"]["lna_gain_db"],
        "vga_gain_db": BAND_PROFILES["noise_floor"]["vga_gain_db"],
        "signal_threshold_db": BAND_PROFILES["noise_floor"]["signal_threshold_db"],
        "captures": 2,
    },
]

# Pluto's stock tuning range (325 MHz - 3.8 GHz) only covers these two Mimir
# bands out of the seven in CALIBRATION_TARGETS. noise_floor at 433 MHz is
# also outside this range, so Pluto calibration runs will have fewer
# cross-type/noise comparisons than a full HackRF run.
PLUTO_SUPPORTED_LABELS = ("ISM_LoRa", "ADS_B")

# CALIBRATION_TARGETS label -> BAND_PROFILES/PLUTO_BAND_PROFILES key. Single
# source of truth for this mapping, matching the pattern already established
# in tools/capture_to_vectorstore.py and tools/diagnose_threshold.py.
LABEL_TO_BAND_KEY = {
    "FM_broadcast": "fm_broadcast",
    "ADS_B": "adsb",
    "Aviation_VHF": "aviation",
    "ACARS": "acars",
    "APRS": "aprs",
    "AIS": "ais",
    "ISM_LoRa": "ism",
    "noise_floor": "noise_floor",
}


def _build_pluto_calibration_targets() -> list[dict]:
    """Build Pluto-gain calibration targets, restricted to ISM_LoRa/ADS_B.

    Reuses freq_hz/sample_rate_hz/num_samples/captures/trace_key from the
    existing CALIBRATION_TARGETS entries — only the gain model changes
    (combined gain_db instead of split lna/vga). Support and gain values are
    checked via band_supported_by_device(), the same helper
    tools/capture_to_vectorstore.py and tools/diagnose_threshold.py use.

    Raises:
        SystemExit: if PLUTO_BAND_PROFILES is missing, or a supported band
            is missing gain_db/signal_threshold_db. This tool never guesses
            a gain value on the operator's behalf.
    """
    try:
        from dashboard.shared_state import (
            PLUTO_BAND_PROFILES,
            band_supported_by_device,
        )
    except ImportError:
        print(
            "\nERROR: dashboard.shared_state.PLUTO_BAND_PROFILES does not exist yet.\n"
            "Pluto calibration needs calibrated gain values first.\n"
            "Run tools/diagnose_pluto_gain.py, pick gain_db for ISM and ADS-B,\n"
            "and add a PLUTO_BAND_PROFILES dict to dashboard/shared_state.py.\n"
        )
        raise SystemExit(1)

    pluto_targets = []
    for base in CALIBRATION_TARGETS:
        label = base["label"]
        if label not in PLUTO_SUPPORTED_LABELS:
            continue
        key = LABEL_TO_BAND_KEY[label]

        if not band_supported_by_device(key, "plutosdr"):
            print(
                f"\nERROR: band_supported_by_device says Pluto does not "
                f"support '{key}' ({label}).\n"
                f"Reason: {PLUTO_BAND_PROFILES[key].get('reason', 'unknown')}\n"
            )
            raise SystemExit(1)

        profile = PLUTO_BAND_PROFILES[key]
        if "gain_db" not in profile or "signal_threshold_db" not in profile:
            print(
                f"\nERROR: PLUTO_BAND_PROFILES['{key}'] is marked supported "
                f"but is missing 'gain_db' or 'signal_threshold_db'.\n"
                f"Run tools/diagnose_pluto_gain.py --band {key} and add the "
                f"result.\n"
            )
            raise SystemExit(1)

        target = dict(base)
        target["gain_db"] = profile["gain_db"]
        target["signal_threshold_db"] = profile["signal_threshold_db"]
        target.pop("lna_gain_db", None)
        target.pop("vga_gain_db", None)
        pluto_targets.append(target)

    return pluto_targets

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

    1. Load the existing calibration vectorstore (persists across runs unless
       --wipe is supplied).
    2. --device hackrf (default) uses all 7 CALIBRATION_TARGETS bands.
       --device pluto restricts to ISM_LoRa/ADS_B via
       _build_pluto_calibration_targets(), and restricts ANTENNA_PROFILES
       iteration to whip ("1") and discone ("3") since those are the only
       antennas Pluto's two bands use.
    3. Determine which bands are stale or missing and group them by antenna.
    4. Prompt the operator to connect each antenna and capture the bands it
       covers. Per-band warnings for ADS-B, ACARS, and AIS fire before the
       first capture of each such band; ADS-B additionally prompts for an
       antenna-length check (telescopic whip only).
    5. Merge freshly captured vectors with stored non-stale vectors from bands
       not captured this run.
    6. Compute pairwise distance matrix between all merged vectors. Split the
       matrix into two halves if there are more than 8 capture entries.
    7. Analyse distances to suggest threshold values for classifier.

    All capture and processing is RX-only — no transmit functionality.
    """
    logger.info("Starting Mimir calibration workflow")

    # ─────────────────────────────────────────────────────────────────────────
    # Step A — Parse CLI arguments
    # ─────────────────────────────────────────────────────────────────────────
    parser = argparse.ArgumentParser(
        description="Calibrate Mimir classifier thresholds from real RF captures."
    )
    parser.add_argument(
        "--wipe",
        action="store_true",
        help="Wipe the calibration vectorstore before starting (full re-baseline).",
    )
    parser.add_argument(
        "--device",
        choices=["hackrf", "pluto"],
        default="hackrf",
        help=(
            "SDR device to calibrate (default: hackrf). Pluto only "
            "supports ISM_LoRa and ADS_B (its stock 325 MHz-3.8 GHz tuning "
            "range excludes the other five bands, including noise_floor "
            "at 433 MHz)."
        ),
    )
    args = parser.parse_args()

    active_targets = (
        _build_pluto_calibration_targets()
        if args.device == "pluto"
        else CALIBRATION_TARGETS
    )
    # Pluto's two bands only ever use the whip ("1", for ADS_B retracted to
    # ~68mm) or the discone ("3", for ISM_LoRa) — the V-dipole ("2") covers
    # neither. Restricting ANTENNA_PROFILES iteration here means the capture
    # loop below (unchanged logic, just a filtered ANTENNA_PROFILES view)
    # never prompts for an antenna Pluto can't use those bands with.
    active_antenna_profiles = (
        {"1": ANTENNA_PROFILES["1"], "3": ANTENNA_PROFILES["3"]}
        if args.device == "pluto"
        else ANTENNA_PROFILES
    )

    # ─────────────────────────────────────────────────────────────────────────
    # Step B — Store initialisation (persists across runs; --wipe overrides)
    # ─────────────────────────────────────────────────────────────────────────
    store_path = Path("data/calibration_vectorstore")
    store_path.mkdir(parents=True, exist_ok=True)

    store = SignalStore(path=str(store_path))
    if args.wipe:
        store.delete_collection()
        store = SignalStore(path=str(store_path))
        print("Calibration store wiped — starting from empty")

    embedder = SpectrumEmbedder()

    # ─────────────────────────────────────────────────────────────────────────
    # Step C — Load stored records and decide what needs calibration
    # ─────────────────────────────────────────────────────────────────────────
    stored = store.get_all_embeddings()
    freshness = _compute_band_freshness(stored, device=args.device)
    _print_startup_summary(freshness)

    all_labels = {t["label"] for t in active_targets}
    stored_labels = set(freshness.keys())
    fresh_labels = {lbl for lbl, (is_fresh, _, _) in freshness.items() if is_fresh}
    stale_labels = {lbl for lbl, (is_fresh, _, _) in freshness.items() if not is_fresh}
    missing_labels = all_labels - stored_labels

    labels_to_capture = (missing_labels | stale_labels) & all_labels
    recapture = _prompt_recapture_fresh_bands(fresh_labels & all_labels, active_targets)
    labels_to_capture |= recapture

    if not labels_to_capture:
        print("\nAll bands are fresh — nothing to capture. Exiting.")
        raise SystemExit(0)

    antenna_groups = _build_antenna_groups(labels_to_capture)
    active_groups = {k: v for k, v in antenna_groups.items() if v}

    print("\n" + "=" * 70)
    print("ANTENNA CAPTURE PLAN")
    print("=" * 70)
    for key, profile in active_antenna_profiles.items():
        bands = active_groups.get(key, [])
        if not bands:
            continue
        print(f"{profile['name']:<22} ({profile['range']}): {', '.join(bands)}")
    print()

    # ─────────────────────────────────────────────────────────────────────────
    # Step D — Capture loop, grouped by antenna
    # ─────────────────────────────────────────────────────────────────────────
    captured_count = 0
    captured_bands: set[str] = set()
    entries: list[dict] = []

    for key, profile in active_antenna_profiles.items():
        bands = active_groups.get(key, [])
        if not bands:
            continue

        print("\n" + "=" * 70)
        print(f"ANTENNA: {profile['name']} ({profile['range']})")
        print("=" * 70)
        prompt = (
            f"Connect {profile['name']} now. "
            "Press ENTER when connected, or Ctrl+C to skip these bands: "
        )
        try:
            input(prompt)
        except KeyboardInterrupt:
            logger.info("User skipped antenna %s", profile['name'])
            print(f"\n  Skipped {profile['name']} bands: {', '.join(bands)}")
            continue

        for label in sorted(bands):
            target = next(t for t in active_targets if t["label"] == label)
            freq_hz = target["freq_hz"]
            num_samples = target["num_samples"]
            sample_rate_hz = target["sample_rate_hz"]
            if args.device == "pluto":
                gain_db = target["gain_db"]
            else:
                lna_gain_db = target["lna_gain_db"]
                vga_gain_db = target["vga_gain_db"]

            print(f"\nCapturing: {label} ({args.device})")
            print(f"  Frequency: {freq_hz / 1e6:.3f} MHz")
            print(f"  Samples: {num_samples:,}")

            # Antenna-length check for ADS_B on the telescopic whip only —
            # same finding as tools/capture_to_vectorstore.py and
            # tools/diagnose_threshold.py. profile["length_reminder"] is only
            # present on the whip profile, so this is a no-op on discone.
            reminder = profile.get("length_reminder", {}).get(label)
            if reminder:
                print(f"\n{reminder}\n")
                try:
                    input("Press ENTER once antenna is ready, or Ctrl+C to skip this band: ")
                except KeyboardInterrupt:
                    logger.info("User skipped %s band at antenna length check", label)
                    print(f"\n  Skipping {label} — no captures stored for this band.")
                    continue

            # Per-band warning fires once, before the first capture of the band.
            if label in ("ADS_B", "ACARS", "AIS"):
                _print_band_warning(label)
                try:
                    input("Press ENTER to continue or Ctrl+C to skip this band: ")
                except KeyboardInterrupt:
                    logger.info("User skipped %s band", label)
                    print(f"\n  Skipping {label} — no captures stored for this band.")
                    continue

            # Replace any prior vectors for THIS band AND THIS device before
            # writing new captures. delete_by_label() alone would also
            # delete the other device's calibration for the same label
            # (e.g. a Pluto ADS_B run wiping HackRF ADS_B calibration) — so
            # this filters by device in Python and deletes by id directly,
            # same get-then-delete-by-ids pattern SignalStore.delete_by_label
            # itself uses internally, matching tools/delete_low_snr.py's
            # precedent for standalone device-aware deletion.
            existing = store.get_all_embeddings()
            existing_metas = existing.get("metadatas") or []
            ids_to_delete = [
                existing["ids"][idx]
                for idx, meta in enumerate(existing_metas)
                if meta
                and meta.get("label") == label
                and meta.get("device", "hackrf") == args.device
            ]
            if ids_to_delete:
                store._collection.delete(ids=ids_to_delete)  # noqa: SLF001
                print(
                    f"  Replaced {len(ids_to_delete)} prior {args.device} "
                    f"calibration record(s) for {label}"
                )

            band_captured = False
            for cap_idx in range(target["captures"]):
                record_id = f"{label}_{args.device}_{cap_idx}"
                print(f"  Capture #{cap_idx + 1}/{target['captures']}")

                try:
                    if args.device == "pluto":
                        samples = capture_iq_pluto(
                            freq_hz=freq_hz,
                            num_samples=num_samples,
                            sample_rate_hz=sample_rate_hz,
                            gain_db=gain_db,
                        )
                    else:
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

                    fingerprint = fingerprint_spectrum(
                        psd_result,
                        signal_threshold_db=target["signal_threshold_db"],
                        trace_key=target.get('trace_key', 'psd_db'),
                    )
                    vector = embedder.embed(fingerprint)

                    # Build record dict with required structure
                    record = {
                        "id": record_id,
                        "embedding": vector,
                        "label": label,
                        "metadata": {
                            "label": label,
                            "device": args.device,
                            "capture_index": cap_idx,
                            "freq_hz": freq_hz,
                            "timestamp": datetime.now().isoformat(),
                            "peak_power_db": fingerprint["peak_power_db"],
                            "snr_db": fingerprint["snr_db"],
                        },
                    }

                    store.add(record)
                    captured_count += 1
                    band_captured = True

                    # Print one-line summary
                    print(
                        f"    ✓ Stored: peak={fingerprint['peak_power_db']:.2f} dB, "
                        f"SNR={fingerprint['snr_db']:.2f} dB"
                    )

                    entries.append({"id": record_id, "label": label, "embedding": vector})

                except RuntimeError as err:
                    logger.error(
                        "Capture failed for %s (capture %d): %s", label, cap_idx, err
                    )
                    print(f"    ✗ FAILED: {err}")
                    continue

                is_last = (
                    not any(
                        active_groups.get(k)
                        for k in list(active_antenna_profiles.keys())[
                            list(active_antenna_profiles.keys()).index(key) + 1:
                        ]
                    )
                    and label == sorted(bands)[-1]
                    and cap_idx == target["captures"] - 1
                )
                if not is_last:
                    logger.info("Waiting 5 seconds before next capture")
                    time.sleep(5)

            if band_captured:
                captured_bands.add(label)

    # ─────────────────────────────────────────────────────────────────────────
    # Step E — Merge stored non-stale vectors for bands not captured this run
    # ─────────────────────────────────────────────────────────────────────────
    entries = _merge_stored_entries(entries, store, freshness, captured_bands, device=args.device)

    # ─────────────────────────────────────────────────────────────────────────
    # Step F — Distance matrix computation
    # ─────────────────────────────────────────────────────────────────────────
    if len(entries) < 2:
        logger.error(
            "Insufficient entries: %d (need at least 2 for distance analysis)",
            len(entries),
        )
        print("\nERROR: Fewer than 2 entries available. Cannot compute distance matrix.")
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

    # Compute thresholds for colouring distance cells (same formulas as Step G)
    entry_labels = {e["id"]: e["label"] for e in entries}
    _same_type_dists = []
    _cross_type_dists = []

    for a_id, b_id, dist in distance_pairs:
        a_lbl = entry_labels[a_id]
        b_lbl = entry_labels[b_id]
        if a_lbl == b_lbl:
            _same_type_dists.append(dist)
        elif "noise_floor" not in (a_lbl, b_lbl):
            _cross_type_dists.append(dist)
        # noise_floor pairs are excluded from matrix threshold computation.

    _col_same_type_spread = float(np.percentile(_same_type_dists, 90)) if _same_type_dists else 0.0
    _col_cross_type_min = min(_cross_type_dists) if _cross_type_dists else 1.0

    _derived = derive_thresholds(_col_same_type_spread, _col_cross_type_min)
    STRONG_MATCH = _derived["strong_match"]
    POSSIBLE_MATCH = _derived["possible_match"]
    DIFFERENT_TYPE = _derived["different_type"]
    NOVEL_SIGNAL = _derived["novel_signal"]

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
    # Step G — Threshold analyser
    # ─────────────────────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("THRESHOLD ANALYSIS")
    print("=" * 70)

    same_type_pairs, cross_type_pairs, noise_pairs = _classify_distance_pairs(
        distance_pairs, entry_labels
    )

    # Compute statistics using the p90 of same-type distances so a single
    # outlier window (e.g. a near-noise ADS-B capture) does not define the
    # class spread. Cross-type distances keep the genuine worst-case min.
    same_type_spread = float(np.percentile(same_type_pairs, 90)) if same_type_pairs else 0.0
    cross_type_min, cross_type_min_pair = _find_cross_type_min_pair(
        distance_pairs, entry_labels
    )
    noise_min = min(noise_pairs) if noise_pairs else 1.0

    # Suggested thresholds for _DISTANCE_SCALE_REFERENCE and _build_user_prompt()
    # in llm/classifier.py.
    derived = derive_thresholds(same_type_spread, cross_type_min)
    STRONG_MATCH = derived["strong_match"]
    POSSIBLE_MATCH = derived["possible_match"]
    DIFFERENT_TYPE = derived["different_type"]
    NOVEL_SIGNAL = derived["novel_signal"]

    print("\nComputed statistics:")
    print(f"  same_type_pairs:       {len(same_type_pairs)} pairs")
    print(f"  cross_type_pairs:      {len(cross_type_pairs)} pairs")
    print(f"  noise_floor_pairs:     {len(noise_pairs)} pairs")
    print()
    if same_type_spread < cross_type_min / SEPARABILITY_FACTOR:
        _st_colour = ANSI_GREEN
    elif same_type_spread < cross_type_min:
        _st_colour = ANSI_YELLOW
    else:
        _st_colour = ANSI_RED
    print("Same-type spread (p90):   {}".format(_colour("{:.4f}".format(same_type_spread), _st_colour)))
    if cross_type_min > SEPARABILITY_FACTOR * same_type_spread:
        _ct_colour = ANSI_GREEN
    elif cross_type_min > same_type_spread:
        _ct_colour = ANSI_YELLOW
    else:
        _ct_colour = ANSI_RED
    print("Cross-type min distance:  {}".format(_colour("{:.4f}".format(cross_type_min), _ct_colour)))
    if cross_type_min_pair:
        print(f"                          ({cross_type_min_pair[0]} vs {cross_type_min_pair[1]})")
    if noise_min > cross_type_min:
        _nf_colour = ANSI_GREEN
    elif noise_min > same_type_spread:
        _nf_colour = ANSI_YELLOW
    else:
        _nf_colour = ANSI_RED
    print("Noise floor min distance: {}".format(_colour("{:.4f}".format(noise_min), _nf_colour)))
    print()
    print("-" * 70)
    if not derived["ok"]:
        print("CALIBRATION FAILED — THRESHOLDS NOT PASTE-READY")
        print("-" * 70)
        print()
        print(derived["reason"])
        print()
        print("Any thresholds derived from this run would collapse the")
        print("strong/possible/different/novel bands into a single bucket.")
        print()
        print("REMEDIATION: recapture the affected band(s) with a live signal")
        print("present. Burst bands (ADS-B, ACARS, AIS) need aircraft or vessels")
        print("in range — check flightradar24 / marinetraffic before recapturing.")
        print("Do NOT paste any thresholds from this run into llm/classifier.py.")
        print()
        print("=" * 70)
        logger.warning("Calibration unusable (%s); thresholds not emitted.",
                       "near-noise" if cross_type_min < CROSS_TYPE_MIN_FLOOR else "overlap")
        raise SystemExit(1)
    print("SUGGESTED THRESHOLDS — update TWO locations in llm/classifier.py:")
    print("-" * 70)
    print()
    print("1. _DISTANCE_SCALE_REFERENCE (module-level constant, ~line 155)")
    print("   Update the distance range text and reference distances.")
    print()
    print("2. _build_user_prompt() threshold block (~lines 424-431)")
    print("   Update the if/elif distance comparisons that label each neighbour.")
    print()

    _diff_type_colour = ANSI_GREEN if derived["ok"] else ANSI_RED

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