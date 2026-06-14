"""
core/device/hackrf_rx.py
Mimir RF Scanner — HackRF One Receive-Only Wrapper

LEGAL NOTICE
────────────
Jurisdiction : Australia — South Australia (Adelaide)
Authority    : ACMA (Australian Communications and Media Authority)
Law          : Radiocommunications Act 1992 (Cth)
Licence held : NONE

This file provides RECEIVE-ONLY access to the HackRF One.
Any call to a transmit function raises HardwareTransmitError immediately.
No transmit path exists in this codebase.

WHAT THIS FILE DOES
───────────────────
This is the main way Mimir talks to the HackRF hardware. It wraps
the SoapySDR Python library, which in turn talks to libhackrf.

The chain is:
  Your Python code
      ↓
  HackRFReceiver (this file)
      ↓
  SoapySDR Python bindings  (python3-SoapySDR package)
      ↓
  libhackrf  (hackrf package)
      ↓
  HackRF One hardware via USB

WHY SOAPYSDR?
─────────────
SoapySDR is a "hardware abstraction layer". It means this code doesn't
need to know the exact USB commands the HackRF uses. Instead, it speaks
a generic SDR language and SoapySDR handles the translation.

This also means if you ever use a different SDR (e.g. an RTL-SDR dongle),
only the driver= argument changes — the rest of your pipeline code stays
the same.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

import numpy as np

from core.device.device_base import DeviceBase
from core.legal.compliance_guard import HardwareTransmitError, transmit_guard

logger = logging.getLogger(__name__)


class HackRFReceiver(DeviceBase):
    """
    Receive-only wrapper for the HackRF One SDR.

    Usage (context manager — recommended):
        with HackRFReceiver() as sdr:
            sdr.set_center_frequency(98_000_000)   # 98 MHz FM
            sdr.set_sample_rate(2_000_000)          # 2 MHz bandwidth
            sdr.set_gain(20)                        # 20 dB gain
            samples = sdr.read_samples(1024 * 256)  # capture IQ data

    Usage (manual):
        sdr = HackRFReceiver()
        sdr.open()
        # ... use it ...
        sdr.close()

    Hardware requirements:
        - HackRF One connected via USB
        - hackrf package installed (dnf install hackrf)
        - python3-SoapySDR installed (dnf install python3-SoapySDR)
        - Antenna attached to the SMA port before powering on
    """

    # SoapySDR direction constants — we store these as class attributes
    # so the values are visible in tests without importing SoapySDR directly.
    # SOAPY_SDR_RX = 1  (receive direction)
    # SOAPY_SDR_TX = 0  (transmit direction — BLOCKED, never used)
    _SOAPY_RX_DIRECTION: int = 1
    _SOAPY_TX_DIRECTION: int = 0  # documented here, never passed to hardware

    # Default safe receive settings
    # Calibrated for telescopic whip SMA antenna (~1 GHz optimised).
    # Poor coupling at FM wavelengths requires gain to compensate.
    # lna=24 / vga=26 confirmed safe on live hardware (no ADC saturation).
    DEFAULT_CENTER_FREQ_HZ: float = 98_000_000    # 98 MHz — FM broadcast
    DEFAULT_SAMPLE_RATE_HZ: float = 2_000_000     # 2 MHz bandwidth
    DEFAULT_LNA_GAIN_DB: float = 24               # RF front-end gain (0–40 dB)
    DEFAULT_VGA_GAIN_DB: float = 26               # Baseband gain (0–62 dB)
    DEFAULT_AMP_ENABLE: bool = False              # RF amp — leave off by default

    def __init__(
        self,
        center_freq_hz: float = DEFAULT_CENTER_FREQ_HZ,
        sample_rate_hz: float = DEFAULT_SAMPLE_RATE_HZ,
        lna_gain_db: float = DEFAULT_LNA_GAIN_DB,
        vga_gain_db: float = DEFAULT_VGA_GAIN_DB,
        amp_enable: bool = DEFAULT_AMP_ENABLE,
        serial: Optional[str] = None,
    ) -> None:
        """
        Initialise the HackRF receiver configuration.

        This does NOT open the hardware yet. Call open() or use the
        object as a context manager (with statement).

        Args:
            center_freq_hz : Frequency to tune to in Hz. Default: 98 MHz.
            sample_rate_hz : Samples per second. Default: 2 MHz.
            lna_gain_db    : LNA (low-noise amplifier) gain 0–40 dB.
                             The LNA is the first amplifier the signal
                             hits — it boosts weak signals before they
                             are processed. Start low, increase if needed.
            vga_gain_db    : VGA (variable gain amplifier) gain 0–62 dB.
                             Applied after the LNA. Controls overall
                             receive level.
            amp_enable     : Whether to enable the built-in RF amplifier.
                             Adds ~11 dB but also adds noise. Keep False
                             unless signals are very weak.
            serial         : Optional HackRF serial number. If None,
                             uses the first detected HackRF.
        """
        self._center_freq_hz = center_freq_hz
        self._sample_rate_hz = sample_rate_hz
        self._lna_gain_db = lna_gain_db
        self._vga_gain_db = vga_gain_db
        self._amp_enable = amp_enable
        self._serial = serial

        self._device = None    # SoapySDR device object — set in open()
        self._stream = None    # RX stream — set in open()
        self._is_open = False

    # ── Lifecycle ──────────────────────────────────────────────────────

    def open(self) -> None:
        """
        Open the HackRF hardware and configure the receiver.

        Raises:
            RuntimeError: If no HackRF is found or hardware fails to open.
        """
        try:
            import SoapySDR
            from SoapySDR import SOAPY_SDR_RX, SOAPY_SDR_CF32
        except ImportError as e:
            raise RuntimeError(
                "SoapySDR Python bindings not found. "
                "Install with: sudo dnf install python3-SoapySDR"
            ) from e

        # Build the device arguments string
        # driver=hackrf tells SoapySDR to use the HackRF plugin
        args = "driver=hackrf"
        if self._serial:
            args += f",serial={self._serial}"

        logger.info("Opening HackRF One (RX only)...")

        # Enumerate available devices before opening
        results = SoapySDR.Device.enumerate(args)
        if not results:
            raise RuntimeError(
                "No HackRF device found. "
                "Check USB connection and run 'hackrf_info' to verify hardware."
            )

        # Open the device
        self._device = SoapySDR.Device(args)

        # ── Configure receive channel 0 ────────────────────────────────
        # Channel 0 is the only receive channel on the HackRF One.
        # We always use _SOAPY_RX_DIRECTION (1), never TX direction (0).

        self._device.setSampleRate(self._SOAPY_RX_DIRECTION, 0, self._sample_rate_hz)
        self._device.setFrequency(self._SOAPY_RX_DIRECTION, 0, self._center_freq_hz)
        self._device.setGain(self._SOAPY_RX_DIRECTION, 0, "LNA", self._lna_gain_db)
        self._device.setGain(self._SOAPY_RX_DIRECTION, 0, "VGA", self._vga_gain_db)
        self._device.setGain(self._SOAPY_RX_DIRECTION, 0, "AMP",
                             11.0 if self._amp_enable else 0.0)

        # Set up the receive stream
        # SOAPY_SDR_CF32 = complex float32 = what we want (IQ samples as
        # complex numbers, each component a 32-bit float)
        self._stream = self._device.setupStream(self._SOAPY_RX_DIRECTION, SOAPY_SDR_CF32)
        self._device.activateStream(self._stream)
        self._is_open = True

        logger.info(
            f"HackRF One opened: "
            f"freq={self._center_freq_hz/1e6:.3f} MHz, "
            f"rate={self._sample_rate_hz/1e6:.1f} MHz, "
            f"LNA={self._lna_gain_db} dB, VGA={self._vga_gain_db} dB"
        )

    def close(self) -> None:
        """Release the HackRF hardware and free all resources."""
        if self._is_open and self._device is not None:
            if self._stream is not None:
                self._device.deactivateStream(self._stream)
                self._device.closeStream(self._stream)
                self._stream = None
            self._device = None
            self._is_open = False
            logger.info("HackRF One closed.")

    def __enter__(self) -> "HackRFReceiver":
        self.open()
        return self

    # ── Receive operations ─────────────────────────────────────────────

    def device_info(self) -> dict:
        """Return device identification information."""
        if not self._is_open:
            return {"status": "not open"}
        info = self._device.getHardwareInfo()
        return dict(info)

    def set_center_frequency(self, freq_hz: float) -> None:
        """
        Tune the receiver to a new centre frequency.

        Args:
            freq_hz: Frequency in Hz. Examples:
                     98_000_000  = 98 MHz (FM broadcast)
                     145_175_000 = 145.175 MHz (APRS — Australian)
                     1_090_000_000 = 1090 MHz (ADS-B aircraft)
        """
        self._center_freq_hz = freq_hz
        if self._is_open:
            if self._stream is not None:
                self._device.deactivateStream(self._stream)
            self._device.setFrequency(self._SOAPY_RX_DIRECTION, 0, freq_hz)
            if self._stream is not None:
                self._device.activateStream(self._stream)
                time.sleep(0.25)
            logger.debug(f"Centre frequency set to {freq_hz/1e6:.3f} MHz")

    def set_sample_rate(self, rate_hz: float) -> None:
        """
        Set the sample rate (how many IQ samples per second).

        Args:
            rate_hz: Samples per second. HackRF supports up to 20 MHz.
                     Common values: 2_000_000, 8_000_000, 10_000_000.
        """
        self._sample_rate_hz = rate_hz
        if self._is_open:
            self._device.setSampleRate(self._SOAPY_RX_DIRECTION, 0, rate_hz)
            logger.debug(f"Sample rate set to {rate_hz/1e6:.1f} MHz")

    def set_gain(self, gain_db: float) -> None:
        """
        Set combined VGA gain. For fine control use set_lna_gain / set_vga_gain.

        Args:
            gain_db: Gain in dB, applied to the VGA stage (0–62 dB).
        """
        self._vga_gain_db = gain_db
        if self._is_open:
            self._device.setGain(self._SOAPY_RX_DIRECTION, 0, "VGA", gain_db)
            logger.debug(f"VGA gain set to {gain_db} dB")

    def set_lna_gain(self, gain_db: float) -> None:
        """
        Set LNA (Low Noise Amplifier) gain separately.

        The LNA is the first amplifier in the receive chain. It boosts
        the incoming signal before any other processing, so it has the
        biggest effect on weak-signal reception.

        Args:
            gain_db: LNA gain in dB (0–40 dB in 8 dB steps on HackRF).
        """
        self._lna_gain_db = gain_db
        if self._is_open:
            self._device.setGain(self._SOAPY_RX_DIRECTION, 0, "LNA", gain_db)
            logger.debug(f"LNA gain set to {gain_db} dB")

    def read_samples(self, num_samples: int) -> np.ndarray:
        """
        Capture IQ samples from the HackRF receiver.

        What are IQ samples?
        ────────────────────
        IQ stands for In-phase / Quadrature. Each sample is a complex
        number that represents the radio signal at one instant in time:
          - The real part (I) captures one component of the signal
          - The imaginary part (Q) captures a 90-degree-shifted component
        Together they let the software determine both the amplitude (how
        strong the signal is) and the phase (where in its cycle the
        signal is) at each moment.

        The samples come back as a numpy array of complex64 values.
        complex64 means each sample uses 64 bits: 32 bits for I, 32 for Q.

        Args:
            num_samples: Number of IQ samples to capture.
                         1024 samples at 2 MHz sample rate = 0.000512 seconds
                         of radio data.

        Returns:
            numpy.ndarray of shape (num_samples,) and dtype complex64.

        Raises:
            RuntimeError: If the device is not open or capture fails.
        """
        if not self._is_open:
            raise RuntimeError("Device is not open. Call open() first.")

        output = np.zeros(num_samples, dtype=np.complex64)
        total = 0
        retry_count = 0
        while total < num_samples:
            remaining = num_samples - total
            chunk = output[total:total + remaining]
            sr = self._device.readStream(
                self._stream, [chunk], remaining, timeoutUs=int(1e7)
            )
            if sr.ret < 0:
                if sr.ret == -4 and retry_count < 1:
                    logger.debug(
                        "Stream timeout on read — retrying after post-retune flush"
                    )
                    time.sleep(0.1)
                    retry_count += 1
                    total = 0
                    output = np.zeros(num_samples, dtype=np.complex64)
                    continue
                raise RuntimeError(
                    f"HackRF read failed (SoapySDR error code {sr.ret}). "
                    f"Try reducing sample rate or checking USB connection."
                )
            total += sr.ret
            if sr.ret == 0:
                break

        return output[:total]

    # ── Transmit — all permanently blocked ────────────────────────────
    # These override DeviceBase and add explicit HackRF-specific naming.

    def transmit(self, *args, **kwargs) -> None:
        """BLOCKED — TX is a criminal offence without an ACMA licence."""
        transmit_guard("HackRFReceiver.transmit")

    def write_samples(self, *args, **kwargs) -> None:
        """BLOCKED — TX is a criminal offence without an ACMA licence."""
        transmit_guard("HackRFReceiver.write_samples")

    def writeStream(self, *args, **kwargs) -> None:
        """BLOCKED — TX is a criminal offence without an ACMA licence."""
        transmit_guard("HackRFReceiver.writeStream")

    def set_tx_gain(self, *args, **kwargs) -> None:
        """BLOCKED — TX is a criminal offence without an ACMA licence."""
        transmit_guard("HackRFReceiver.set_tx_gain")

    def set_tx_frequency(self, *args, **kwargs) -> None:
        """BLOCKED — TX is a criminal offence without an ACMA licence."""
        transmit_guard("HackRFReceiver.set_tx_frequency")

    def setupTxStream(self, *args, **kwargs) -> None:
        """BLOCKED — TX is a criminal offence without an ACMA licence."""
        transmit_guard("HackRFReceiver.setupTxStream")

    def activateTxStream(self, *args, **kwargs) -> None:
        """BLOCKED — TX is a criminal offence without an ACMA licence."""
        transmit_guard("HackRFReceiver.activateTxStream")

    # ── Properties (read-only view of current config) ──────────────────

    @property
    def center_freq_hz(self) -> float:
        return self._center_freq_hz

    @property
    def sample_rate_hz(self) -> float:
        return self._sample_rate_hz

    @property
    def is_open(self) -> bool:
        return self._is_open
