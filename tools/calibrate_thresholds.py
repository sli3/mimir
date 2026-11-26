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

Each band card shows the antenna name and any length reminder on separate,
aligned rows alongside live-traffic warnings, followed by one start prompt.
Multi-band antenna groups also have one connection prompt.
On a terminal, a block-bar spinner covers captures and waits, followed by a band
summary; piped logs and --verbose retain one line per capture. A band's first
failed capture stops that band and keeps its prior records. If failures leave
no completed bands, exit before analysing stored records or suggesting values.

With --verbose, print the distance matrix, computed statistics and log messages.
If the merged set exceeds 8 entries, split the matrix into two halves. Default
console logging is silent, including WARNING records from core/ and libraries;
uncaught exceptions still print their traceback. Default results highlight
captures closer to another band, without changing the maths.

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
    ./mimir tool calibrate_thresholds
    ./mimir tool calibrate_thresholds --wipe
    ./mimir tool calibrate_thresholds --device pluto
    ./mimir tool calibrate_thresholds --device pluto --wipe
    ./mimir tool calibrate_thresholds --verbose

Legal: Receive-only. Radiocommunications Act 1992 (Cth).
       No transmission. Jurisdiction: AU/SA. Authority: ACMA.
"""

from core.pipeline.capture import capture_iq, capture_iq_pluto
from core.pipeline.fft import compute_psd
from core.pipeline.features import fingerprint_spectrum
from dashboard.shared_state import BAND_PROFILES
from embeddings.embedder import SpectrumEmbedder
from embeddings.store import SignalStore
from tools._console import (
    FAILURE, OK, WARNING, Spinner, SpinnerLogHandler, box, dim, fail, next_step,
    ok, step, table, warn,
)

import argparse
import itertools
import logging
import numpy as np
import time
from datetime import datetime
from pathlib import Path
from textwrap import wrap

logger = logging.getLogger(__name__)

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


def _configure_console_logging(verbose: bool) -> None:
    """Replace root console handlers with silent or spinner-aware logging.

    Default mode hides root-propagated records, including WARNING messages
    from core/ and libraries. Uncaught exceptions still print their traceback.
    Verbose mode enables INFO for Mimir only, keeps the root at WARNING and
    routes messages around active progress. Repeated setup replaces handlers
    rather than duplicating console output.
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
        """Suppress third-party INFO even if a library enables it explicitly."""
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
    """Suppress SoapySDR INFO chatter while retaining driver warnings/errors.

    The RX/TX-capable binding is used only for logging here, without opening
    a device. Capture paths remain receive-only.
    Support both binding names and carry on when the binding is unavailable.
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
    """Return concise live-traffic warnings for inclusion in the band card.

    Aircraft/vessel bands need traffic within range; otherwise captures
    contain only noise. The card replaces the warning box and its prompt.
    """
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


def _print_startup_summary(
    freshness: dict[str, tuple[bool, float, str]], device: str
) -> None:
    """Show an aligned device header with fresh dates and stale exclusions."""
    rows = []
    for label in sorted(freshness):
        is_fresh, age_days, ts_str = freshness[label]
        if is_fresh:
            age = "today" if age_days < 1 else ts_str[:10]
            rows.append([ok(f"{OK} {label}"), ok(f"fresh · {age}")])
        else:
            rows.append([
                warn(f"{WARNING} {label}"),
                warn(f"stale · {int(age_days)} days ago ({ts_str[:10]}) · "
                     "excluded unless recaptured"),
            ])
    lines = table(rows) if rows else ["No prior calibration data, starting fresh"]
    box(f"Mimir · calibrate thresholds · {device}", lines)


def _prompt_recapture_fresh_bands(
    fresh_labels: set[str], targets: list[dict]
) -> set[str]:
    """List fresh bands briefly, then read a validated recapture selection.

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
    valid_names = [t["label"] for t in targets if t["label"] in fresh_labels]
    print(f"  Fresh within the last {STALENESS_DAYS} days: "
          f"{', '.join(sorted(fresh_labels))}.")
    print(f"  Recapture which? {', '.join(valid_names)} "
          "(comma-separated, Enter to skip)")
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


def _find_misplaced_captures(
    entries: list[dict], distance_pairs: list[tuple[str, str, float]]
) -> list[dict]:
    """Find captures closer to another label than their nearest own label.

    Skip labels with fewer than two entries. Other labels include noise_floor;
    an exact distance tie does not flag a capture. This is read-only reporting.
    """
    labels = {entry["id"]: entry["label"] for entry in entries}
    counts: dict[str, int] = {}
    for label in labels.values():
        counts[label] = counts.get(label, 0) + 1
    neighbours: dict[str, list[tuple[float, str]]] = {key: [] for key in labels}
    for a_id, b_id, distance in distance_pairs:
        neighbours[a_id].append((distance, b_id))
        neighbours[b_id].append((distance, a_id))
    misplaced = []
    for entry in entries:
        record_id, label = entry["id"], entry["label"]
        if counts[label] < 2:
            continue
        own = [d for d, other in neighbours[record_id] if labels[other] == label]
        other = [
            (d, key) for d, key in neighbours[record_id] if labels[key] != label
        ]
        if not own or not other:
            continue
        own_distance = min(own)
        other_distance, other_id = min(other)
        if other_distance < own_distance:
            misplaced.append({
                "id": record_id, "label": label,
                "nearest_other_id": other_id,
                "nearest_other_label": labels[other_id],
                "own_distance": own_distance, "other_distance": other_distance,
            })
    return misplaced


def _compute_pairwise_distances(
    entries: list[dict],
    store: SignalStore,
) -> list[tuple[str, str, float]]:
    """Compute pairwise distances between all entries using store.query().

    Returns list of (a_id, b_id, distance) tuples. Pairs whose partner cannot
    be located in the store's neighbour list (which after the fix genuinely
    indicates a bug: an entry whose ID was never added to the store) are
    dropped with a diagnostic logger.error log line and excluded from the
    result.

    n_results is sized to the entire store (not len(entries)) so the partner
    for a pair can never be truncated out of the neighbour list by off-device
    or older-session records competing for the top-K slots. Previous truncation
    at len(entries) silently dropped pairs whose partner was outside the top-K,
    distorting the threshold derivation (Phase 77).

    Caller invariant: every entry in `entries` must already be in the store
    (added via store.add() or merged from it). Because n_results spans the
    whole store, the competitor set is broader than just off-device records:
    stale same-device records of skipped bands (e.g. an operator aborting at
    the antenna prompt) also compete for neighbour slots.
    """
    n_results = store.count()
    distance_pairs: list[tuple[str, str, float]] = []

    for a, b in itertools.combinations(entries, 2):
        a_id, b_id = a["id"], b["id"]

        # Query store with embedding from entry a to find nearest neighbours
        query_result = store.query(a["embedding"], n_results=n_results)

        # Get distances and ids (ChromaDB returns lists)
        distances = query_result.get("distances", [[]])[0]
        ids = query_result.get("ids", [[]])[0]

        # Find the distance to entry b
        try:
            idx_b = ids.index(b_id)
            distance = float(distances[idx_b])
            distance_pairs.append((a_id, b_id, distance))
        except ValueError:
            logger.error(
                "Could not find pair (%s, %s) in store: store has %d records, "
                "queried n_results=%d; an entry ID present in entries but absent "
                "from the store indicates a bug",
                a_id,
                b_id,
                store.count(),
                n_results,
            )
            continue

    return distance_pairs


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
    """Print a matrix subset, colouring cells only on a colour-enabled TTY.

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
                            colour = ok
                        elif dist <= possible_match:
                            colour = warn
                        else:
                            colour = fail
                    elif is_noise:
                        if dist <= strong_match:
                            colour = fail
                        elif dist >= different_type:
                            colour = ok
                        else:
                            colour = warn
                    else:
                        if dist >= different_type:
                            colour = ok
                        elif dist >= possible_match:
                            colour = warn
                        else:
                            colour = fail

                    cell = colour(f"{cell_visible:>{col_width}}")
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

    1. Parse arguments and configure silent default or spinner-aware verbose
       logging. Load the existing store; --wipe deletes its entire calibration
       collection before captures begin.
    2. --device hackrf (default) uses all 7 CALIBRATION_TARGETS bands.
       --device pluto restricts to ISM_LoRa/ADS_B via
       _build_pluto_calibration_targets(), and restricts ANTENNA_PROFILES
       iteration to whip ("1") and discone ("3") since those are the only
       antennas Pluto's two bands use.
    3. Determine which bands are stale, missing or selected for recapture and
       group them by antenna. If none need capture, use the stored records.
    4. Show each band's antenna name, separate aligned length reminder, traffic
       warning and sample count in one card with one start prompt. Multi-band
       groups first prompt for connection. Animate captures and waits on a TTY,
       then summarise SNR; indent status lines by two spaces, retaining capture
       details in verbose/piped output. Replace prior records only after every
       capture succeeds. Stop a band on its first RuntimeError, report its
       error once by default and keep priors. Prompt skips remain separate.
    5. If failures leave no completed bands, report whether earlier records
       were wiped, show device guidance and exit.
       Otherwise merge new vectors with non-stale stored bands not captured.
    6. Compute distances between all merged vectors; --verbose prints the
       matrix, split into two halves above 8 entries, and detailed statistics.
    7. Report compact consistency results and threshold values, mark misplaced
       runs unsafe to apply, and show the next operator action.

    All capture and processing is RX-only — no transmit functionality.
    """
    _quiet_soapy_info_logs()
    logger.info("Starting Mimir calibration workflow")

    # ─────────────────────────────────────────────────────────────────────────
    # Step A — Parse CLI arguments and configure console logging
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
    parser.add_argument(
        "--verbose", action="store_true",
        help="Show capture details, the distance matrix, statistics and logs.",
    )
    args = parser.parse_args()
    _configure_console_logging(args.verbose)

    active_targets = (
        _build_pluto_calibration_targets()
        if args.device == "pluto"
        else CALIBRATION_TARGETS
    )
    # Pluto's two bands only ever use the whip ("1", for ADS_B retracted to
    # ~68mm) or the discone ("3", for ISM_LoRa) — the V-dipole ("2") covers
    # neither. Restricting ANTENNA_PROFILES here ensures that the capture
    # cards only offer antennas suited to Pluto's supported bands.
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
    # Step C — Select captures, or continue with fresh stored records only
    # ─────────────────────────────────────────────────────────────────────────
    stored = store.get_all_embeddings()
    freshness = _compute_band_freshness(stored, device=args.device)
    _print_startup_summary(freshness, args.device)

    all_labels = {t["label"] for t in active_targets}
    stored_labels = set(freshness.keys())
    fresh_labels = {lbl for lbl, (is_fresh, _, _) in freshness.items() if is_fresh}
    stale_labels = {lbl for lbl, (is_fresh, _, _) in freshness.items() if not is_fresh}
    missing_labels = all_labels - stored_labels

    labels_to_capture = (missing_labels | stale_labels) & all_labels
    recapture = _prompt_recapture_fresh_bands(fresh_labels & all_labels, active_targets)
    labels_to_capture |= recapture

    if not labels_to_capture:
        print(dim("  Nothing to recapture · using the stored records"))

    antenna_groups = _build_antenna_groups(labels_to_capture)
    active_groups = {k: v for k, v in antenna_groups.items() if v}

    # ─────────────────────────────────────────────────────────────────────────
    # Step D — Capture by antenna; empty active groups skip all device access
    # ─────────────────────────────────────────────────────────────────────────
    captured_count = 0
    captured_bands: set[str] = set()
    any_failed = False
    last_error = ""
    entries: list[dict] = []
    band_number = 0
    band_total = sum(len(bands) for bands in active_groups.values())

    for key, profile in active_antenna_profiles.items():
        bands = active_groups.get(key, [])
        if not bands:
            continue

        # A single-band card includes the antenna connection instruction.
        if len(bands) > 1:
            print(step(f"\nAntenna: {profile['name']} ({profile['range']})"))
            prompt = (
                f"Connect {profile['name']} now. "
                "Press ENTER when connected, or Ctrl+C to skip these bands: "
            )
            try:
                input(step(prompt))
            except KeyboardInterrupt:
                logger.info("User skipped antenna %s", profile['name'])
                print(f"\n  Skipped {profile['name']} bands: {', '.join(bands)}")
                band_number += len(bands)
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

            band_number += 1
            # Keep the antenna name and length advice on separate aligned rows.
            # A 72-column card leaves 56 value columns after the key and gap.
            reminder = profile.get("length_reminder", {}).get(label)
            card_rows = [["Antenna", profile["name"]]]
            if reminder:
                advice = (
                    "Retract it to ~68 mm before you start"
                    if label == "ADS_B" else reminder
                )
                card_rows.extend(["", line] for line in wrap(advice, 56))
            for index, warning in enumerate(_band_signal_lines(label)):
                card_rows.append(["Signal" if index == 0 else "", warning])
            card_rows.append(["Samples", f"{num_samples:,}"])
            box(
                f"[{band_number}/{band_total}] {label} · {freq_hz / 1e6:.3f} MHz",
                table(card_rows), style=step,
            )
            try:
                input(step("  Enter to start · Ctrl+C to skip this band\n"))
            except KeyboardInterrupt:
                if reminder:
                    logger.info("User skipped %s band at antenna length check", label)
                else:
                    logger.info("User skipped %s band", label)
                print(warn(f"  {WARNING} {label} skipped"))
                continue

            # Collect prior ids for this label and device without deleting.
            # Replace them only if every capture succeeds: one failed capture
            # discards this band's good pending captures and keeps the old set.
            # Other devices' records must survive the replacement.
            existing = store.get_all_embeddings()
            existing_metas = existing.get("metadatas") or []
            ids_to_delete = [
                existing["ids"][idx]
                for idx, meta in enumerate(existing_metas)
                if meta
                and meta.get("label") == label
                and meta.get("device", "hackrf") == args.device
            ]
            pending_records: list[dict] = []
            pending_entries: list[dict] = []
            band_failed = False
            with Spinner(
                label=f"capturing 1/{target['captures']}",
                total=target["captures"],
            ) as progress:
                for cap_idx in range(target["captures"]):
                    progress.update(
                        f"capturing {cap_idx + 1}/{target['captures']}",
                        cap_idx, target["captures"],
                    )
                    record_id = f"{label}_{args.device}_{cap_idx}"

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

                        pending_records.append(record)
                        pending_entries.append(
                            {"id": record_id, "label": label, "embedding": vector}
                        )

                        # Pending captures appear in verbose/piped logs only.
                        if args.verbose or not progress.active:
                            progress.write_above(ok(
                                f"  {OK} capture {cap_idx + 1}/{target['captures']} · "
                                f"peak {fingerprint['peak_power_db']:.2f} dB · "
                                f"SNR {fingerprint['snr_db']:.2f} dB"
                            ))

                    except RuntimeError as err:
                        any_failed = True
                        band_failed = True
                        last_error = str(err)
                        progress.pause()
                        logger.error(
                            "Capture failed for %s (capture %d): %s", label, cap_idx, err
                        )
                        progress.write_above(fail(
                            f"  {FAILURE} capture {cap_idx + 1}/{target['captures']} "
                            "failed"
                        ))
                        progress.write_above(dim(f"    {last_error}"))
                        # A failed band cannot replace priors; stop immediately.
                        break

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
                        progress.pause()
                        logger.info("Waiting 5 seconds before next capture")
                        progress.update(
                            "waiting 5s",
                            cap_idx + 1, target["captures"],
                        )
                        progress.resume()
                        time.sleep(5)

            snrs = [record["metadata"]["snr_db"] for record in pending_records]
            if snrs:
                print(ok(
                    f"  {OK} {len(snrs)}/{target['captures']} captured · "
                    f"SNR {min(snrs):.1f} to {max(snrs):.1f} dB"
                ))
            elif not band_failed:
                print(warn(
                    f"  {WARNING} 0/{target['captures']} captured · no SNR available"
                ))

            if len(pending_records) == target["captures"]:
                # Reused ids require deletion first; insert the batch immediately.
                if ids_to_delete:
                    store._collection.delete(ids=ids_to_delete)  # noqa: SLF001
                store.add_batch(pending_records)
                entries.extend(pending_entries)
                captured_count += len(pending_records)
                captured_bands.add(label)
                print(ok(
                    f"  {OK} Replaced {len(ids_to_delete)} prior {args.device} "
                    f"calibration record(s) for {label}"
                ))
            else:
                print(warn(
                    f"  {WARNING} Kept {len(ids_to_delete)} prior {args.device} "
                    f"calibration record(s) for {label}; no new records were "
                    "stored because not every capture succeeded. "
                    "A stale prior set is still excluded from the ladder."
                ))

    if any_failed and not captured_bands:
        failure_lines = ["No band completed its captures."]
        # --wipe removes the whole calibration collection before capturing.
        if args.wipe:
            failure_lines.extend([
                "The calibration store was wiped at the start of this run.",
                "Earlier calibration records are gone; recapture is needed.",
            ])
        else:
            failure_lines.append("Stored records were left untouched.")
        box("No new captures", failure_lines, style=fail)
        next_step(
            "check the Pluto is plugged in (iio_info should list it), "
            "then run again"
            if args.device == "pluto" else
            "check the HackRF is plugged in (hackrf_info should list it), "
            "then run again"
        )
        raise SystemExit(1)

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
    distance_pairs = _compute_pairwise_distances(entries, store)

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
    # Print the optional matrix; its colouring thresholds are always computed.
    # ─────────────────────────────────────────────────────────────────────────
    if args.verbose:
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
    if args.verbose:
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

    if args.verbose:
        print("\nComputed statistics:")
        print(f"  same_type_pairs:       {len(same_type_pairs)} pairs")
        print(f"  cross_type_pairs:      {len(cross_type_pairs)} pairs")
        print(f"  noise_floor_pairs:     {len(noise_pairs)} pairs")
        print()
        if same_type_spread < cross_type_min / SEPARABILITY_FACTOR:
            _st_colour = ok
        elif same_type_spread < cross_type_min:
            _st_colour = warn
        else:
            _st_colour = fail
        print(
            "Same-type spread (p90):   "
            + _st_colour(f"{same_type_spread:.4f}")
        )
        if cross_type_min > SEPARABILITY_FACTOR * same_type_spread:
            _ct_colour = ok
        elif cross_type_min > same_type_spread:
            _ct_colour = warn
        else:
            _ct_colour = fail
        print(
            "Cross-type min distance:  " + _ct_colour(f"{cross_type_min:.4f}")
        )
        if cross_type_min_pair:
            print(
                f"                          ({cross_type_min_pair[0]} "
                f"vs {cross_type_min_pair[1]})"
            )
        if noise_min > cross_type_min:
            _nf_colour = ok
        elif noise_min > same_type_spread:
            _nf_colour = warn
        else:
            _nf_colour = fail
        print("Noise floor min distance: " + _nf_colour(f"{noise_min:.4f}"))
        print()
        print("-" * 70)
    # Report suspicious neighbours without changing the derived ladder.
    misplaced = _find_misplaced_captures(entries, distance_pairs)
    misplaced_labels = {capture["label"] for capture in misplaced}
    result_rows = []
    for label in sorted(set(entry_labels.values())):
        band_entries = [entry for entry in entries if entry["label"] == label]
        band_distances = [
            distance for a_id, b_id, distance in distance_pairs
            if entry_labels[a_id] == entry_labels[b_id] == label
        ]
        spread = (
            float(np.percentile(band_distances, 90)) if band_distances else 0.0
        )
        if len(band_entries) == 1:
            status = "only one capture, not checked"
        elif label in misplaced_labels:
            status = warn(f"{WARNING} captures disagree")
        elif band_distances:
            status = ok(f"{OK} consistent")
        else:
            status = warn(f"{WARNING} distances unavailable, not checked")
        result_rows.append([
            label, str(len(band_entries)),
            f"{spread:.4f}" if band_distances else "—", status,
        ])
    result_lines = table(
        result_rows, headers=["Band", "Captures", "Spread", "Status"]
    )
    result_lines.append("")
    for capture in misplaced:
        result_lines.append(warn(
            f"{WARNING} {capture['id']} looks like "
            f"{capture['nearest_other_label']} "
            f"({capture['other_distance']:.3f} away, "
            f"own band {capture['own_distance']:.3f})"
        ))
    if not derived["ok"]:
        result_lines.append(fail(f"{FAILURE} failed"))
    elif misplaced:
        result_lines.append(warn(
            f"{WARNING} usable but affected by misplaced captures"
        ))
    else:
        result_lines.append(ok(f"{OK} usable"))
    box("Results", result_lines)

    if not derived["ok"]:
        box("Calibration failed · thresholds not paste-ready", [
            derived["reason"],
            "",
            "Any thresholds derived from this run would collapse the "
            "strong/possible/different/novel bands into a single bucket.",
            "",
            "REMEDIATION: recapture the affected band(s) with a live signal "
            "present. Burst bands (ADS-B, ACARS, AIS) need aircraft or vessels "
            "in range — check flightradar24 / marinetraffic before recapturing.",
            "Do NOT paste any thresholds from this run into llm/classifier.py.",
        ], style=fail)
        next_step("recapture with a live signal present")
        logger.warning("Calibration unusable (%s); thresholds not emitted.",
                       "near-noise" if cross_type_min < CROSS_TYPE_MIN_FLOOR else "overlap")
        raise SystemExit(1)
    threshold_lines = table([
        ["STRONG_MATCH", ok(f"{STRONG_MATCH:.3f}"), "same type, strong match"],
        ["POSSIBLE_MATCH", warn(f"{POSSIBLE_MATCH:.3f}"), "borderline"],
        ["DIFFERENT_TYPE", ok(f"{DIFFERENT_TYPE:.3f}"), ""],
        ["NOVEL_SIGNAL", ok(f"{NOVEL_SIGNAL:.3f}"), "above this counts as unseen"],
    ])
    if misplaced:
        box(
            "Suggested thresholds · not safe to apply", threshold_lines,
            style=warn,
        )
        next_step(
            f"recapture {', '.join(sorted(misplaced_labels))}. "
            "Leave llm/classifier.py unchanged."
        )
    else:
        threshold_lines.extend([
            "",
            dim("llm/classifier.py: _DISTANCE_SCALE_REFERENCE"),
            dim("and the _build_user_prompt() threshold block."),
        ])
        box("Suggested thresholds", threshold_lines, style=ok)
        next_step("copy the values into llm/classifier.py")

    logger.info("Calibration complete. %d vectors stored, thresholds computed.", captured_count)


if __name__ == "__main__":
    main()
