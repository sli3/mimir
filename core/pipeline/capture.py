"""
capture.py — IQ capture and save pipeline for the Mimir RF Scanner

Legal: Receive-only. Radiocommunications Act 1992 (Cth).
       No transmission. Jurisdiction: AU/SA. Authority: ACMA.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Callable

import numpy as np
import sigmf

from core.device.hackrf_rx import HackRFReceiver
from core.device.pluto_rx import PlutoReceiver
from core.device.profiles import DEVICE_PROFILES
from core.pipeline.fft import compute_psd
from core.pipeline.features import fingerprint_spectrum
from dashboard.shared_state import BAND_PROFILES

logger = logging.getLogger(__name__)

# The seven measurement keys from fingerprint_spectrum() written into
# SigMF metadata under the nested "mimir:fingerprint" global field.
# fingerprint_spectrum() returns 14 keys; the remaining seven are
# threshold/diagnostic internals (signal_threshold_db, snr_margin_db,
# peak_bin_power_db, burst_ratio_db, expected_noise_ratio_db,
# burst_excess_db, is_burst) that describe the detection pipeline rather
# than the captured spectrum, so they stay out of the recording.
_FINGERPRINT_METADATA_KEYS = (
    "peak_freq_hz",
    "peak_power_db",
    "noise_floor_db",
    "snr_db",
    "bandwidth_hz",
    "occupied_bins",
    "spectral_flatness",
)


def capture_iq(
    freq_hz: float,
    num_samples: int,
    sample_rate_hz: float,
    lna_gain_db: float,
    vga_gain_db: float,
) -> np.ndarray:
    """
    Capture IQ samples from the HackRF One at the specified frequency.

    IQ samples are complex numbers representing the radio signal at each
    instant in time. The real part (I) and imaginary part (Q) together
    encode both amplitude and phase information.

    Args:
        freq_hz: Centre frequency to tune to in Hz.
                 Example: 98_000_000 for 98 MHz FM broadcast.
        num_samples: Number of IQ samples to capture.
                     At 2 MHz sample rate, 1_000_000 samples = 0.5 seconds.
        sample_rate_hz: Samples per second. HackRF supports up to 20 MHz.
        lna_gain_db: LNA (low-noise amplifier) gain, 0-40 dB.
        vga_gain_db: VGA (variable gain amplifier) gain, 0-62 dB.

    Returns:
        numpy.ndarray of shape (num_samples,) and dtype complex64.

    Raises:
        RuntimeError: If no HackRF is found or capture fails.
    """
    sdr = HackRFReceiver(
        center_freq_hz=freq_hz,
        sample_rate_hz=sample_rate_hz,
        lna_gain_db=lna_gain_db,
        vga_gain_db=vga_gain_db,
    )

    try:
        with sdr:
            logger.info(
                "Capturing %d samples at %.3f MHz",
                num_samples,
                freq_hz / 1e6,
            )
            samples = sdr.read_samples(num_samples)
            logger.info("Captured %d IQ samples", len(samples))
            return samples
    except RuntimeError as err:
        logger.error("IQ capture failed: %s", err)
        raise


def capture_iq_pluto(
    freq_hz: float,
    num_samples: int,
    sample_rate_hz: float,
    gain_db: float,
    bandwidth_hz: float | None = None,
) -> np.ndarray:
    """
    Capture IQ samples from the ADALM-PLUTO at the specified frequency.

    The Pluto uses a SINGLE combined gain stage (0-74.5 dB), NOT the
    split LNA/VGA pair the HackRF uses, so this function takes one
    gain_db argument where capture_iq takes two. There is deliberately
    no automatic translation between the two gain models here. As
    documented in core/device/profiles.py: "There is no correct
    automatic translation from a split pair to a single combined
    figure." The two HackRF stages sit at different points in the
    receive chain and contribute differently to noise and linearity,
    so any mechanical mapping would be a fiction. Callers must pass a
    native Pluto gain directly, calibrated for the Pluto itself.

    PlutoReceiver already enforces the receive-only constraint
    internally: it guards every transmit-capable entry point so any
    such call raises before touching hardware. This function therefore
    only ever drives the RX path (open, read_samples, close).

    Args:
        freq_hz: Centre frequency to tune to in Hz.
                 Example: 1_090_000_000 for 1090 MHz ADS-B.
        num_samples: Number of IQ samples to capture.
                     At 2 MHz sample rate, 256_000 samples = 0.128 seconds.
        sample_rate_hz: Samples per second. Mimir uses 2 MHz, well
                        inside the Pluto's USB 2.0 throughput cap.
        gain_db: Combined receive gain, 0-74.5 dB.
        bandwidth_hz: RF filter bandwidth in Hz. If None, PlutoReceiver
                      defaults it to sample_rate_hz.

    Returns:
        numpy.ndarray of shape (num_samples,) and dtype complex64.

    Raises:
        ValueError: If gain_db is outside 0-74.5 dB. Raised by
                    PlutoReceiver and propagated unchanged.
        RuntimeError: If no Pluto is found or capture fails.
    """
    sdr = PlutoReceiver(
        center_freq_hz=freq_hz,
        sample_rate_hz=sample_rate_hz,
        gain_db=gain_db,
        bandwidth_hz=bandwidth_hz,
    )

    try:
        with sdr:
            logger.info(
                "Capturing %d samples at %.3f MHz",
                num_samples,
                freq_hz / 1e6,
            )
            samples = sdr.read_samples(num_samples)
            logger.info("Captured %d IQ samples", len(samples))
            return samples
    except RuntimeError as err:
        logger.error("IQ capture failed: %s", err)
        raise


# Maps device driver keys to their capture functions. Used by
# capture_and_save() to validate the device string BEFORE any hardware
# call: an unknown key raises ValueError immediately. Keys must match
# DEVICE_PROFILES exactly ("hackrf" / "plutosdr" - never "pluto").
# The dict is validation only; the actual dispatch is an explicit
# if/elif because capture_iq and capture_iq_pluto take different kwargs
# (split LNA/VGA gain model vs combined gain plus RF bandwidth).
_CAPTURE_DISPATCH: dict[str, Callable] = {
    "hackrf": capture_iq,
    "plutosdr": capture_iq_pluto,
}


def save_capture(
    samples: np.ndarray,
    freq_hz: float,
    sample_rate_hz: float,
    device: str = "hackrf",
    output_dir: Path = Path("data/captures"),
    bandwidth_hz: float | None = None,
    fingerprint: dict | None = None,
) -> Path:
    """
    Save IQ samples as a SigMF recording (.sigmf-data + .sigmf-meta pair).

    SigMF (Signal Metadata Format) makes captures self-describing: the
    sample rate, centre frequency, hardware and datatype travel with the
    raw samples, so the recording is readable by any SigMF-compatible
    tool (GNU Radio, inspectrum, iqengine) without external knowledge of
    how it was captured.

    The device identity is stored in the JSON metadata only, never in
    the filename. The filename stays controlled (numeric frequency plus
    timestamp) so no caller-controlled string can influence the path.

    This function is device-agnostic and RECEIVE-ONLY: it writes files
    and nothing else. It performs no software DSP - bandwidth_hz is
    recorded as metadata only (the operator's declared RF filter width);
    any actual narrowing happened in the device's analogue filter at
    capture time.

    Args:
        samples: numpy array of complex64 IQ samples to save.
        freq_hz: Centre frequency in Hz. Recorded in the filename and in
                 the SigMF capture record (core:frequency).
        sample_rate_hz: Samples per second. Required — recorded as the
                        SigMF core:sample_rate global field; without it
                        the capture cannot be interpreted.
        device: Device profile name - a DEVICE_PROFILES driver key
                ("hackrf" / "plutosdr"). Stored in the SigMF metadata
                under the custom global field "mimir:device_profile"
                (the mimir: vendor-namespace prefix is the
                SigMF-spec-compliant way to carry non-core fields), and
                its DEVICE_PROFILES display_name is recorded in core:hw.
                Defaults to "hackrf".
        output_dir: Directory to save the files in. Created if it does
                    not exist. Defaults to Path("data/captures").
        bandwidth_hz: RF filter bandwidth in Hz, if the capture device
                      applied one. Recorded as core:bandwidth in the
                      capture record at sample index 0. If None the key
                      is omitted entirely. Metadata only - no samples
                      are filtered, cropped, or resampled here.
        fingerprint: Spectral fingerprint dict as returned by
                     fingerprint_spectrum(). When provided, the seven
                     measurement keys in _FINGERPRINT_METADATA_KEYS are
                     written as a single nested global field,
                     "mimir:fingerprint". When None (default) the field
                     is omitted entirely. Metadata only - the samples
                     on disk are never touched by the measurement.

    Returns:
        Path to the .sigmf-meta file. This is the canonical handle for
        the recording; the sibling .sigmf-data file with the same base
        name holds the raw complex64 samples.

    Raises:
        KeyError: If device is not a DEVICE_PROFILES driver key. This is
                  deliberate fail-fast behaviour; capture_and_save()
                  validates the key with a clearer ValueError before any
                  hardware call, so direct callers of save_capture()
                  get the KeyError with the bad device key.

    Files written:
        {output_dir}/capture_{int(freq_hz)}hz_{YYYYMMDD_HHMMSS}.sigmf-data
        {output_dir}/capture_{int(freq_hz)}hz_{YYYYMMDD_HHMMSS}.sigmf-meta

    Metadata recorded:
        core:datatype    — "cf32_le" (from the complex64 array)
        core:sample_rate — sample_rate_hz
        core:hw          — DEVICE_PROFILES display_name (e.g. "HackRF One",
                           "ADALM-PLUTO")
        core:description — passive-receive legal provenance note
        core:frequency   — freq_hz (capture record at sample index 0)
        core:bandwidth   — bandwidth_hz (same capture record; only when
                           bandwidth_hz is not None)
        mimir:device_profile — device profile name (custom global field)
        mimir:fingerprint  - nested dict of the seven spectral
                             measurement keys (only when fingerprint
                             is not None)
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = f"capture_{int(freq_hz)}hz_{timestamp}"
    base_path = output_dir / base_name

    meta = sigmf.fromarray(samples)
    meta.sample_rate = sample_rate_hz
    # DEVICE_PROFILES is the single source of truth for the human-readable
    # hardware name; an unknown device key fails fast here with a KeyError.
    meta.hw = DEVICE_PROFILES[device]["display_name"]
    # Legal provenance travels with every capture as a free-text global field.
    meta.description = (
        "Mimir RF Scanner — passive receive only. "
        "Radiocommunications Act 1992 (Cth). ACMA jurisdiction. "
        "No transmission."
    )
    # Declare the mimir: extension namespace (SigMF spec requires custom
    # namespaces to be declared; an undeclared one is a DeprecationWarning
    # today and a ValidationError in future versions). The plain
    # name/version/optional keys match the sigmf 1.11.x schema.
    meta.set_global_field(
        sigmf.EXTENSIONS_KEY,
        [{"name": "mimir", "version": "1.0.0", "optional": True}],
    )
    # mimir: vendor-namespace custom field for programmatic device identity.
    meta.set_global_field("mimir:device_profile", device)
    # mimir:fingerprint carries the spectral measurement taken from these
    # samples at capture time. Kept as one nested field (never flattened
    # to the top level) so the seven measurement keys travel as a unit.
    # The samples themselves are untouched - this is a measurement
    # recorded alongside the data, not signal processing applied to it.
    if fingerprint is not None:
        meta.set_global_field(
            "mimir:fingerprint",
            {k: fingerprint[k] for k in _FINGERPRINT_METADATA_KEYS},
        )
    # Note: fromarray() pre-creates a bare capture at start_index=0; this
    # call merges our metadata into it rather than appending. bandwidth_hz
    # is metadata only (core:bandwidth) - no software DSP is applied here;
    # on Pluto the analogue RF filter does the actual narrowing, and
    # HackRF has no settable bandwidth at all.
    capture_meta = {sigmf.FREQUENCY_KEY: freq_hz}
    if bandwidth_hz is not None:
        capture_meta["core:bandwidth"] = bandwidth_hz
    meta.add_capture(start_index=0, metadata=capture_meta)

    meta.tofile(base_path)
    meta_path = Path(str(base_path) + ".sigmf-meta")
    logger.info("Saved SigMF capture to %s", meta_path)
    return meta_path


def save_recording(
    samples: np.ndarray,
    freq_hz: float,
    sample_rate_hz: float,
    device: str,
    fingerprint_sequence: list[dict],
    output_dir: Path = Path("data/captures"),
) -> Path:
    """
    Save an operator-controlled "Record" capture (Phase 68) as a SigMF
    recording (.sigmf-data + .sigmf-meta pair).

    Unlike save_capture() (a single scan cycle's samples with one
    spectral fingerprint), this saves a longer, operator-bounded
    recording: the concatenated samples of every scan cycle captured
    between the operator's start and stop actions, with ONE fingerprint
    entry PER CYCLE so any slice of the recording can be located and
    replayed later.

    The per-cycle entries are written as a JSON list under the
    "mimir:fingerprint_sequence" global field. Each entry carries the
    seven _FINGERPRINT_METADATA_KEYS measurement fields plus:

        sample_start   — int, cumulative sample offset of this cycle
                         into the concatenated buffer. Ground truth for
                         replay slicing: cycle N's samples occupy
                         [sample_start, sample_start + sample_count).
        sample_count   — int, number of samples this cycle contributed.
        timestamp_sec  — float, sample_start / sample_rate_hz. A
                         display convenience derived from sample_start;
                         sample_start remains the authoritative value.

    MUTUAL EXCLUSION CONTRACT: this function writes
    "mimir:fingerprint_sequence" and NEVER the singular
    "mimir:fingerprint" field; save_capture() does the reverse. A
    recorded file therefore always has exactly one of the two, by
    construction, with no either/or ambiguity for downstream readers.

    Defensive re-filtering: each caller-supplied entry is re-filtered
    through the SAME _FINGERPRINT_METADATA_KEYS allowlist used by
    save_capture(). Internal-only keys (signal_threshold_db,
    snr_margin_db, is_burst, etc.) are stripped even if the caller
    passes them, so this function has the same safety property as
    save_capture() regardless of what the caller hands over.

    DRIFT RISK: save_capture() must remain byte-for-byte stable for
    existing consumers, so the SigMF boilerplate below is DUPLICATED
    rather than shared through a helper. Any future SigMF metadata
    change (namespace declaration, description text, capture-record
    shape) must be applied to BOTH functions in lockstep.

    This function is device-agnostic and RECEIVE-ONLY: it writes files
    and nothing else. No hardware access, no DSP.

    Args:
        samples: numpy array of complex64 IQ samples - the concatenation
                 of every scan cycle captured during the recording.
        freq_hz: Centre frequency in Hz. The frequency at record START;
                 if the operator changed the focus frequency mid-
                 recording the recording continues but the file records
                 the start frequency (see ScanRunner's frequency-change
                 guard). Recorded in the filename and in the SigMF
                 capture record (core:frequency).
        sample_rate_hz: Samples per second. Recorded as the SigMF
                        core:sample_rate global field and used by the
                        scan loop to derive each entry's timestamp_sec.
        device: Device profile name - a DEVICE_PROFILES driver key
                ("hackrf" / "plutosdr"). Stored under
                "mimir:device_profile" and its DEVICE_PROFILES
                display_name is recorded in core:hw.
        fingerprint_sequence: Per-cycle fingerprint dicts, one per scan
                cycle, in capture order. Each must already carry
                sample_start / sample_count / timestamp_sec; the seven
                measurement keys are re-filtered through
                _FINGERPRINT_METADATA_KEYS here regardless of what else
                the caller included.
        output_dir: Directory to save the files in. Created if it does
                    not exist. Defaults to Path("data/captures").

    Returns:
        Path to the .sigmf-meta file. This is the canonical handle for
        the recording; the sibling .sigmf-data file with the same base
        name holds the raw complex64 samples.

    Raises:
        KeyError: If device is not a DEVICE_PROFILES driver key (same
                  fail-fast behaviour as save_capture()).

    Files written:
        {output_dir}/capture_{int(freq_hz)}hz_{YYYYMMDD_HHMMSS}.sigmf-data
        {output_dir}/capture_{int(freq_hz)}hz_{YYYYMMDD_HHMMSS}.sigmf-meta

    Metadata recorded:
        core:datatype    — "cf32_le" (from the complex64 array)
        core:sample_rate — sample_rate_hz
        core:hw          — DEVICE_PROFILES display_name (e.g. "HackRF One",
                           "ADALM-PLUTO")
        core:description — passive-receive legal provenance note
        core:frequency   — freq_hz (capture record at sample index 0)
        mimir:device_profile — device profile name (custom global field)
        mimir:fingerprint_sequence — JSON list of per-cycle entries,
                           each the seven measurement keys plus
                           sample_start / sample_count / timestamp_sec
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = f"capture_{int(freq_hz)}hz_{timestamp}"
    base_path = output_dir / base_name

    meta = sigmf.fromarray(samples)
    meta.sample_rate = sample_rate_hz
    # DEVICE_PROFILES is the single source of truth for the human-readable
    # hardware name; an unknown device key fails fast here with a KeyError.
    meta.hw = DEVICE_PROFILES[device]["display_name"]
    # Legal provenance travels with every capture as a free-text global field.
    meta.description = (
        "Mimir RF Scanner — passive receive only. "
        "Radiocommunications Act 1992 (Cth). ACMA jurisdiction. "
        "No transmission."
    )
    # Declare the mimir: extension namespace (SigMF spec requires custom
    # namespaces to be declared; an undeclared one is a DeprecationWarning
    # today and a ValidationError in future versions). The plain
    # name/version/optional keys match the sigmf 1.11.x schema.
    meta.set_global_field(
        sigmf.EXTENSIONS_KEY,
        [{"name": "mimir", "version": "1.0.0", "optional": True}],
    )
    # mimir: vendor-namespace custom field for programmatic device identity.
    meta.set_global_field("mimir:device_profile", device)
    # Per-cycle fingerprint sequence. Each entry is re-filtered through
    # the same _FINGERPRINT_METADATA_KEYS allowlist save_capture() uses,
    # then extended with the three replay-slicing fields. Internal-only
    # keys are stripped here even if the caller passed them. The singular
    # "mimir:fingerprint" field is deliberately NEVER set by this
    # function - the two fields are mutually exclusive by construction.
    meta.set_global_field(
        "mimir:fingerprint_sequence",
        [
            {
                **{k: entry[k] for k in _FINGERPRINT_METADATA_KEYS},
                "sample_start": int(entry["sample_start"]),
                "sample_count": int(entry["sample_count"]),
                "timestamp_sec": float(entry["timestamp_sec"]),
            }
            for entry in fingerprint_sequence
        ],
    )
    # Note: fromarray() pre-creates a bare capture at start_index=0; this
    # call merges our metadata into it rather than appending.
    capture_meta = {sigmf.FREQUENCY_KEY: freq_hz}
    meta.add_capture(start_index=0, metadata=capture_meta)

    meta.tofile(base_path)
    meta_path = Path(str(base_path) + ".sigmf-meta")
    logger.info("Saved SigMF recording to %s", meta_path)
    return meta_path


def capture_and_save(
    freq_hz: float,
    num_samples: int,
    sample_rate_hz: float,
    band: str,
    output_dir: Path = Path("data/captures"),
    device: str = "hackrf",
    bandwidth_hz: float | None = None,
) -> Path:
    """
    Capture IQ samples and save them as a SigMF recording in one call.

    Supports both the HackRF One (device="hackrf") and the ADALM-PLUTO
    (device="plutosdr"). Both the band string and the device string are
    validated BEFORE any hardware call - an unrecognised band raises
    ValueError against BAND_PROFILES and an unknown device raises
    ValueError against _CAPTURE_DISPATCH, so a typo can never open the
    wrong device or silently fall through. The band is never guessed
    from freq_hz; the caller must state it explicitly.

    The whole call chain is RECEIVE-ONLY. Both device wrappers guard
    every transmit-capable entry point at the wrapper level, and this
    function only ever drives the RX path (open, read_samples, close).

    After the samples come back, a spectral fingerprint is measured
    from them (compute_psd then fingerprint_spectrum, parameterised by
    the band's BAND_PROFILES entry) and recorded in the SigMF metadata
    as the nested "mimir:fingerprint" global field. This is a
    measurement only: the samples written to .sigmf-data are unchanged
    and unfiltered, and no software DSP, cropping, or decimation is
    applied to them.

    Gain handling per device:
      - HackRF uses its split gain model with the wrapper defaults
        (LNA 24 dB, VGA 26 dB), calibrated for the telescopic whip SMA
        antenna and confirmed safe on live Adelaide FM signals.
      - Pluto uses its single combined gain stage at
        PlutoReceiver.DEFAULT_GAIN_DB (30.0 dB). That figure is
        PROVISIONAL - chosen from spur observation, NOT from a
        calibration session. See the pluto_rx.py module docstring and
        the PLUTO_BAND_PROFILES comments in dashboard/shared_state.py.

    bandwidth_hz handling per device:
      - Pluto: passed through to capture_iq_pluto, where PlutoReceiver
        applies it to the analogue RF filter.
      - HackRF: the HackRF has no settable RF bandwidth, so the value
        is NOT passed to capture_iq. A warning is logged, but the value
        is still recorded in the SigMF metadata (core:bandwidth) because
        it records the operator's intent.

    Args:
        freq_hz: Centre frequency to tune to in Hz.
        num_samples: Number of IQ samples to capture.
        sample_rate_hz: Samples per second.
        band: BAND_PROFILES key (e.g. "fm_broadcast", "adsb"). Required.
              Selects the per-band signal_threshold_db,
              fingerprint_trace_key, crop_half_width_hz, and
              burst_use_wide_window used for the fingerprint
              measurement. Any key not defined by the band's
              profile falls back to fingerprint_spectrum()'s own default.
        output_dir: Directory to save the files in. Defaults to
                    Path("data/captures").
        device: DEVICE_PROFILES driver key - "hackrf" or "plutosdr".
                Defaults to "hackrf".
        bandwidth_hz: RF filter bandwidth in Hz. Applied only on Pluto;
                      logged-and-ignored (but still recorded in metadata)
                      on HackRF. Defaults to None.

    Returns:
        Path to the saved .sigmf-meta file (the canonical SigMF handle;
        the sibling .sigmf-data file holds the raw samples).

    Raises:
        ValueError: If band is not a key of BAND_PROFILES, or device is
                    not a key of _CAPTURE_DISPATCH. Both are raised
                    BEFORE any hardware call.
    """
    if band not in BAND_PROFILES:
        raise ValueError(
            f"Unknown band {band!r} - valid bands: "
            f"{', '.join(sorted(BAND_PROFILES.keys()))}"
        )

    capture_fn = _CAPTURE_DISPATCH.get(device)
    if capture_fn is None:
        raise ValueError(
            f"Unknown device {device!r} — valid devices: "
            f"{', '.join(sorted(_CAPTURE_DISPATCH.keys()))}"
        )

    if device == "hackrf":
        if bandwidth_hz is not None:
            logger.warning(
                "bandwidth_hz ignored (HackRF has no settable RF filter): "
                "%s Hz requested; metadata will still record the value",
                bandwidth_hz,
            )
        samples = capture_iq(
            freq_hz=freq_hz,
            num_samples=num_samples,
            sample_rate_hz=sample_rate_hz,
            lna_gain_db=HackRFReceiver.DEFAULT_LNA_GAIN_DB,
            vga_gain_db=HackRFReceiver.DEFAULT_VGA_GAIN_DB,
        )
    elif device == "plutosdr":
        # PlutoReceiver.DEFAULT_GAIN_DB (30.0) is provisional - chosen
        # from spur observation, NOT from a calibration session.
        # See the pluto_rx.py module docstring and the PLUTO_BAND_PROFILES
        # comments in dashboard/shared_state.py.
        samples = capture_iq_pluto(
            freq_hz=freq_hz,
            num_samples=num_samples,
            sample_rate_hz=sample_rate_hz,
            gain_db=PlutoReceiver.DEFAULT_GAIN_DB,
            bandwidth_hz=bandwidth_hz,
        )
    else:
        # Unreachable - _CAPTURE_DISPATCH validation above would have
        # raised already. Defensive only.
        raise ValueError(f"Unknown device {device!r}")  # pragma: no cover

    # Measure the spectral fingerprint from the captured samples. The
    # band profile supplies the per-band measurement parameters; any key
    # a profile does not define falls back to fingerprint_spectrum()'s
    # own default via .get() (signal_threshold_db=None, trace_key='psd_db',
    # crop_half_width_hz=None, burst_use_wide_window=False). This is a
    # measurement recorded as metadata - the samples passed to
    # save_capture below are the raw captures, unmodified.
    profile = BAND_PROFILES[band]
    psd_result = compute_psd(samples, sample_rate_hz, freq_hz)
    fingerprint = fingerprint_spectrum(
        psd_result,
        signal_threshold_db=profile.get("signal_threshold_db"),
        trace_key=profile.get("fingerprint_trace_key", "psd_db"),
        crop_half_width_hz=profile.get("crop_half_width_hz"),
        burst_use_wide_window=profile.get("burst_use_wide_window", False),
    )

    return save_capture(
        samples,
        freq_hz=freq_hz,
        sample_rate_hz=sample_rate_hz,
        device=device,
        output_dir=output_dir,
        bandwidth_hz=bandwidth_hz,
        fingerprint=fingerprint,
    )
