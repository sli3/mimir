"""
replay.py — Offline replay of SigMF captures through the fingerprint pipeline

Legal: Receive-only. Radiocommunications Act 1992 (Cth).
       No transmission. Jurisdiction: AU/SA. Authority: ACMA.

WHAT THIS MODULE DOES
---------------------
Replays a saved SigMF capture (.sigmf-meta / .sigmf-data pair) through
the existing spectral fingerprinting pipeline (compute_psd then
fingerprint_spectrum), parameterised by TODAY's BAND_PROFILES thresholds,
and compares the replayed measurement against the fingerprint recorded in
the file at capture time. This is a calibration/diagnostic capability: it
answers "would this capture measure the same under the current band
configuration?" without touching any hardware.

Mimir produces two flavours of SigMF capture, distinguished by which
custom global field is present (mutually exclusive by construction —
see core/pipeline/capture.py):

  - One-shot (Phase 66, capture_now()): a singular "mimir:fingerprint"
    global field carrying the seven _FINGERPRINT_METADATA_KEYS
    measurement fields. The whole file is one scan cycle.
  - Record-mode (Phase 68, start/stop_recording()): a
    "mimir:fingerprint_sequence" list of per-cycle dicts, each the seven
    measurement keys plus sample_start / sample_count / timestamp_sec.
    Each entry's samples occupy
    [sample_start, sample_start + sample_count) of the .sigmf-data file.

IMPORTANT NAME COLLISION: SigMFFile.read_samples() is the SigMF FILE
reader — it reads complex64 samples from the .sigmf-data file on disk.
It is NOT the hardware method of the same name on HackRFReceiver /
PlutoReceiver. This module never opens a device; every sample it
processes comes from a file already on disk.

HARDWARE ISOLATION: this module has no direct core.device.* import.
The transitive core.pipeline.capture dependency is constants-only
(the seven _FINGERPRINT_METADATA_KEYS); this module never instantiates
or opens a device. TX remains blocked by HardwareTransmitError in
core/legal/compliance_guard.py.

RESOURCE GUARDS (security-analyst conditions, HIGH severity): replaying
a large Record-mode file reproduces its capture-time memory footprint
(the Phase 68 live-verified worst case was 488.6 MB / 466 cycles).
Three guards bound that:
  1. REPLAY_LOCK — one replay at a time, process-wide. A plain
     threading.Lock (non-reentrant by design): replay_capture() acquires
     it around its whole body. Callers choose their contention
     behaviour via the wait parameter — the CLI blocks (wait=True,
     the default), the /api/replay route fails fast (wait=False) and
     maps the resulting ReplayBusyError to a structured 503. A
     reentrant lock was considered and rejected: with an RLock, a
     same-thread holder would silently pass the route's busy check,
     weakening exactly the guarantee this lock exists to enforce.
  2. MAX_ONE_SHOT_SAMPLES — cap on whole-file reads for the one-shot
     path. One-shot files are single scan cycles (~1 MB); a 50 MB cap
     (50M complex64 samples = 400 MB cf32... see note below) stops a
     mislabelled Record-mode file being slurped whole.
  3. Record-mode sequence validation BEFORE iterating: entry count cap,
     per-entry validated slicing fields (non-negative integer
     sample_start, positive integer sample_count, float-coercible
     timestamp_sec), and sample_start + sample_count must not exceed
     the file-implied total sample count derived from core:datatype and
     the .sigmf-data size.

NOTE on MAX_ONE_SHOT_SAMPLES units: the constant counts SAMPLES, not
bytes. 50_000_000 complex64 samples is 400 MB of cf32 data — far above
any legitimate one-shot capture (~131k samples / 1 MB), so the cap only
ever fires on genuinely mislabelled or adversarial files.
"""

from __future__ import annotations

import logging
import math
import threading
from pathlib import Path
from typing import Any

import sigmf
from sigmf import SigMFFile
from sigmf.error import SigMFFileError

from core.pipeline.fft import compute_psd
from core.pipeline.features import fingerprint_spectrum
from core.pipeline.capture import _FINGERPRINT_METADATA_KEYS as SAVED_MEASUREMENT_KEYS
from dashboard.shared_state import (
    BAND_PROFILES,
    PLUTO_BAND_PROFILES,
    band_key_for_freq,
    resolve_band_profile,
)

logger = logging.getLogger(__name__)


class ReplayFileError(Exception):
    """A file-level replay failure: the caller pointed at a file that is
    missing, malformed, not a SigMF recording, structurally inconsistent
    (bad fingerprint_sequence slicing fields), or outside the resource
    caps. Maps to HTTP 400 at the /api/replay route — the client named a
    bad file, nothing internal broke."""


class ReplayBusyError(Exception):
    """Another replay already holds REPLAY_LOCK. Raised only when
    replay_capture() is called with wait=False (the /api/replay route,
    which maps this to a structured 503). CLI callers use the default
    wait=True and simply block until the lock is free."""


# One replay at a time, process-wide. Plain threading.Lock — see the
# module docstring for why reentrancy was deliberately rejected.
REPLAY_LOCK = threading.Lock()

# Resource caps (HIGH-severity security conditions).
MAX_ONE_SHOT_SAMPLES = 50_000_000  # one-shot whole-file read cap (samples)
MAX_SEQUENCE_ENTRIES = 10_000      # Record-mode fingerprint_sequence cap
                                   # (real worst case: 466, Phase 68)

# Comparison policy per field (security-analyst condition 4):
#   - _DB_FIELDS: compared within tolerance_db (default 0.1 dB).
#   - peak_freq_hz: exact (bin-derived frequency).
#   - bandwidth_hz: float-exact. It IS a float
#     (float(occupied_bins * hz_per_bin), features.py) — do NOT cast.
#   - occupied_bins: integer-exact (true bin count).
#   - spectral_flatness: Wiener-entropy float log-sum; exact equality can
#     flap across numpy builds, so a small absolute tolerance applies.
_DB_FIELDS = ("peak_power_db", "noise_floor_db", "snr_db")
_FLATNESS_TOLERANCE = 1e-9

# NaN POLICY: noise-only / degenerate captures can produce NaN values,
# and NaN != NaN per IEEE 754. NaN-vs-NaN is treated as a MATCH (both
# sides degenerate — no semantic difference). Finite-vs-NaN is a
# mismatch. Mismatch flags otherwise fire only on finite-vs-finite
# deltas exceeding the field's tolerance.


def _values_match(saved: Any, replayed: Any, tolerance: float) -> bool:
    """Compare two numeric values under the module NaN policy.

    NaN-vs-NaN matches; exactly-one-NaN mismatches; otherwise the
    absolute difference must not exceed tolerance (0.0 means exact).
    """
    try:
        saved_f = float(saved)
        replayed_f = float(replayed)
    except (TypeError, ValueError):
        return False
    saved_nan = math.isnan(saved_f)
    replayed_nan = math.isnan(replayed_f)
    if saved_nan and replayed_nan:
        return True
    if saved_nan or replayed_nan:
        return False
    return abs(saved_f - replayed_f) <= tolerance


def _compare_fingerprints(
    saved: dict,
    replayed: dict,
    tolerance_db: float,
) -> dict:
    """Compare a saved seven-key fingerprint against a replayed one.

    Args:
        saved: The seven SAVED_MEASUREMENT_KEYS fields read back from the
               file's mimir:fingerprint (or one mimir:fingerprint_sequence
               entry).
        replayed: The full fingerprint_spectrum() dict produced by
                  replaying the samples.
        tolerance_db: Match tolerance in dB for the _DB_FIELDS fields.

    Returns:
        {
            "tolerance_db": float,
            "field_results": {field: {"saved": ..., "replayed": ...,
                                      "match": bool, ...}, ...},
            "all_match": bool,
        }
    """
    field_results: dict[str, dict] = {}

    # peak_freq_hz — exact, bin-derived.
    saved_v = saved.get("peak_freq_hz")
    replayed_v = replayed.get("peak_freq_hz")
    field_results["peak_freq_hz"] = {
        "saved": saved_v,
        "replayed": replayed_v,
        "match": _values_match(saved_v, replayed_v, 0.0),
    }

    # dB-scale fields — tolerance_db, with a signed delta recorded.
    for field in _DB_FIELDS:
        saved_v = saved.get(field)
        replayed_v = replayed.get(field)
        try:
            delta_db = float(replayed_v) - float(saved_v)
        except (TypeError, ValueError):
            delta_db = float("nan")
        field_results[field] = {
            "saved": saved_v,
            "replayed": replayed_v,
            "match": _values_match(saved_v, replayed_v, tolerance_db),
            "delta_db": delta_db,
        }

    # bandwidth_hz — float-exact (do not cast to int; see module notes).
    field_results["bandwidth_hz"] = {
        "saved": saved.get("bandwidth_hz"),
        "replayed": replayed.get("bandwidth_hz"),
        "match": _values_match(
            saved.get("bandwidth_hz"), replayed.get("bandwidth_hz"), 0.0
        ),
    }

    # occupied_bins — integer-exact.
    field_results["occupied_bins"] = {
        "saved": saved.get("occupied_bins"),
        "replayed": replayed.get("occupied_bins"),
        "match": _values_match(
            saved.get("occupied_bins"), replayed.get("occupied_bins"), 0.0
        ),
    }

    # spectral_flatness — small absolute tolerance (float log-sum).
    saved_v = saved.get("spectral_flatness")
    replayed_v = replayed.get("spectral_flatness")
    try:
        delta = float(replayed_v) - float(saved_v)
    except (TypeError, ValueError):
        delta = float("nan")
    field_results["spectral_flatness"] = {
        "saved": saved_v,
        "replayed": replayed_v,
        "match": _values_match(saved_v, replayed_v, _FLATNESS_TOLERANCE),
        "delta": delta,
    }

    all_match = all(r["match"] for r in field_results.values())
    return {
        "tolerance_db": float(tolerance_db),
        "field_results": field_results,
        "all_match": all_match,
    }


def _resolve_band(core_freq_hz: float) -> tuple[str | None, str]:
    """Resolve a capture's centre frequency to a BAND_PROFILES key.

    Returns (band_key, match) where match is "exact" (a profile's
    center_freq_hz equals the capture frequency), "nearest" (the
    band_key_for_freq nearest-match fallback fired — e.g. a 915.825 MHz
    Phase 68 recording resolving to the 915.000 MHz ism profile), or
    "none" (unresolvable — caller raises ReplayFileError).
    """
    for key, profile in BAND_PROFILES.items():
        if profile["center_freq_hz"] == int(core_freq_hz):
            return key, "exact"
    key = band_key_for_freq(core_freq_hz)
    if key is None:
        return None, "none"
    return key, "nearest"


def _fingerprint_samples(
    samples,
    sample_rate_hz: float,
    core_freq_hz: float,
    band_key: str,
    device: str,
) -> dict:
    """Run compute_psd + fingerprint_spectrum over replayed samples.

    All four fingerprint_spectrum() parameters come from the SAME
    device-resolved band profile, resolved via
    resolve_band_profile(band_key, device) — the same helper the live
    scan loop uses to populate shared_state.current_band
    (dashboard/server.py). This matters for Pluto captures: a Pluto
    ADS-B file was fingerprinted at capture time against
    PLUTO_BAND_PROFILES (signal_threshold_db 10.0 dB, calibrated
    2026-08-17), so replaying it against the raw BAND_PROFILES base
    (3.0 dB) would shift occupied_bins / bandwidth_hz and report a
    structural mismatch on a capture that never changed. On "hackrf"
    (or any unknown device string) resolve_band_profile returns the
    BAND_PROFILES base unchanged, matching the pre-fix behaviour.

    fingerprint_trace_key is CRITICAL for ADS-B: that band fingerprints
    the psd_max_hold_db trace, and replaying it against the default
    averaged trace would make every ADS-B comparison structurally
    invalid. resolve_band_profile never overlays the trace key, so the
    BAND_PROFILES value carries through on both devices.
    """
    profile = resolve_band_profile(band_key, device)
    psd_result = compute_psd(samples, sample_rate_hz, core_freq_hz)
    return fingerprint_spectrum(
        psd_result,
        signal_threshold_db=profile.get("signal_threshold_db"),
        crop_half_width_hz=profile.get("crop_half_width_hz"),
        burst_use_wide_window=profile.get("burst_use_wide_window", False),
        trace_key=profile.get("fingerprint_trace_key", "psd_db"),
    )


def _validate_measurement_keys(fingerprint: Any, context: str) -> dict:
    """Validate that a saved fingerprint dict carries all seven keys."""
    if not isinstance(fingerprint, dict):
        raise ReplayFileError(
            f"{context}: expected a dict of measurement fields, got "
            f"{type(fingerprint).__name__}"
        )
    missing = [k for k in SAVED_MEASUREMENT_KEYS if k not in fingerprint]
    if missing:
        raise ReplayFileError(
            f"{context}: saved fingerprint is missing keys: "
            f"{', '.join(missing)}"
        )
    return fingerprint


def _validate_sequence(sequence: Any, total_samples: int) -> list:
    """Validate a mimir:fingerprint_sequence list BEFORE iterating.

    Caps the entry count, requires a non-negative integer sample_start
    and a positive (>= 1) integer sample_count per entry, requires
    timestamp_sec to be float-coercible (it is echoed into every
    Record-mode per-chunk result), and requires sample_start +
    sample_count to fit inside the file-implied total sample count
    (derived from core:datatype and the .sigmf-data file size by the
    SigMF library). Any violation is a ReplayFileError — no samples are
    read from a structurally invalid file.
    """
    if not isinstance(sequence, list):
        raise ReplayFileError(
            "mimir:fingerprint_sequence must be a JSON list, got "
            f"{type(sequence).__name__}"
        )
    if len(sequence) > MAX_SEQUENCE_ENTRIES:
        raise ReplayFileError(
            f"mimir:fingerprint_sequence has {len(sequence)} entries, "
            f"exceeding the {MAX_SEQUENCE_ENTRIES}-entry cap"
        )
    for idx, entry in enumerate(sequence):
        if not isinstance(entry, dict):
            raise ReplayFileError(
                f"fingerprint_sequence entry {idx} is not a dict"
            )
        sample_start = entry.get("sample_start")
        # bool is an int subclass — exclude it explicitly.
        if (
            not isinstance(sample_start, int)
            or isinstance(sample_start, bool)
            or sample_start < 0
        ):
            raise ReplayFileError(
                f"fingerprint_sequence entry {idx}: sample_start must be "
                f"a non-negative int, got {sample_start!r}"
            )
        sample_count = entry.get("sample_count")
        # sample_count must be POSITIVE: 0 passes a non-negative check
        # but read_samples(count=0) raises IOError ("Number of samples
        # must be greater than zero"), an OSError the /api/replay route
        # would miscategorise as a 500 internal_error for what is really
        # a client-named bad file.
        if (
            not isinstance(sample_count, int)
            or isinstance(sample_count, bool)
            or sample_count < 1
        ):
            raise ReplayFileError(
                f"fingerprint_sequence entry {idx}: sample_count must be "
                f"a positive int (>= 1), got {sample_count!r}"
            )
        # timestamp_sec is one of the three replay-slicing fields
        # save_recording() documents and is echoed into every Record-mode
        # result chunk. Validate it here: a missing key would otherwise
        # surface as a bare KeyError mid-loop (route 500), and a
        # non-numeric value would flow into the result unvalidated.
        try:
            float(entry["timestamp_sec"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ReplayFileError(
                f"fingerprint_sequence entry {idx}: timestamp_sec must be "
                f"float-coercible, got {entry.get('timestamp_sec')!r}"
            ) from exc
        if entry["sample_start"] + entry["sample_count"] > total_samples:
            raise ReplayFileError(
                f"fingerprint_sequence entry {idx}: sample_start "
                f"({entry['sample_start']}) + sample_count "
                f"({entry['sample_count']}) exceeds the file-implied "
                f"total of {total_samples} samples"
            )
        _validate_measurement_keys(entry, f"fingerprint_sequence entry {idx}")
    return sequence


def _load_sigmf(meta_path: Path) -> SigMFFile:
    """Load a .sigmf-meta file, converting parse failures to ReplayFileError."""
    # Accept a .sigmf-data path too — the SigMF pair shares a base name.
    if meta_path.suffix == ".sigmf-data":
        meta_path = meta_path.with_suffix(".sigmf-meta")
    try:
        # sigmf.fromfile (module-level) is the loader in sigmf 1.11.x —
        # SigMFFile.fromfile does not exist as a classmethod there.
        return sigmf.fromfile(str(meta_path))
    except (SigMFFileError, OSError, ValueError) as exc:
        raise ReplayFileError(
            f"could not load SigMF metadata from {meta_path}: {exc}"
        ) from exc


def replay_capture(
    meta_path: Path,
    tolerance_db: float = 0.1,
    wait: bool = True,
) -> dict:
    """Replay a SigMF capture through the fingerprint pipeline and compare.

    Reads the samples from the .sigmf-data sibling (NEVER from hardware),
    recomputes the spectral fingerprint under TODAY's BAND_PROFILES
    configuration, and compares it field-by-field against the fingerprint
    saved in the file at capture time.

    Device-profile resolution (HIGH-01): the capture's mimir:device_profile
    field (read from the SigMF metadata) determines which band profile is
    used for replay. "plutosdr" on a Pluto-supported band overlays
    PLUTO_BAND_PROFILES (e.g. ADS-B signal_threshold_db 10.0 dB, calibrated
    2026-08-17), while "hackrf" or any unknown device string replays against
    the BAND_PROFILES base. The result's band_resolution.profile_source
    field indicates whether "pluto_overlay" or "hackrf_base" was used.

    Mismatches are NOT failures: they are reported per field and the
    function returns normally. Only file-level problems raise:
    - Missing or malformed file
    - No fingerprint field
    - Structurally invalid fingerprint_sequence
    - Resource-cap breach
    - Unresolvable band

    Validation (MED-02, MED-03): Record-mode fingerprint_sequence entries
    are validated BEFORE iteration, requiring sample_count >= 1 (not merely
    non-negative) and timestamp_sec to be float-coercible. Any violation
    raises ReplayFileError before samples are read.

    Error wrapping (MED-01): all sigmf-library failures (SigMFFileError,
    SigMFAccessError, OSError on missing files) are converted to
    ReplayFileError, providing a single typed-error contract for callers.

    The whole body runs under REPLAY_LOCK (one replay at a time,
    process-wide). Contention behaviour is chosen by wait: the default
    wait=True blocks until any in-progress replay finishes (correct for
    the CLI); wait=False raises ReplayBusyError immediately if another
    replay holds the lock (correct for the /api/replay route, which maps
    it to a structured 503).

    Args:
        meta_path: Path to the .sigmf-meta file (a .sigmf-data path is
                   accepted and normalised to its meta sibling).
        tolerance_db: Match tolerance in dB for peak_power_db,
                      noise_floor_db and snr_db. Default 0.1.
        wait: Contention behaviour on REPLAY_LOCK (see above).

    Returns:
        A JSON-serialisable dict:
        {
            "file_metadata": {path, core_frequency_hz, core_sample_rate_hz,
                              core_datatype, mimir_device_profile,
                              fingerprint_field},
            "band_resolution": {band_key, match, band_center_freq_hz,
                                profile_source ("pluto_overlay" when the
                                capture's mimir:device_profile resolved a
                                PLUTO_BAND_PROFILES overlay, otherwise
                                "hackrf_base")},
            "per_chunk_results": [{replayed_fingerprint, saved_fingerprint,
                                   comparison, and for Record-mode also
                                   sample_start / sample_count /
                                   timestamp_sec}, ...],
            "summary": {total_chunks, matched_chunks, mismatched_chunks},
        }
        Derived measurements only — raw IQ samples never appear in the
        result.

    Raises:
        ReplayFileError: On any file-level failure (see above).
        ReplayBusyError: If wait is False and another replay holds
                         REPLAY_LOCK.
    """
    if not REPLAY_LOCK.acquire(blocking=wait):
        raise ReplayBusyError("another replay is in progress")
    try:
        return _replay_capture_impl(meta_path, tolerance_db)
    finally:
        REPLAY_LOCK.release()


def _replay_capture_impl(meta_path: Path, tolerance_db: float) -> dict:
    """The replay body. Runs only under REPLAY_LOCK (see replay_capture).

    Typed-error contract: every sigmf-library failure after the initial
    _load_sigmf() parse is converted to ReplayFileError by the except
    clause at the bottom — SigMFAccessError on a missing core:sample_rate
    (meta.sample_rate RAISES for a missing core field; it never returns
    None), SigMFFileError on a missing .sigmf-data sibling or a missing
    core:datatype. File-level failures therefore always surface as
    ReplayFileError (HTTP 400 at the /api/replay route), never as a raw
    library traceback.
    """
    meta = _load_sigmf(Path(meta_path))
    try:
        captures = meta.get_captures()
        core_freq = captures[0].get("core:frequency") if captures else None
        sample_rate = meta.sample_rate
        datatype = meta.get_global_field("core:datatype")
        if core_freq is None:
            raise ReplayFileError(
                "SigMF metadata has no core:frequency capture field — "
                "cannot resolve a band profile"
            )
        core_freq = float(core_freq)
        sample_rate = float(sample_rate)

        band_key, band_match = _resolve_band(core_freq)
        if band_key is None:
            # band_key_for_freq returned None — must be a typed error,
            # never a BAND_PROFILES[None] KeyError.
            raise ReplayFileError(
                f"could not resolve a BAND_PROFILES band for "
                f"{core_freq:.0f} Hz"
            )

        # The device the capture was recorded on decides which
        # threshold set replay compares against, mirroring the live
        # scan loop (whose current_band comes from
        # resolve_band_profile). "hackrf" — and any unknown or empty
        # device string, e.g. a hand-edited file — replays against
        # the BAND_PROFILES base; "plutosdr" on a Pluto-supported
        # band overlays PLUTO_BAND_PROFILES (e.g. ADS-B
        # signal_threshold_db 10.0 dB, calibrated 2026-08-17) so a
        # Pluto capture is compared against the same configuration
        # that produced its saved fingerprint, not the HackRF base.
        device = meta.get_global_field("mimir:device_profile") or "hackrf"
        profile_source = (
            "pluto_overlay"
            if device == "plutosdr"
            and PLUTO_BAND_PROFILES.get(band_key, {}).get("supported", False)
            else "hackrf_base"
        )

        # File-implied total sample count, computed by the SigMF
        # library from core:datatype and the .sigmf-data file size.
        total_samples = int(meta.sample_count or 0)

        saved_single = meta.get_global_field("mimir:fingerprint")
        saved_sequence = meta.get_global_field("mimir:fingerprint_sequence")
        if saved_sequence is not None:
            fingerprint_field = "mimir:fingerprint_sequence"
        elif saved_single is not None:
            fingerprint_field = "mimir:fingerprint"
        else:
            raise ReplayFileError(
                "SigMF file carries neither mimir:fingerprint nor "
                "mimir:fingerprint_sequence — nothing to compare against"
            )

        per_chunk_results: list[dict] = []

        if fingerprint_field == "mimir:fingerprint_sequence":
            sequence = _validate_sequence(saved_sequence, total_samples)
            for entry in sequence:
                # SigMFFile.read_samples — the FILE reader, not hardware.
                samples = meta.read_samples(
                    start_index=entry["sample_start"],
                    count=entry["sample_count"],
                )
                replayed = _fingerprint_samples(
                    samples, sample_rate, core_freq, band_key, device
                )
                saved_keys = {k: entry[k] for k in SAVED_MEASUREMENT_KEYS}
                per_chunk_results.append({
                    "replayed_fingerprint": replayed,
                    "saved_fingerprint": saved_keys,
                    "comparison": _compare_fingerprints(
                        saved_keys, replayed, tolerance_db
                    ),
                    "sample_start": entry["sample_start"],
                    "sample_count": entry["sample_count"],
                    "timestamp_sec": entry["timestamp_sec"],
                })
        else:
            # One-shot path: the whole file is one scan cycle. Cap the
            # whole-file read so a mislabelled Record-mode file cannot
            # be slurped into memory.
            if total_samples > MAX_ONE_SHOT_SAMPLES:
                raise ReplayFileError(
                    f"one-shot replay refused: file implies "
                    f"{total_samples} samples, exceeding the "
                    f"{MAX_ONE_SHOT_SAMPLES}-sample cap (is this a "
                    f"Record-mode file missing its fingerprint_sequence?)"
                )
            saved_keys = _validate_measurement_keys(
                saved_single, "mimir:fingerprint"
            )
            saved_keys = {k: saved_single[k] for k in SAVED_MEASUREMENT_KEYS}
            # SigMFFile.read_samples — the FILE reader, not hardware.
            samples = meta.read_samples(count=-1)
            replayed = _fingerprint_samples(
                samples, sample_rate, core_freq, band_key, device
            )
            per_chunk_results.append({
                "replayed_fingerprint": replayed,
                "saved_fingerprint": saved_keys,
                "comparison": _compare_fingerprints(
                    saved_keys, replayed, tolerance_db
                ),
            })

        matched = sum(
            1 for r in per_chunk_results if r["comparison"]["all_match"]
        )
        return {
            "file_metadata": {
                "path": str(meta_path),
                "core_frequency_hz": core_freq,
                "core_sample_rate_hz": sample_rate,
                "core_datatype": datatype,
                "mimir_device_profile": meta.get_global_field(
                    "mimir:device_profile"
                ),
                "fingerprint_field": fingerprint_field,
            },
            "band_resolution": {
                "band_key": band_key,
                "match": band_match,
                "band_center_freq_hz": (
                    BAND_PROFILES[band_key]["center_freq_hz"]
                ),
                "profile_source": profile_source,
            },
            "per_chunk_results": per_chunk_results,
            "summary": {
                "total_chunks": len(per_chunk_results),
                "matched_chunks": matched,
                "mismatched_chunks": len(per_chunk_results) - matched,
            },
        }
    except sigmf.error.SigMFError as exc:
        raise ReplayFileError(f"sigmf library error: {exc}") from exc


# ── DEFERRED ITEMS (from Phase 70 dual code review) ───────────────────────────────
# These items are documented technical debt or follow-up work identified during the
# Phase 70 finalise review. They are not blocking issues but should be addressed in
# future phases.

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
# ADVISORY: the 503 fast-fail path was verified to hold no worker thread; the route is
#     fully stateless — clean, no action needed.
# ADVISORY: MAX_ONE_SHOT_SAMPLES = 50M is generous (~380x a legitimate one-shot capture);
#     a tighter cap (2-5M) would still clear legitimate files 15-40x over — defensible
#     as-is, no action needed.
# ADVISORY: consider adding a delta (Hz / bins) on the exact-match fields
#     (peak_freq_hz, bandwidth_hz, occupied_bins) for a future "diff against historical
#     threshold" report — own phase.
# ───────────────────────────────────────────────────────────────────────────────────
