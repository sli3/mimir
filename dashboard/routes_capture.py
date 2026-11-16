"""Provide manual capture and recording control routes.

Legal: Receive-only. Radiocommunications Act 1992 (Cth).
       No transmission. Jurisdiction: AU/SA. Authority: ACMA.
"""

from flask import jsonify

import dashboard.server as _server


@_server.app.route("/api/capture", methods=["POST"])
def api_capture():
    """Manual capture button. Fires a SigMF save of the samples the scan
    loop is already reading this cycle (no second device open — see
    ScanRunner.capture_now()'s docstring and the [62] session's
    timing-integrity rationale for reusing in-flight samples rather than
    a separately-timed grab). Always returns HTTP 200 with a structured
    status field, mirroring /api/radar/reason's "never 500 the user"
    convention — capture failures are expected/handleable, not server
    errors.

    Output format:
    {
        "status": "ok" | "error" | "timeout" | "scanner_unavailable",
        "file": str,           — present only on "ok"
        "fingerprint": dict,   — present only on "ok" (the seven
                                  _FINGERPRINT_METADATA_KEYS fields)
        "is_burst": bool,      — present only on "ok". Top-level sibling
                                  of `fingerprint`. Deliberately NOT
                                  persisted in the SigMF metadata
                                  because _FINGERPRINT_METADATA_KEYS
                                  excludes it (it describes the burst
                                  detection pipeline, not the captured
                                  spectrum). The dashboard verdict uses
                                  this key to override the
                                  occupied_bins fallback for narrow
                                  bursts; the saved file's mimir:fingerprint
                                  stays at the seven measurement fields.
        "cause": str,          — present only on "error"
    }

    Response / file asymmetry: the `is_burst` key appears in this HTTP
    response but is NEVER written to the saved .sigmf-meta file. The
    asymmetry is intentional — the seven-key tuple in core/pipeline/
    capture.py is the source of truth for what survives on disk, and
    expanding it would re-flow Phase 45-46 burst metric decisions onto
    every offline replay path. The response shape is the right place
    for a transient detection flag consumed only by the live UI.

    Implementation notes:
    - RECEIVE-ONLY. No RF transmission or hardware control. The endpoint
      signals the existing scan loop to file-write samples it is already
      reading.
    - Legal constraint: Radiocommunications Act 1992 (Cth), AU/SA
      jurisdiction, ACMA authority. Every recording carries the
      legal provenance note baked into save_capture()'s SigMF metadata.
    """
    if _server._scanner_ref is None:
        return jsonify({"status": "scanner_unavailable"}), 200
    result = _server._scanner_ref.capture_now()
    return jsonify(result), 200


@_server.app.route("/api/record/start", methods=["POST"])
def api_record_start():
    """Operator "Record" button: begin an in-memory recording (Phase 68).

    Tells the scan loop to start appending every cycle's already-read
    samples to an in-memory accumulator. Nothing touches disk on this
    call — the buffer lives in RAM until POST /api/record/stop
    concatenates it and writes ONE SigMF file via save_recording().
    Fully separate mechanism from /api/capture: separate state, separate
    scan-loop code path, no shared fields.

    There is deliberately NO backend duration cap and NO auto-stop: the
    recording runs until the operator stops it. The 60-second warning is
    a frontend-only display concern; this endpoint has no awareness of
    elapsed time.

    Always returns HTTP 200 with a structured status field, mirroring
    /api/capture's "never 500 the user" convention.

    Output format:
    {
        "status": "ok" | "already_recording" | "scanner_unavailable",
    }

    - "ok"                — recording has begun; accumulator state reset.
    - "already_recording" — a recording is in progress and was left
                            untouched (a silent reset would throw away
                            samples the operator believes are still
                            being captured).
    - "scanner_unavailable" — the ScanRunner is not running.

    Implementation notes:
    - RECEIVE-ONLY. No RF transmission or hardware control. The endpoint
      flips a flag the existing scan loop reads; the loop keeps using
      samples it is already reading.
    - Legal constraint: Radiocommunications Act 1992 (Cth), AU/SA
      jurisdiction, ACMA authority. The eventual recording carries the
      legal provenance note baked into save_recording()'s SigMF
      metadata.
    """
    if _server._scanner_ref is None:
        return jsonify({"status": "scanner_unavailable"}), 200
    return jsonify(_server._scanner_ref.start_recording()), 200


@_server.app.route("/api/record/stop", methods=["POST"])
def api_record_stop():
    """Operator "Record" button: stop the recording and write the file
    (Phase 68).

    Tells the scan loop to stop accumulating, concatenates the in-memory
    sample buffer into one array, and writes ONE SigMF file via
    save_recording() with a per-cycle "mimir:fingerprint_sequence"
    metadata field (each entry: the seven _FINGERPRINT_METADATA_KEYS
    measurement fields plus sample_start / sample_count / timestamp_sec
    for replay slicing). The singular "mimir:fingerprint" field is never
    written by this path — the two fields are mutually exclusive by
    construction.

    The response blocks briefly for the concatenate plus file write,
    which is bounded and fast.

    Always returns HTTP 200 with a structured status field, mirroring
    /api/capture's "never 500 the user" convention — a save failure
    (e.g. disk full) is an expected/handleable outcome, not a server
    error.

    Output format:
    {
        "status": "ok" | "error" | "not_recording" | "scanner_unavailable",
        "file": str,           — present only on "ok" (path to the
                                  .sigmf-meta file)
        "duration_sec": float, — present only on "ok" (total samples /
                                  sample rate)
        "cycle_count": int,    — present only on "ok" (scan cycles
                                  captured)
        "cause": str,          — present only on "error"
    }

    Implementation notes:
    - RECEIVE-ONLY. No RF transmission or hardware control. The endpoint
      writes a file of already-received samples.
    - Legal constraint: Radiocommunications Act 1992 (Cth), AU/SA
      jurisdiction, ACMA authority. Every recording carries the legal
      provenance note baked into save_recording()'s SigMF metadata.
    - On "error" the scanner-side accumulator state is still fully
      reset, so a subsequent /api/record/start begins clean.
    """
    if _server._scanner_ref is None:
        return jsonify({"status": "scanner_unavailable"}), 200
    return jsonify(_server._scanner_ref.stop_recording()), 200
