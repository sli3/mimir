"""Provide offline capture replay and metadata listing routes.

Legal: Receive-only. Radiocommunications Act 1992 (Cth).
       No transmission. Jurisdiction: AU/SA. Authority: ACMA.
"""

import logging
import math

import sigmf
from flask import jsonify, request

from core.pipeline.replay import ReplayBusyError, ReplayFileError, replay_capture
import dashboard.server as _server
from dashboard.capture_listing import _capture_sort_key, _parse_capture_meta_entry

logger = logging.getLogger(__name__)


@_server.app.route("/api/replay", methods=["POST"])
def api_replay():
    """Replay a saved SigMF capture through the fingerprint pipeline.

    Purpose: offline calibration/diagnostic counterpart to /api/capture
    and /api/record/*. Reads a capture ALREADY ON DISK (one-shot
    "mimir:fingerprint" or Record-mode "mimir:fingerprint_sequence"),
    recomputes its spectral fingerprint under TODAY's BAND_PROFILES
    thresholds via core.pipeline.replay.replay_capture(), and returns the
    field-by-field match/mismatch comparison. NO hardware is touched —
    every sample comes from the .sigmf-data file (SigMFFile.read_samples
    is the SigMF file reader, not the hardware method of the same name).

    Device-profile resolution (HIGH-01): the capture's mimir:device_profile
    field determines which band profile is used for replay. The response's
    band_resolution.profile_source field indicates "pluto_overlay" when
    PLUTO_BAND_PROFILES were applied (e.g. for Pluto ADS-B with calibrated
    10.0 dB signal_threshold_db), otherwise "hackrf_base".

    Input format: POST with a JSON body:
    {
        "path": str,              — required. Relative to data/captures/
                                    (absolute paths and traversal are
                                    rejected; see containment below).
        "tolerance_db": number    — optional, default 0.1. Match
                                    tolerance for the dB-scale fields.
    }

    Output format on success: HTTP 200 with the structured result from
    replay_capture() — file_metadata, band_resolution (band key plus
    whether the frequency resolved "exact" or "nearest", so a 915.825 MHz
    recording reports "nearest" against the 915.000 MHz ism profile),
    per_chunk_results (replayed fingerprint, saved fingerprint, per-field
    comparison), and a matched/mismatched summary. The response carries
    DERIVED MEASUREMENTS ONLY — never raw IQ samples.
    Non-finite floats are null; spectral_flatness comparisons include
    delta_format="exponential" for client delta formatting.

    Mismatches are NOT failures: a capture that no longer matches under
    current thresholds is a valid finding and returns 200 like any other
    completed replay.

    Error format: non-2xx with a stable shape
    {"error": "<short_key>", "detail": "<more info>"} — a deliberate
    departure from the "always 200 + status" convention of /api/capture,
    acceptable here because file failures are client errors, not scanner
    states:
        400 invalid_body             — body was not a JSON object
        400 invalid_path             — path missing / not a string
        400 path_resolve_failed      — path could not be resolved
        400 path_outside_captures_dir — traversal / absolute path escaped
                                       data/captures/
        400 not_a_sigmf_meta_file    — suffix is not .sigmf-meta
        400 invalid_tolerance        — tolerance_db not coercible to float
        400 tolerance_out_of_range   — tolerance_db is NaN, infinite,
                                       negative, or a bool
        404 file_not_found           — no such file inside data/captures/
        400 replay_failed            — ReplayFileError (malformed file,
                                       no fingerprint field, resource-cap
                                       breach, unresolvable band; all
                                       sigmf-library errors are wrapped)
        500 internal_error           — unexpected OSError/ValueError/
                                       KeyError inside the replay
        503 busy                     — another replay is in progress

    Path containment: the caller-supplied path is joined onto
    _REPLAY_CAPTURES_DIR (Path("data/captures").resolve() — the same CWD
    assumption capture.py makes for its default output_dir), resolved
    (which follows symlinks), then required to satisfy is_relative_to()
    the captures dir. resolve() + is_relative_to() defeats both ../
    traversal and planted symlinks pointing outside the directory.

    Resource guards: only one replay runs at a time process-wide
    (REPLAY_LOCK, non-blocking here so concurrent callers get 503 rather
    than queuing behind a 488 MB file), and replay_capture() enforces its
    own per-file caps (MAX_ONE_SHOT_SAMPLES on whole-file reads,
    MAX_SEQUENCE_ENTRIES plus slicing-field validation on Record-mode
    sequences, including sample_count >= 1 and float-coercible
    timestamp_sec).

    Implementation notes:
    - RECEIVE-ONLY. No RF transmission or hardware control. The endpoint
      reads files the scanner already wrote; it never opens a device.
    - Fully stateless: no ScanRunner, no shared_state mutation, no
      SocketIO emission.
    - The server binds locally by default (core/config/loader.py), so
      this endpoint is not network-exposed in the standard deployment.
    - Legal constraint: Radiocommunications Act 1992 (Cth), AU/SA
      jurisdiction, ACMA authority. Replaying a passive-RX recording
      from disk is receive-only analysis.
    """
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(
            {"error": "invalid_body", "detail": "JSON object required"}
        ), 400
    user_path = payload.get("path")
    if not isinstance(user_path, str) or not user_path:
        return jsonify(
            {
                "error": "invalid_path",
                "detail": "path must be a non-empty string",
            }
        ), 400
    try:
        resolved = (_server._REPLAY_CAPTURES_DIR / user_path).resolve()
    except (OSError, RuntimeError) as exc:
        return jsonify(
            {"error": "path_resolve_failed", "detail": str(exc)}
        ), 400
    if not resolved.is_relative_to(_server._REPLAY_CAPTURES_DIR):
        return jsonify(
            {
                "error": "path_outside_captures_dir",
                "detail": "path must resolve inside data/captures/",
            }
        ), 400
    if resolved.suffix != ".sigmf-meta":
        return jsonify(
            {
                "error": "not_a_sigmf_meta_file",
                "detail": "path must end in .sigmf-meta",
            }
        ), 400
    if not resolved.is_file():
        return jsonify(
            {"error": "file_not_found", "detail": str(resolved.name)}
        ), 404
    # tolerance_db must be a real number: not a bool (float(True)==1.0
    # would silently pass the isfinite/>=0 check below), not NaN or
    # +-inf, and not negative. The original invalid_tolerance path
    # (non-numeric input) is preserved byte-identical; this ADDS two
    # distinct guards for the cases that float() coerces without
    # raising. See LOW-03 in AGENTS.md.
    raw_tolerance = payload.get("tolerance_db", 0.1)
    if isinstance(raw_tolerance, bool):
        # bool must be rejected BEFORE float() — float(True) is 1.0
        return jsonify(
            {
                "error": "tolerance_out_of_range",
                "detail": "tolerance_db must be finite and non-negative",
            }
        ), 400
    try:
        tolerance_db = float(raw_tolerance)
    except (TypeError, ValueError):
        return jsonify(
            {
                "error": "invalid_tolerance",
                "detail": "tolerance_db must be a number",
            }
        ), 400
    if not math.isfinite(tolerance_db) or tolerance_db < 0:
        return jsonify(
            {
                "error": "tolerance_out_of_range",
                "detail": "tolerance_db must be finite and non-negative",
            }
        ), 400

    # Locking happens inside replay_capture() — callers only choose the
    # contention behaviour via wait. wait=False fails fast with
    # ReplayBusyError, mapped here to a structured 503.
    try:
        result = replay_capture(resolved, tolerance_db=tolerance_db, wait=False)
    except ReplayBusyError:
        return jsonify(
            {"error": "busy", "detail": "another replay is in progress"}
        ), 503
    except ReplayFileError as exc:
        return jsonify({"error": "replay_failed", "detail": str(exc)}), 400
    except sigmf.error.SigMFError as exc:
        # Defence-in-depth (MED-01): replay_capture() already converts
        # sigmf-library failures (SigMFAccessError / SigMFFileError on a
        # malformed file) to ReplayFileError; this clause guards any path
        # that escapes that conversion. A sigmf error always means a bad
        # file, so it maps to the same 400 replay_failed response rather
        # than the 500 internal_error fallthrough below.
        return jsonify({"error": "replay_failed", "detail": str(exc)}), 400
    except (OSError, ValueError, KeyError) as exc:
        logger.exception("Unexpected replay error for %s", resolved)
        return jsonify({"error": "internal_error", "detail": str(exc)}), 500
    return jsonify(result), 200


@_server.app.route("/api/captures", methods=["GET"])
def api_captures():
    """List saved SigMF captures in data/captures/.

    Purpose: read-only directory peek for the /replay page picker.
    Returns a lightweight list of every .sigmf-meta file in the
    captures directory, with just enough metadata to let the operator
    choose one. The paired .sigmf-data files are NEVER opened or read.

    Per-file metadata is parsed with stdlib json.load() rather than
    sigmf.fromfile() because SigMFFile may eagerly inspect the sibling
    .sigmf-data file (size, checksum), and this endpoint is intended to
    be a fast peek-only listing.

    Output format on success: HTTP 200 with
    {
        "captures": [
            {
                "filename": str,
                "mode": "oneshot" | "record" | "unknown",
                "chunk_count": int,
                "core_frequency_hz": float | null,
                "device": str | null,
                "timestamp": "YYYY-MM-DDTHH:MM:SS" | null
            },
            ...
        ]
    }

    Mode detection:
        - "oneshot": file contains a dict "mimir:fingerprint" global field
                     (single scan cycle). chunk_count = 1.
        - "record": file contains "mimir:fingerprint_sequence" global
                    field containing a list within MAX_SEQUENCE_ENTRIES.
                    chunk_count =
                    len(sequence).
        - "unknown": neither field present, or file is malformed.
                     chunk_count = 0.

    Malformed files are surfaced as "unknown" entries with an extra
    "error" key; they do NOT abort the whole listing. Oversized sequences,
    non-list sequences and non-dict one-shot fingerprints stay "unknown"
    with chunk_count = 0. Non-finite core:frequency values are null.

    Sort order: descending by parsed timestamp; entries without a
    parseable timestamp sort after all dated entries. Filename provides
    a stable secondary sort.

    Error format: non-2xx with the same stable shape as /api/replay:
        {"error": "internal_error", "detail": "..."}

    Path containment: the search is confined to _REPLAY_CAPTURES_DIR.
    Although no caller-supplied path is used here, is_relative_to()
    is still applied as defence-in-depth in case the constant is ever
    pointed at a symlinked location.

    Implementation notes:
    - RECEIVE-ONLY. No RF hardware, no scanner interaction, no sample
      data access.
    - json.load() keeps the operation on the metadata file only; the
      .sigmf-data sibling is never touched.
    - read_samples() is the hardware SDR method and is NOT called here.
    - core.device.* is not imported by this route.
    - Missing directory returns 200 with an empty captures list.
    """
    captures = []
    try:
        if not _server._REPLAY_CAPTURES_DIR.exists():
            return jsonify({"captures": captures}), 200

        for entry in _server._REPLAY_CAPTURES_DIR.iterdir():
            if not entry.is_file() or entry.suffix != ".sigmf-meta":
                continue
            # Defence-in-depth: skip anything that resolves outside the
            # captures dir even though we built the path ourselves.
            try:
                resolved = entry.resolve()
                if not resolved.is_relative_to(_server._REPLAY_CAPTURES_DIR):
                    continue
            except (OSError, RuntimeError):
                continue

            parsed = _parse_capture_meta_entry(entry)
            captures.append(parsed)

        captures.sort(key=_capture_sort_key, reverse=True)
    except Exception as exc:  # pragma: no cover - defensive top-level guard
        logger.exception("Unexpected error listing captures in %s", _server._REPLAY_CAPTURES_DIR)
        return jsonify({"error": "internal_error", "detail": str(exc)}), 500

    return jsonify({"captures": captures}), 200


# ── DEFERRED ITEMS (from Phase 70 dual code review) ───────────────────────────────
# These items are documented technical debt or follow-up work identified during the
# Phase 70 finalise review. They are not blocking issues but should be addressed in
# future phases.

# LOW-04: NaN serialisation is non-strict JSON; +-inf not covered by the NaN policy
#     — sanitize non-finite values to null at the result boundary, own phase.
# ADVISORY: REPLAY_LOCK is process-wide only; the CLI and the API route run as
#     separate processes, so they can run concurrently despite the lock — one-sentence
#     docstring note recommended.
# ADVISORY: the 503 fast-fail path was verified to hold no worker thread; the route is
#     fully stateless — clean, no action needed.
# ADVISORY: MAX_ONE_SHOT_SAMPLES = 50M is generous (~380x a legitimate one-shot capture);
#     a tighter cap (2-5M) would still clear legitimate files 15-40x over — defensible
#     as-is, no action needed.
# ───────────────────────────────────────────────────────────────────────────────────
