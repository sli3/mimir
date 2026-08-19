"""
replay_capture.py — Replay a saved SigMF capture through the fingerprint pipeline

Offline calibration/diagnostic tool. Reads a SigMF capture already on
disk (one-shot Phase 66 "mimir:fingerprint" or Record-mode Phase 68
"mimir:fingerprint_sequence"), recomputes the spectral fingerprint of the
recorded samples under TODAY's BAND_PROFILES thresholds, and reports
field-by-field match/mismatch against the fingerprint saved at capture
time. NO hardware is touched — every sample comes from the .sigmf-data
file. Mismatches are findings, not failures: the tool exits 0 with the
full comparison printed. File-level problems (missing/malformed file, no
fingerprint field, resource-cap breach) are hard errors: exit 1.

Usage:
    python tools/replay_capture.py data/captures/capture_98000000hz_20260819_120000.sigmf-meta
    python tools/replay_capture.py path/to/capture.sigmf-data --tolerance-db 0.25
    python tools/replay_capture.py path/to/capture.sigmf-meta --json result.json

Legal: Receive-only. Radiocommunications Act 1992 (Cth).
       No transmission. Jurisdiction: AU/SA. Authority: ACMA.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from core.pipeline.replay import ReplayBusyError, ReplayFileError, replay_capture

logger = logging.getLogger(__name__)

# ANSI colour helpers for terminal output (same convention as the other
# tools: green = match, red = mismatch/error).
ANSI_GREEN = "\033[92m"
ANSI_YELLOW = "\033[93m"
ANSI_RED = "\033[91m"
ANSI_RESET = "\033[0m"


def _colour(text: str, code: str) -> str:
    """Wrap text in an ANSI colour code."""
    return f"{code}{text}{ANSI_RESET}"


def _parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Replay a saved SigMF capture through the fingerprint pipeline "
            "under today's BAND_PROFILES and compare against the saved "
            "fingerprint. Offline only — no hardware is touched."
        ),
    )
    parser.add_argument(
        "path",
        type=Path,
        help="Path to .sigmf-meta (or .sigmf-data) file.",
    )
    parser.add_argument(
        "--json",
        type=Path,
        default=None,
        help="Also write the structured result to this path as JSON.",
    )
    parser.add_argument(
        "--tolerance-db",
        type=float,
        default=0.1,
        help=(
            "Match tolerance in dB for snr_db/peak_power_db/noise_floor_db "
            "(default: 0.1)."
        ),
    )
    return parser.parse_args()


def _print_chunk(index: int, chunk: dict) -> None:
    """Print one chunk's comparison line, colour-coded on snr_db."""
    snr = chunk["comparison"]["field_results"]["snr_db"]
    verdict = _colour("MATCH", ANSI_GREEN) if snr["match"] else _colour(
        "MISMATCH", ANSI_RED
    )
    location = ""
    if "sample_start" in chunk:
        location = (
            f" [sample_start={chunk['sample_start']} "
            f"t={chunk['timestamp_sec']:.3f}s]"
        )
    print(
        f"chunk {index}{location}: snr_db saved={snr['saved']} "
        f"replayed={snr['replayed']} (delta={snr['delta_db']:+.3f} dB) "
        f"{verdict}"
    )
    if not chunk["comparison"]["all_match"]:
        for field, result in chunk["comparison"]["field_results"].items():
            if not result["match"]:
                print(
                    _colour(
                        f"    {field}: saved={result['saved']} "
                        f"replayed={result['replayed']}",
                        ANSI_YELLOW,
                    )
                )


def main() -> None:
    """CLI entry point for the replay_capture tool.

    Reads a saved SigMF capture (one-shot "mimir:fingerprint" or Record-mode
    "mimir:fingerprint_sequence"), recomputes its spectral fingerprint under
    TODAY's BAND_PROFILES thresholds via core.pipeline.replay.replay_capture(),
    and prints a field-by-field match/mismatch comparison.

    Device-profile resolution (HIGH-01): the capture's mimir:device_profile
    field determines which band profile is used for replay. The output shows
    band_resolution.profile_source as "pluto_overlay" when PLUTO_BAND_PROFILES
    were applied, otherwise "hackrf_base".

    Error handling (MED-01): ReplayFileError (malformed file, no fingerprint,
    resource-cap breach, unresolvable band) maps to exit 1 with a red error
    message. All sigmf-library failures are already wrapped as ReplayFileError
    by replay_capture().

    Validation (MED-02, MED-03): Record-mode fingerprint_sequence entries are
    validated before replay, requiring sample_count >= 1 and float-coercible
    timestamp_sec. Any violation raises ReplayFileError and exits with error.

    Locking: REPLAY_LOCK is acquired inside replay_capture(). The CLI uses
    wait=True (blocking contention), which is correct for single-shot usage.
    The API route uses wait=False for fast-fail 503 responses.
    """
    args = _parse_args()

    # Locking happens inside replay_capture() — callers only choose the
    # contention behaviour via wait. Single-shot CLI usage means contention
    # is negligible, and waiting (wait=True) is the correct behaviour (the
    # API route is the path that must fail fast with 503 instead).
    try:
        result = replay_capture(args.path, tolerance_db=args.tolerance_db, wait=True)
    except ReplayFileError as exc:
        print(_colour(f"ERROR: {exc}", ANSI_RED))
        sys.exit(1)
    except ReplayBusyError as exc:
        # Effectively unreachable with wait=True; defensive only.
        print(_colour(f"ERROR: another replay is in progress: {exc}", ANSI_RED))
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nInterrupted — replay abandoned before completion.")
        sys.exit(130)

    meta = result["file_metadata"]
    band = result["band_resolution"]
    print(f"File:      {meta['path']}")
    print(f"Frequency: {meta['core_frequency_hz']:.0f} Hz  "
          f"Sample rate: {meta['core_sample_rate_hz']:.0f} Hz")
    print(f"Field:     {meta['fingerprint_field']}")
    print(f"Band:      {band['band_key']} ({band['match']} match, "
          f"centre {band['band_center_freq_hz']} Hz)")
    print()
    for index, chunk in enumerate(result["per_chunk_results"]):
        _print_chunk(index, chunk)
    print()
    summary = result["summary"]
    print(
        f"{summary['matched_chunks']}/{summary['total_chunks']} chunks "
        f"matched within {args.tolerance_db} dB tolerance"
    )

    if args.json is not None:
        args.json.write_text(json.dumps(result, indent=2))
        print(f"Structured result written to {args.json}")


if __name__ == "__main__":
    main()


# ── DEFERRED ITEMS (from Phase 70 dual code review) ───────────────────────────────
# These items are documented technical debt or follow-up work identified during the
# Phase 70 finalise review. They are not blocking issues but should be addressed in
# future phases.

# LOW-03: tolerance_db unvalidated for NaN/negative/bool at both CLI and route entry
#     points — add math.isfinite(tolerance_db) and tolerance_db >= 0 check, own phase.
# LOW-04: NaN serialisation is non-strict JSON; +-inf not covered by the NaN policy
#     — sanitize non-finite values to null at the result boundary, own phase.
# LOW-05: int(core_freq_hz) truncation and OverflowError risk for infinite core:frequency
#     — rides along with the MED-01 wrapper (already fixed) but the int() cast itself
#     wasn't hardened.
# ADVISORY: REPLAY_LOCK is process-wide only; the CLI and the API route run as
#     separate processes, so they can run concurrently despite the lock — one-sentence
#     docstring note recommended.
# ADVISORY: large replay runs execute inside the live scan.py process; NumPy releases
#     the GIL during FFTs but scan-cycle latency may rise during a big replay — no
#     action needed unless operators report sluggishness; os.nice is the eventual answer
#     if so.
# ADVISORY: MAX_ONE_SHOT_SAMPLES = 50M is generous (~380x a legitimate one-shot capture);
#     a tighter cap (2-5M) would still clear legitimate files 15-40x over — defensible
#     as-is, no action needed.
# ADVISORY: consider adding a delta (Hz / bins) on the exact-match fields
#     (peak_freq_hz, bandwidth_hz, occupied_bins) for a future "diff against historical
#     threshold" report — own phase.
# ───────────────────────────────────────────────────────────────────────────────────
