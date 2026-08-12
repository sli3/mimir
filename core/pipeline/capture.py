"""
capture.py — IQ capture and save pipeline for the Mimir RF Scanner

Legal: Receive-only. Radiocommunications Act 1992 (Cth).
       No transmission. Jurisdiction: AU/SA. Authority: ACMA.
"""

import logging
from datetime import datetime
from pathlib import Path

import numpy as np
import sigmf

from core.device.hackrf_rx import HackRFReceiver
from core.device.pluto_rx import PlutoReceiver

logger = logging.getLogger(__name__)

# Maps device profile names to human-readable hardware names recorded in
# the SigMF core:hw field. Phase B will add: "pluto": "ADALM-PLUTO".
# Unknown device strings fall back to the string itself so callers never
# silently lose the value.
_DEVICE_HW_NAMES: dict[str, str] = {
    "hackrf": "HackRF One",
}


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


def save_capture(
    samples: np.ndarray,
    freq_hz: float,
    sample_rate_hz: float,
    device: str = "hackrf",
    output_dir: Path = Path("data/captures"),
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

    Args:
        samples: numpy array of complex64 IQ samples to save.
        freq_hz: Centre frequency in Hz. Recorded in the filename and in
                 the SigMF capture record (core:frequency).
        sample_rate_hz: Samples per second. Required — recorded as the
                        SigMF core:sample_rate global field; without it
                        the capture cannot be interpreted.
        device: Device profile name (e.g. "hackrf"). Stored in the
                SigMF metadata under the custom global field
                "mimir:device_profile" (the mimir: vendor-namespace
                prefix is the SigMF-spec-compliant way to carry
                non-core fields). Defaults to "hackrf".
        output_dir: Directory to save the files in. Created if it does
                    not exist. Defaults to Path("data/captures").

    Returns:
        Path to the .sigmf-meta file. This is the canonical handle for
        the recording; the sibling .sigmf-data file with the same base
        name holds the raw complex64 samples.

    Files written:
        {output_dir}/capture_{int(freq_hz)}hz_{YYYYMMDD_HHMMSS}.sigmf-data
        {output_dir}/capture_{int(freq_hz)}hz_{YYYYMMDD_HHMMSS}.sigmf-meta

    Metadata recorded:
        core:datatype    — "cf32_le" (from the complex64 array)
        core:sample_rate — sample_rate_hz
        core:hw          — human-readable hardware name ("HackRF One")
        core:description — passive-receive legal provenance note
        core:frequency   — freq_hz (capture record at sample index 0)
        mimir:device_profile — device profile name (custom global field)
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = f"capture_{int(freq_hz)}hz_{timestamp}"
    base_path = output_dir / base_name

    meta = sigmf.fromarray(samples)
    meta.sample_rate = sample_rate_hz
    meta.hw = _DEVICE_HW_NAMES.get(device, device)
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
    # call merges our frequency metadata into it rather than appending.
    meta.add_capture(start_index=0, metadata={sigmf.FREQUENCY_KEY: freq_hz})

    meta.tofile(base_path)
    meta_path = Path(str(base_path) + ".sigmf-meta")
    logger.info("Saved SigMF capture to %s", meta_path)
    return meta_path


def capture_and_save(
    freq_hz: float,
    num_samples: int,
    sample_rate_hz: float,
    output_dir: Path = Path("data/captures"),
) -> Path:
    """
    Capture IQ samples and save them as a SigMF recording in one call.

    HackRF-only: this function captures via capture_iq (HackRFReceiver).
    Pluto support and a bandwidth_hz override are a separate Phase B
    change; do not add them here.

    Uses default safe gain settings (LNA 24 dB, VGA 26 dB).
    These defaults are calibrated for the telescopic whip SMA antenna
    (~1 GHz optimised). Poor coupling at FM wavelengths requires gain
    to compensate. Confirmed safe on live hardware with Adelaide FM
    signals (no ADC saturation). Adjust only if capturing weak signals
    on bands other than FM.

    Args:
        freq_hz: Centre frequency to tune to in Hz.
        num_samples: Number of IQ samples to capture.
        sample_rate_hz: Samples per second.
        output_dir: Directory to save the files in. Defaults to
                    Path("data/captures").

    Returns:
        Path to the saved .sigmf-meta file (the canonical SigMF handle;
        the sibling .sigmf-data file holds the raw samples).
    """
    samples = capture_iq(
        freq_hz=freq_hz,
        num_samples=num_samples,
        sample_rate_hz=sample_rate_hz,
        lna_gain_db=HackRFReceiver.DEFAULT_LNA_GAIN_DB,
        vga_gain_db=HackRFReceiver.DEFAULT_VGA_GAIN_DB,
    )
    return save_capture(
        samples,
        freq_hz=freq_hz,
        sample_rate_hz=sample_rate_hz,
        device="hackrf",
        output_dir=output_dir,
    )
