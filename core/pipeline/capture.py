"""
capture.py — IQ capture and save pipeline for the Mimir RF Scanner

Legal: Receive-only. Radiocommunications Act 1992 (Cth).
       No transmission. Jurisdiction: AU/SA. Authority: ACMA.
"""

import logging
from datetime import datetime
from pathlib import Path

import numpy as np

from core.device.hackrf_rx import HackRFReceiver

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


def save_capture(
    samples: np.ndarray,
    freq_hz: float,
    output_dir: Path = Path("data/captures"),
) -> Path:
    """
    Save IQ samples to a .npy file with a timestamped filename.

    Args:
        samples: numpy array of complex64 IQ samples to save.
        freq_hz: Centre frequency in Hz, included in the filename.
        output_dir: Directory to save the file in. Created if it does not exist.
                    Defaults to Path("data/captures").

    Returns:
        Path to the saved .npy file.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"capture_{int(freq_hz)}hz_{timestamp}.npy"
    filepath = output_dir / filename

    np.save(filepath, samples)
    logger.info("Saved capture to %s", filepath)
    return filepath


def capture_and_save(
    freq_hz: float,
    num_samples: int,
    sample_rate_hz: float,
    output_dir: Path = Path("data/captures"),
) -> Path:
    """
    Capture IQ samples and save them to a .npy file in one call.

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
        output_dir: Directory to save the file in. Defaults to Path("data/captures").

    Returns:
        Path to the saved .npy file.
    """
    samples = capture_iq(
        freq_hz=freq_hz,
        num_samples=num_samples,
        sample_rate_hz=sample_rate_hz,
        lna_gain_db=HackRFReceiver.DEFAULT_LNA_GAIN_DB,
        vga_gain_db=HackRFReceiver.DEFAULT_VGA_GAIN_DB,
    )
    return save_capture(samples, freq_hz, output_dir)
