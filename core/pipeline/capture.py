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

logger = logging.getLogger(__name__)


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


def capture_and_save(
    freq_hz: float,
    num_samples: int,
    sample_rate_hz: float,
    output_dir: Path = Path("data/captures"),
    device: str = "hackrf",
    bandwidth_hz: float | None = None,
) -> Path:
    """
    Capture IQ samples and save them as a SigMF recording in one call.

    Supports both the HackRF One (device="hackrf") and the ADALM-PLUTO
    (device="plutosdr"). The device string is validated against
    _CAPTURE_DISPATCH BEFORE any hardware call - an unknown key raises
    ValueError immediately, so a typo can never open the wrong device
    or silently fall through.

    The whole call chain is RECEIVE-ONLY. Both device wrappers guard
    every transmit-capable entry point at the wrapper level, and this
    function only ever drives the RX path (open, read_samples, close).

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
        ValueError: If device is not a key of _CAPTURE_DISPATCH. Raised
                    BEFORE any hardware call.
    """
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

    return save_capture(
        samples,
        freq_hz=freq_hz,
        sample_rate_hz=sample_rate_hz,
        device=device,
        output_dir=output_dir,
        bandwidth_hz=bandwidth_hz,
    )
